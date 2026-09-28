"""G-103: enseñanza del modelo de utilidad por candidata (regresión logística, biblioteca estándar).

python3 -m experiments.g103_educar BASE.json SALIDA.json CARPETA_BANCO... [--sin-pares] [--barajar-pares] [--semilla N]

Cada turno con acción `responder` y claves (con al menos una unidad que las contiene) o con acción `abstenerse`/`derivar`
enseña: para cada una de las primeras ocho candidatas, etiqueta 1 si la unidad contiene todas las claves. Las preguntas
sin ninguna unidad que contenga las claves (cuentas, datos repartidos) no enseñan.  Se guardan solo pesos y cuentas:
ningún texto de pregunta ni de respuesta (los pares son «palabra|palabra», con apoyo en ≥ 3 candidatas).

Calibración: puntajes de la candidata elegida en cada turno, obtenidos con modelos que no vieron ese negocio (5 grupos por
sha256 del banco y el negocio); ajuste isotónico con tramos de ≥ 30.  Controles: `--sin-pares` (ablación) y `--barajar-pares`
(las palabras de los pares de cada candidata se toman de otra candidata al azar: señal confundida).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from leobot import Bot
from leobot.context import DENSE_FEATURES

FOLDS = 5
PAIR_SCALE = 0.5
PAIR_SUPPORT = 3
C = 0.3
EPOCHS = 25
ETA = 0.3
MIN_BLOCK = 30
B0_CITE = 0.4


def contains(text: str, keys) -> bool:
    haystack = f' {plain(text)} '
    return all(f' {plain(k)} ' in haystack for k in keys if plain(k))


def extract(bot: Bot, folders, shuffle_pairs=False, seed=0):
    """One record per teaching turn: business group, candidates (dense, pairs, label)."""
    rng = random.Random(seed)
    records = []
    for folder in folders:
        for name, text, instructions, conversations in businesses([folder]):
            bot.load_context(text, instructions)
            group = int(hashlib.sha256(f'{Path(folder).name}/{name}'.encode()).hexdigest(), 16) % FOLDS
            for conversation in conversations:
                for turn in conversation:
                    action = turn.get('accion', 'responder')
                    if action == 'charla':
                        continue
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    _, question = bot._question_part(turn['cliente'])
                    terms = bot.context_terms(question)
                    if not terms:
                        continue
                    gold = set()
                    if action == 'responder':
                        if not keys:
                            continue
                        gold = {i for i, u in enumerate(bot.context_units)
                                if u['kind'] != 'question' and contains(u['text'], keys)}
                        if not gold:
                            continue
                    bot.soft_prefix = False
                    old = bot._rank(terms, question)      # línea base: confianza de siete rasgos, sin prefijos
                    bot.soft_prefix = True
                    base, gains, how, asked = bot._gains(terms, question)
                    table = bot._candidate_table(terms, question, base, gains, how, asked)
                    if not table:
                        continue
                    if shuffle_pairs:
                        donors = [c['pairs'] for c in table]
                        rng.shuffle(donors)
                        for c, pairs in zip(table, donors):
                            c['pairs'] = pairs
                    records.append({'group': group, 'answerable': action == 'responder',
                                    'b0_cites': bool(old and old.get('useful') is not None and old['useful'] >= B0_CITE),
                                    'candidates': [(c['dense'], c['pairs'], int(c['unit'] in gold)) for c in table]})
    return records


def fit(records, use_pairs=True, seed=0):
    rows = [(dense, pairs, label) for r in records for dense, pairs, label in r['candidates']]
    n_features = len(DENSE_FEATURES)
    mean = [sum(r[0][j] for r in rows) / len(rows) for j in range(n_features)]
    scale = [math.sqrt(sum((r[0][j] - mean[j]) ** 2 for r in rows) / len(rows)) or 1.0 for j in range(n_features)]
    support: dict = {}
    if use_pairs:
        for _, pairs, _ in rows:
            for key in set(pairs):
                support[key] = support.get(key, 0) + 1
    vocabulary = sorted(k for k, v in support.items() if v >= PAIR_SUPPORT)
    index = {k: j for j, k in enumerate(vocabulary)}
    data = [([(x - m) / s for x, m, s in zip(dense, mean, scale)], [index[k] for k in set(pairs) if k in index], label)
            for dense, pairs, label in rows]
    w = [0.0] * n_features
    b = math.log((sum(r[2] for r in data) + 1) / (len(data) - sum(r[2] for r in data) + 1))
    v = [0.0] * len(vocabulary)
    gw, gv, gb = [1e-8] * n_features, [1e-8] * len(vocabulary), 1e-8
    decay = 1.0 / (C * len(data))
    order = list(range(len(data)))
    rng = random.Random(seed)
    for _ in range(EPOCHS):
        rng.shuffle(order)
        for k in order:
            dense, pairs, label = data[k]
            z = b + sum(a * c for a, c in zip(w, dense)) + PAIR_SCALE * sum(v[j] for j in pairs)
            err = (1.0 / (1.0 + math.exp(-z)) if z > -30 else 0.0) - label
            gb += err * err
            b -= ETA * err / math.sqrt(gb)
            for j in range(n_features):
                g = err * dense[j] + decay * w[j]
                gw[j] += g * g
                w[j] -= ETA * g / math.sqrt(gw[j])
            for j in pairs:
                g = err * PAIR_SCALE + decay * v[j]
                gv[j] += g * g
                v[j] -= ETA * g / math.sqrt(gv[j])
    pairs_weights = {k: round(v[j], 4) for k, j in index.items() if abs(v[j]) >= 0.005}
    return {'dense': list(DENSE_FEATURES), 'mean': [round(m, 6) for m in mean], 'scale': [round(s, 6) for s in scale],
            'weights': [round(x, 5) for x in w], 'bias': round(b, 5), 'pairs': pairs_weights, 'pair_scale': PAIR_SCALE}


def z_of(model, dense, pairs):
    z = model['bias'] + sum(w * (x - m) / s for x, m, s, w in zip(dense, model['mean'], model['scale'], model['weights']))
    return z + model['pair_scale'] * sum(model['pairs'].get(k, 0.0) for k in pairs)


def chosen(model, record):
    best = max(record['candidates'], key=lambda c: z_of(model, c[0], c[1]))
    return z_of(model, best[0], best[1]), best[2]


def isotonic(points):
    """Pool-adjacent-violators over (score, correct) pairs, then blocks of at least MIN_BLOCK: [[low, rate, n], ...]."""
    points = sorted(points)
    blocks = [[1.0 * y, 1, x, x] for x, y in points]
    merged = []
    for block in blocks:
        merged.append(block)
        while len(merged) > 1 and merged[-2][0] / merged[-2][1] >= merged[-1][0] / merged[-1][1]:
            last = merged.pop()
            merged[-1] = [merged[-1][0] + last[0], merged[-1][1] + last[1], merged[-1][2], last[3]]
    out, pending = [], None
    for block in merged:
        pending = block if pending is None else [pending[0] + block[0], pending[1] + block[1], pending[2], block[3]]
        if pending[1] >= MIN_BLOCK:
            out.append(pending)
            pending = None
    if pending is not None:
        if out:
            out[-1] = [out[-1][0] + pending[0], out[-1][1] + pending[1], out[-1][2], pending[3]]
        else:
            out.append(pending)
    return [[round(-1e9 if k == 0 else b[2], 5), round((b[0] + 1) / (b[1] + 2), 4), b[1]] for k, b in enumerate(out)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    seed = int(sys.argv[sys.argv.index('--semilla') + 1]) if '--semilla' in sys.argv else 0
    if '--semilla' in sys.argv:
        args.remove(sys.argv[sys.argv.index('--semilla') + 1])
    base, out, folders = Path(args[0]), Path(args[1]), args[2:]
    use_pairs = '--sin-pares' not in sys.argv
    t0 = time.process_time()
    bot = Bot.load(base)
    bot.candidate_model = False
    records = extract(bot, folders, shuffle_pairs='--barajar-pares' in sys.argv, seed=seed)
    t_extract = time.process_time() - t0
    cross = []
    for fold in range(FOLDS):
        train = [r for r in records if r['group'] != fold]
        model = fit(train, use_pairs, seed)
        cross += [chosen(model, r) + (r['answerable'],) for r in records if r['group'] == fold]
    final = fit(records, use_pairs, seed)
    points = [(z, int(label and answerable)) for z, label, answerable in cross]
    final['calibration'] = isotonic(points)

    def rate_of(z):
        rate = final['calibration'][0][1]
        for low, block_rate, _ in final['calibration']:
            if z >= low:
                rate = block_rate
        return rate
    # Umbral de cita: el menor cuya tasa de citas sobre lo no respondible, medida con puntajes cruzados, no supera la de la
    # confianza anterior (0,4) en los mismos turnos.
    silent = [r for r in records if not r['answerable']]
    budget = sum(r['b0_cites'] for r in silent) / max(1, len(silent))
    scores = [rate_of(z) for (z, _, answerable) in cross if not answerable]
    threshold = 1.0
    for candidate in sorted(set(rate_of(z) for z, _, _ in cross)):
        if sum(x >= candidate for x in scores) / max(1, len(scores)) <= budget:
            threshold = candidate
            break
    final['cite_from'] = round(threshold, 4)
    final['cite_budget'] = round(budget, 4)
    answerable_cross = [(z, label) for z, label, answerable in cross if answerable]
    top1 = sum(label for _, label in answerable_cross) / max(1, len(answerable_cross))
    final['candidates'] = 8
    final['source'] = {'folders': [Path(f).name for f in folders], 'turns': len(records),
                       'candidates': sum(len(r['candidates']) for r in records), 'pairs': len(final['pairs']),
                       'use_pairs': use_pairs, 'shuffled_pairs': '--barajar-pares' in sys.argv, 'seed': seed}
    bot.context_model['usefulness'] = final
    bot.load_context('')
    bot.save(out)
    print(json.dumps({'cite_from': final['cite_from'], 'presupuesto_citas_sin_dato': final['cite_budget'],
                      'acierto_entre_respondibles_cruzado': round(top1, 4),
                      'turnos': len(records), 'pares': len(final['pairs']), 'bloques': len(final['calibration']),
                      'cpu_extraer_s': round(t_extract, 1), 'cpu_total_s': round(time.process_time() - t0, 1),
                      'bytes': out.stat().st_size}))


if __name__ == '__main__':
    main()

"""G-103: enseñanza del modelo de utilidad por candidata (regresión logística, biblioteca estándar).

python3 -m experiments.g103_educar BASE.json SALIDA.json CARPETA_BANCO... [--sin-pares] [--barajar-pares] [--sin-historial] [--sin-instrucciones] [--semilla N]

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
import os
PAIR_SUPPORT = int(os.environ.get('PAIR_SUPPORT', '4'))
PAIR_KEEP = float(os.environ.get('PAIR_KEEP', '0.04'))
C = float(os.environ.get('C_REG', '0.3'))
EPOCHS = int(os.environ.get('EPOCHS', '25'))
ETA = 0.3
MIN_BLOCK = 30
B0_CITE = 0.4


def contains(text: str, keys) -> bool:
    haystack = f' {plain(text)} '
    return all(f' {plain(k)} ' in haystack for k in keys if plain(k))


def instruction_gold(bot, evidence, keys, action):
    """G-105: sentences of the instructions that back the turn: they hold every key, or hold the evidence, or are held by it."""
    gold = set()
    pe = plain(evidence or '')
    for k, u in enumerate(bot.context_instructions):
        if u['kind'] in ('heading', 'question'):
            continue
        pu = plain(u['text'])
        if action == 'responder' and keys and contains(u['text'], keys):
            gold.add(k)
        elif pe and len(pu.split()) >= 3 and (pu in pe or pe in pu):
            gold.add(k)
    return gold


def one_turn(bot, turn, group, history, shuffle_pairs, rng):
    action = turn.get('accion', 'responder')
    if action == 'charla':
        return None
    keys = [k for k in turn.get('claves') or [] if plain(k)]
    _, question = bot._question_part(turn['cliente'])
    terms = bot.context_terms(question)
    if not terms:
        return None
    gold, gold_instructions = set(), set()
    evidence = turn.get('evidencia')
    if bot.context_instructions and getattr(bot, 'follow_instructions', True):
        gold_instructions = instruction_gold(bot, evidence, keys, action)
    if action == 'responder':
        if not keys and not gold_instructions:
            return None
        if keys:
            gold = {i for i, u in enumerate(bot.context_units) if u['kind'] != 'question' and contains(u['text'], keys)}
        if not gold and not gold_instructions:
            return None
    bot.soft_prefix = False
    old = bot._rank(terms, question)      # línea base: confianza de siete rasgos, sin prefijos
    bot.soft_prefix = True
    previous = bot._previous_topic(history)
    base, gains, how, asked = bot._gains(terms, question)
    table = bot._candidate_table(terms, question, base, gains, how, asked, previous)
    labels = [int(c['unit'] in gold) for c in table]
    spaces = [0] * len(table)
    view = bot._instruction_view() if getattr(bot, 'follow_instructions', True) else None
    if view is not None:
        ibase, igains, ihow, iasked = view._gains(terms, question)
        itable = view._candidate_table(terms, question, ibase, igains, ihow, iasked)
        table += itable
        labels += [int(c['unit'] in gold_instructions) for c in itable]
        spaces += [1] * len(itable)
    if not table:
        return None
    if shuffle_pairs:
        donors = [c['pairs'] for c in table]
        rng.shuffle(donors)
        for c, pairs in zip(table, donors):
            c['pairs'] = pairs
    return {'group': group, 'answerable': bool(gold or gold_instructions),
            'b0_cites': bool(old and old.get('useful') is not None and old['useful'] >= B0_CITE),
            'candidates': [(c['dense'], c['pairs'], label, space) for c, label, space in zip(table, labels, spaces)]}


FALLBACK_EXAMPLES: list = []


def extract(bot: Bot, folders, shuffle_pairs=False, seed=0):
    """One record per teaching turn: business group, candidates (dense, pairs, label).  The earlier turns of the
    conversation are the history, as the caller of `Bot.answer` would send them."""
    rng = random.Random(seed)
    records = []
    for folder in folders:
        for name, text, instructions, conversations in businesses([folder]):
            bot.load_context(text, instructions)
            group = int(hashlib.sha256(f'{Path(folder).name}/{name}'.encode()).hexdigest(), 16) % FOLDS
            exits = set()
            for conversation in conversations:
                for turn in conversation:
                    if turn.get('tipo') == 'sin_respuesta' and turn.get('accion') in ('derivar', 'abstenerse') and turn.get('evidencia'):
                        exits |= instruction_gold(bot, turn['evidencia'], [], 'derivar')
            for k, u in enumerate(bot.context_instructions):
                if u['kind'] not in ('heading', 'question'):
                    FALLBACK_EXAMPLES.append((group, list(u['terms']), int(k in exits)))
            for conversation in conversations:
                history = []
                for turn in conversation:
                    record = one_turn(bot, turn, group, history, shuffle_pairs, rng)
                    history.append({'role': 'user', 'text': turn['cliente']})
                    if record is not None:
                        records.append(record)
    return records


def fit(records, use_pairs=True, seed=0):
    rows = [(dense, pairs, label) for r in records for dense, pairs, label, _ in r['candidates']]
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
    data = [([(x - m) / s for x, m, s in zip(dense, mean, scale)], [index[k] for k in sorted(set(pairs)) if k in index], label)
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
    pairs_weights = {k: round(v[j], 3) for k, j in index.items() if abs(v[j]) >= PAIR_KEEP and k.count('|') == 1 and ';' not in k}
    return {'dense': list(DENSE_FEATURES), 'mean': [round(m, 6) for m in mean], 'scale': [round(s, 6) for s in scale],
            'weights': [round(x, 5) for x in w], 'bias': round(b, 5), 'pairs': pairs_weights, 'pair_scale': PAIR_SCALE}


def grouped(pairs: dict) -> dict:
    """Guardado compacto: ``{palabra de la pregunta o marca: 'resto:peso;resto:peso'}``."""
    out: dict = {}
    for key, weight in sorted(pairs.items()):
        head, tail = key.split('|')
        out.setdefault(head, []).append(f'{tail}:{weight:g}')
    return {head: ';'.join(items) for head, items in out.items()}


def fit_fallback(examples, seed=0):
    """G-105: regresión logística sobre las palabras de una frase de instrucciones: ¿dice qué hacer cuando falta el dato?"""
    support: dict = {}
    for _, terms, _ in examples:
        for t in set(terms):
            support[t] = support.get(t, 0) + 1
    vocabulary = sorted(t for t, n in support.items() if n >= 2)
    index = {t: j for j, t in enumerate(vocabulary)}
    data = [([index[t] for t in sorted(set(terms)) if t in index], label) for _, terms, label in examples]
    positives = sum(label for _, label in data)
    b = math.log((positives + 1) / (len(data) - positives + 1))
    w, gw, gb = [0.0] * len(vocabulary), [1e-8] * len(vocabulary), 1e-8
    decay = 1.0 / (1.0 * len(data))
    rng, order = random.Random(seed), list(range(len(data)))
    for _ in range(EPOCHS + 15):
        rng.shuffle(order)
        for k in order:
            features, label = data[k]
            z = b + sum(w[j] for j in features)
            err = (1.0 / (1.0 + math.exp(-z)) if z > -30 else 0.0) - label
            gb += err * err
            b -= ETA * err / math.sqrt(gb)
            for j in features:
                g = err + decay * w[j]
                gw[j] += g * g
                w[j] -= ETA * g / math.sqrt(gw[j])
    return {'bias': round(b, 5), 'weights': {t: round(w[j], 4) for t, j in index.items() if abs(w[j]) >= 0.01}}


def fallback_model(examples, seed=0):
    cross = []
    for fold in range(FOLDS):
        model = fit_fallback([e for e in examples if e[0] != fold], seed)
        for _, terms, label in [e for e in examples if e[0] == fold]:
            z = model['bias'] + sum(model['weights'].get(t, 0.0) for t in set(terms))
            cross.append((1.0 / (1.0 + math.exp(-z)) if z > -30 else 0.0, label))
    threshold, best = 0.9, (0.0, 0.0)
    total = sum(label for _, label in cross)
    for candidate in sorted({round(c, 3) for c, _ in cross}):
        chosen = [(c, y) for c, y in cross if c >= candidate]
        if not chosen:
            continue
        precision = sum(y for _, y in chosen) / len(chosen)
        recall = sum(y for _, y in chosen) / total if total else 0.0
        if precision >= 0.7 and recall > best[1]:
            threshold, best = candidate, (precision, recall)
    if best[1] == 0.0:
        return None          # resultado negativo: con tan pocos negocios que la traen no se aprende una salida fiable
    final = fit_fallback(examples, seed)
    final.update({'threshold': round(threshold, 3), 'cross_precision': round(best[0], 3), 'cross_recall': round(best[1], 3),
                  'examples': len(examples), 'positives': total})
    return final


def z_of(model, dense, pairs):
    z = model['bias'] + sum(w * (x - m) / s for x, m, s, w in zip(dense, model['mean'], model['scale'], model['weights']))
    return z + model['pair_scale'] * sum(model['pairs'].get(k, 0.0) for k in pairs)


def chosen(model, record):
    """Best candidate of each space: (z, label) for the text and (z, label) for the instructions (None when there are none)."""
    out = [None, None]
    for dense, pairs, label, space in record['candidates']:
        z = z_of(model, dense, pairs)
        if out[space] is None or z > out[space][0]:
            out[space] = (z, label)
    return out


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
    bot.history_features = '--sin-historial' not in sys.argv
    bot.follow_instructions = '--sin-instrucciones' not in sys.argv
    records = extract(bot, folders, shuffle_pairs='--barajar-pares' in sys.argv, seed=seed)
    t_extract = time.process_time() - t0
    cross = []
    for fold in range(FOLDS):
        train = [r for r in records if r['group'] != fold]
        model = fit(train, use_pairs, seed)
        cross += [(chosen(model, r), r['answerable']) for r in records if r['group'] == fold]
    final = fit(records, use_pairs, seed)
    final['calibration'] = isotonic([(best[0][0], best[0][1]) for best, _ in cross if best[0] is not None])
    if any(best[1] is not None for best, _ in cross):
        final['calibration_instructions'] = isotonic([(best[1][0], best[1][1]) for best, _ in cross if best[1] is not None])

    def rate_of(curve, z):
        rate = curve[0][1]
        for low, block_rate, _ in curve:
            if z >= low:
                rate = block_rate
        return rate

    def best_rate(best):
        rates = [rate_of(final['calibration'] if k == 0 else final.get('calibration_instructions') or final['calibration'], b[0])
                 for k, b in enumerate(best) if b is not None]
        return max(rates, default=0.0)
    # Umbral de cita: el menor cuya tasa de citas sobre lo no respondible, medida con puntajes cruzados, no supera la de la
    # confianza anterior (0,4) en los mismos turnos.
    silent = [r for r in records if not r['answerable']]
    budget = sum(r['b0_cites'] for r in silent) / max(1, len(silent))
    scores = [best_rate(best) for best, answerable in cross if not answerable]
    threshold = 1.0
    for candidate in sorted({best_rate(best) for best, _ in cross}):
        if sum(x >= candidate for x in scores) / max(1, len(scores)) <= budget:
            threshold = candidate
            break
    final['cite_from'] = round(threshold, 4)
    final['cite_budget'] = round(budget, 4)
    answerable_cross = [(best_rate(best), max((b[1] for b in best if b is not None), default=0)) for best, answerable in cross if answerable]
    top1 = sum(label for _, label in answerable_cross) / max(1, len(answerable_cross))
    final['source'] = {'folders': [Path(f).name for f in folders], 'turns': len(records),
                       'candidates': sum(len(r['candidates']) for r in records), 'pairs': len(final['pairs']),
                       'use_pairs': use_pairs, 'shuffled_pairs': '--barajar-pares' in sys.argv, 'seed': seed}
    final['source']['pairs'] = len(final['pairs'])
    final['pairs'] = grouped(final['pairs'])
    bot.context_model['usefulness'] = final
    if FALLBACK_EXAMPLES and getattr(bot, 'follow_instructions', True):
        exit_model = fallback_model(FALLBACK_EXAMPLES, seed)
        if exit_model is not None:
            bot.context_model['fallback'] = exit_model
    bot.load_context('')
    bot.save(out)
    print(json.dumps({'cite_from': final['cite_from'], 'presupuesto_citas_sin_dato': final['cite_budget'],
                      'acierto_entre_respondibles_cruzado': round(top1, 4),
                      'fallback': {k: v for k, v in bot.context_model.get('fallback', {}).items() if k not in ('weights',)},
                      'turnos': len(records), 'pares': final['source']['pairs'], 'bloques': len(final['calibration']),
                      'cpu_extraer_s': round(t_extract, 1), 'cpu_total_s': round(time.process_time() - t0, 1),
                      'bytes': out.stat().st_size}))


if __name__ == '__main__':
    main()

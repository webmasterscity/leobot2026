"""G-60: cuentas de la confianza de la cita, en los bancos gastados (G-57, G-58, G-59 y desarrollo A–F).

python3 -m experiments.g60_calibrar_confianza BASE.json SALIDA.json

Cada turno se contesta con la mejor unidad (sin silencio ni cita).  Etiqueta automática: acción esperada abstenerse o
derivar → no útil; si no, útil si la unidad contiene todas las claves (coincide con el juez en el 95,3 % de 654 citas
juzgadas en G-58 y G-59).  Se guardan solo cuentas:
- Bayes ingenuo: por rasgo y valor, cuántos útiles y no útiles;
- calibración isotónica (ajuste que solo deja subir la utilidad con el puntaje) sobre puntajes cruzados: cada turno se
  puntúa con las cuentas de la otra mitad de los negocios (mitad por sha256 del banco y el negocio); tramos de ≥ 30;
- control «dos rasgos»: celdas de G-58 con utilidad ≥ 0,7 y ≥ 5 casos, contadas en los mismos turnos.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, contains, plain
from leobot import Bot
from leobot.context import CITE_FROM

BANKS = (Path('results_v3/kiosco/congelado'), Path('results_v3/kiosco/congelado_g58'),
         Path('results_v3/kiosco/congelado_g59'), Path('results_v3/kiosco/desarrollo'))
MIN_BLOCK = 30
MIN_CELL = 5


def rows_of(bot: Bot) -> list[dict]:
    bot.calibrated, bot.closest = False, False
    rows = []
    for bank in BANKS:
        for name, text, instructions, conversations in businesses(sorted(p for p in bank.iterdir() if p.is_dir())):
            bot.load_context(text, instructions)
            half = int(hashlib.sha256(f'{bank.name}/{name}'.encode()).hexdigest(), 16) % 2
            for conversation in conversations:
                for turn in conversation:
                    action = turn.get('accion', 'responder')
                    if action == 'charla':
                        continue
                    reply = bot.answer(turn['cliente'])
                    if reply['status'] != 'answered':
                        continue
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    if action in ('abstenerse', 'derivar'):
                        useful = 0
                    elif not keys:
                        continue
                    else:
                        useful = int(all(contains(reply['text'], k) for k in keys))
                    _, text_part = bot._question_part(turn['cliente'])
                    ranked = bot._rank(bot.context_terms(text_part), text_part)
                    rows.append({'half': half, 'y': useful, 'f': ranked['features'], 'cell': ranked['cell']})
    return rows


def naive_bayes(rows) -> dict:
    n1 = sum(r['y'] for r in rows)
    counts, values = {}, {}
    for r in rows:
        for name, value in r['f'].items():
            counts.setdefault(name, {}).setdefault(value, [0, 0])[r['y']] += 1
    for name in counts:
        counts[name] = dict(sorted(counts[name].items()))
        values[name] = len(counts[name])
    return {'prior': [len(rows) - n1, n1], 'counts': dict(sorted(counts.items())), 'values': dict(sorted(values.items()))}


def score(model, features) -> float:
    n0, n1 = model['prior']
    s = math.log((n1 + 1) / (n0 + 1))
    for name, counts in model['counts'].items():
        c0, c1 = counts.get(features.get(name), (0, 0))
        k = model['values'][name] + 1
        s += math.log((c1 + 1) / (n1 + k)) - math.log((c0 + 1) / (n0 + k))
    return s


def isotonic(points) -> list[list]:
    """Pool adjacent violators over (score, useful), then merge blocks under MIN_BLOCK cases."""
    blocks = []
    for s, y in sorted(points):
        blocks.append([s, y, 1])
        while len(blocks) > 1 and blocks[-2][1] * blocks[-1][2] >= blocks[-1][1] * blocks[-2][2]:
            _, y2, n2 = blocks.pop()
            blocks[-1][1] += y2
            blocks[-1][2] += n2
    while len(blocks) > 1 and min(b[2] for b in blocks) < MIN_BLOCK:
        k = min(range(len(blocks)), key=lambda i: (blocks[i][2], i))
        j = k - 1 if k == len(blocks) - 1 or (k > 0 and blocks[k - 1][2] <= blocks[k + 1][2]) else k + 1
        lo, hi = min(j, k), max(j, k)
        blocks[lo:hi + 1] = [[blocks[lo][0], blocks[lo][1] + blocks[hi][1], blocks[lo][2] + blocks[hi][2]]]
    return [[round(b[0], 6), round(b[1] / b[2], 4), b[2]] for b in blocks]


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = rows_of(Bot.load(base))
    crossed = []
    for half in (0, 1):
        model = naive_bayes([r for r in rows if r['half'] != half])
        crossed += [(score(model, r['f']), r['y']) for r in rows if r['half'] == half]
    confidence = naive_bayes(rows)
    confidence['calibration'] = isotonic(crossed)
    confidence['cite_from'] = CITE_FROM
    confidence['rows'] = len(rows)
    cells = {}
    for r in rows:
        row = cells.setdefault(r['cell'], [0, 0])
        row[0] += 1
        row[1] += r['y']
    bot = Bot.load(base)
    model = bot.context_model
    model['confidence'] = confidence
    model['closest_cells'] = {k: cells[k] for k in sorted(cells)}
    model['closest'] = sorted(c for c, (n, ok) in cells.items() if n >= MIN_CELL and ok >= CITE_FROM * n)
    model.setdefault('source', {})['confidence'] = {'banks': [str(b) for b in BANKS], 'labels': 'claves',
                                                    'halves': 'sha256(banco/negocio) % 2', 'min_block': MIN_BLOCK}
    bot.save(out)
    cited = [(s, y) for s, y in crossed
             if next((b[1] for b in reversed(confidence['calibration']) if s >= b[0]), confidence['calibration'][0][1])
             >= CITE_FROM]
    print(json.dumps({'turnos': len(rows), 'utiles': sum(r['y'] for r in rows),
                      'tramos': [b[1:] for b in confidence['calibration']],
                      'cruzado_citas': len(cited), 'cruzado_utiles': sum(y for _, y in cited),
                      'celdas_dos_rasgos': model['closest']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

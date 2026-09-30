"""G-112: modelo de utilidad G-103 (sin pares) con umbral de cita que iguala TODAS las citas malas de la línea base.

python3 -m experiments.g112_educar BASE.json SALIDA.json CARPETA... [--semilla N]

Igual que `g103_educar --sin-pares`, salvo la regla del umbral de cita: el menor umbral cuyas citas malas (respondibles con la unidad
equivocada + sin respuesta), medidas con puntajes cruzados por negocio en los turnos de enseñanza, no superan las citas malas de la
línea base B0 (confianza de siete rasgos a 0,4) en los mismos turnos.  G-103 igualaba solo las citas sin dato.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('PAIR_SUPPORT', '3')
os.environ.setdefault('PAIR_KEEP', '0.03')
os.environ.setdefault('C_REG', '0.1')
os.environ.setdefault('EPOCHS', '25')

import experiments.g103_educar as g103  # noqa: E402
from leobot import Bot  # noqa: E402

_one_turn = g103.one_turn


def one_turn(bot, turn, group, history, shuffle_pairs, rng):
    record = _one_turn(bot, turn, group, history, shuffle_pairs, rng)
    if record is not None:
        # B0's choice is right when its unit holds every key (same label as the candidates).
        bot.soft_prefix = False
        keys = [k for k in turn.get('claves') or [] if g103.plain(k)]
        _, question = bot._question_part(turn['cliente'])
        old = bot._rank(bot.context_terms(question), question)
        bot.soft_prefix = True
        record['b0_good'] = bool(keys and old and old.get('unit') is not None
                                 and g103.contains(bot.context_units[old['unit']]['text'], keys))
    return record


g103.one_turn = one_turn


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    seed = int(args.pop()) if '--semilla' in sys.argv else 0
    base, out, folders = Path(args[0]), Path(args[1]), args[2:]
    t0 = time.process_time()
    bot = Bot.load(base)
    bot.candidate_model = False
    records = g103.extract(bot, folders)
    cross = []
    for fold in range(g103.FOLDS):
        model = g103.fit([r for r in records if r['group'] != fold], False, seed)
        cross += [(g103.chosen(model, r)[0], r) for r in records if r['group'] == fold]
    final = g103.fit(records, False, seed)
    final['calibration'] = g103.isotonic([(best[0], best[1]) for best, _ in cross if best is not None])

    def rate(z):
        value = final['calibration'][0][1]
        for low, block, _ in final['calibration']:
            if z >= low:
                value = block
        return value
    scored = [(rate(best[0]), bool(best[1]) and r['answerable']) for best, r in cross if best is not None]
    budget = sum(r['b0_cites'] and not r['b0_good'] for r in records)
    threshold = 1.0
    for candidate in sorted({s for s, _ in scored}):
        if sum(s >= candidate and not good for s, good in scored) <= budget:
            threshold = candidate
            break
    final['cite_from'] = round(threshold, 4)
    final['cite_budget_bad'] = budget
    final['source'] = {'folders': [Path(f).name for f in folders], 'turns': len(records), 'pairs': 0, 'use_pairs': False,
                       'seed': seed, 'rule': 'G-112: citas malas totales <= B0'}
    final['pairs'] = {}
    bot.context_model['usefulness'] = final
    bot.load_context('')
    bot.save(out)
    useful = sum(s >= threshold and good for s, good in scored)
    b0_useful = sum(r['b0_cites'] and r['b0_good'] for r in records)
    print(json.dumps({'cite_from': final['cite_from'], 'malas_b0': budget, 'utiles_b0': b0_useful,
                      'utiles_modelo_cruzado': useful, 'malas_modelo_cruzado': sum(s >= threshold and not g for s, g in scored),
                      'cpu_s': round(time.process_time() - t0, 1)}))


if __name__ == '__main__':
    main()

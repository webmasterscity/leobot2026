"""G-115b: δ' fuera de pliegue al enseñar y calibrar el modelo de utilidad G-112 (solo datos; el motor no cambia).

python3 -m experiments.g115b_educar BASE.json SALIDA.json [--semilla N]

Ver prereg/G-115b-delta-fuera-de-pliegue.md.  Los 216 negocios de enseñanza se reparten en los 5 grupos de G-103; los registros de
los negocios del grupo f se extraen con una base cuyo δ' se contó sin ellos.  Con esos registros: modelos cruzados por grupo, modelo
final, calibración isotónica y umbral de cita cuyas citas malas no superan las de B0 con el δ original.  La base guardada lleva el δ'
contado con los 216 negocios.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
from pathlib import Path

import experiments.g112_educar  # noqa: F401  (instala el registro de B0 de G-112 en g103.one_turn)
import experiments.g103_educar as g103
import experiments.g115_delta_documento as g115
from leobot import Bot

_businesses = g103.businesses


def group_of(folder, name):
    return int(hashlib.sha256(f'{Path(folder).name}/{name}'.encode()).hexdigest(), 16) % g103.FOLDS


def only(keep):
    """`businesses` limited to the teaching businesses whose group passes `keep`."""
    def filtered(folders):
        for folder in folders:
            for item in _businesses([folder]):
                if keep(group_of(folder, item[0])):
                    yield item
    return filtered


def with_delta(bot, old, folders, keep):
    g115.businesses = only(keep)
    n, own, other, tags, turns = g115.count(bot, folders)
    g115.businesses = _businesses
    delta, rare_delta, _ = g115.learn(n, own, other, tags)
    merged = dict(old['delta'])
    merged.update(delta)
    bot.context_model['delta'] = merged
    bot.context_model['rare_delta'] = rare_delta
    return turns


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    seed = int(args.pop()) if '--semilla' in sys.argv else 0
    base, out = Path(args[0]), Path(args[1])
    folders = g115.teaching_folders()
    t0 = time.process_time()
    bot = Bot.load(base)
    bot.candidate_model = False
    original = copy.deepcopy({'delta': bot.context_model['delta'], 'rare_delta': bot.context_model['rare_delta']})
    # B0's budget with the original δ.
    b0 = g103.extract(bot, folders)
    budget = sum(r['b0_cites'] and not r['b0_good'] for r in b0)
    b0_useful = sum(r['b0_cites'] and r['b0_good'] for r in b0)
    del b0
    records = []
    for fold in range(g103.FOLDS):
        with_delta(bot, original, folders, lambda g, f=fold: g != f)
        g103.businesses = only(lambda g, f=fold: g == f)
        records += [r for r in g103.extract(bot, folders) if r['group'] == fold]
        g103.businesses = _businesses
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
    threshold = 1.0
    for candidate in sorted({s for s, _ in scored}):
        if sum(s >= candidate and not good for s, good in scored) <= budget:
            threshold = candidate
            break
    final['cite_from'] = round(threshold, 4)
    final['cite_budget_bad'] = budget
    final['source'] = {'folders': [Path(f).name for f in folders], 'turns': len(records), 'pairs': 0, 'use_pairs': False,
                       'seed': seed, 'rule': 'G-115b: delta fuera de pliegue; citas malas totales <= B0 con delta original'}
    final['pairs'] = {}
    # The saved base carries δ' counted on all 216 businesses.
    turns = with_delta(bot, original, folders, lambda g: True)
    bot.context_model['usefulness'] = final
    bot.context_model.setdefault('source', {})['g115b'] = {'turnos_delta': turns, 'fuera_de_pliegue': True}
    bot.load_context('')
    bot.save(out)
    print(json.dumps({'cite_from': final['cite_from'], 'malas_b0': budget, 'utiles_b0': b0_useful,
                      'utiles_modelo_cruzado': sum(s >= threshold and g for s, g in scored),
                      'malas_modelo_cruzado': sum(s >= threshold and not g for s, g in scored),
                      'registros': len(records), 'cpu_s': round(time.process_time() - t0, 1)}))


if __name__ == '__main__':
    main()

"""Comprobación posterior a auditoría: la API pública coincide con el conteo.

No reenseña, ajusta, selecciona ni promueve modelos. Usa solo tablas congeladas.
timeout 120s python3 -m experiments.g68_g70_respuestas_reales BASE SALIDA
"""
import copy
import json
from pathlib import Path
import sys
import time

from leobot import Bot
from experiments.g57_kiosco import businesses, contains, plain
from experiments.g68_confianza import DEV, predict, calibrated
from experiments.g70_puente_condicionado import install


def measure(bot):
    core = useful = absent = without_data = quotes = 0
    times = []
    for bank in DEV:
        root = Path('results_v3/kiosco')/bank
        for _, text, instructions, conversations in businesses(sorted(p for p in root.iterdir() if p.is_dir())):
            bot.load_context(text, instructions)
            for conv in conversations:
                history = []
                for turn in conv:
                    t = time.perf_counter()
                    reply = bot.answer(turn['cliente'], history)
                    times.append(1000*(time.perf_counter()-t))
                    history += [turn['cliente'], reply['text']]
                    action = turn.get('accion', 'responder')
                    keys = [k for k in turn.get('claves', []) or [] if plain(k)]
                    if action == 'charla' or reply['status'] == 'phatic' or (
                            action not in ('abstenerse', 'derivar') and not keys):
                        continue
                    said = reply['status'] in ('answered', 'closest')
                    quotes += said
                    if action in ('abstenerse', 'derivar'):
                        absent += 1
                        without_data += said
                    if action == 'responder' and turn.get('tipo') in ('directa', 'si_no'):
                        core += 1
                        useful += said and all(contains(reply['text'], key) for key in keys)
    times.sort()
    return {'core': core, 'useful_core': useful, 'quotes': quotes, 'absent_n': absent,
            'quotes_without_data': without_data, 'p50_ms': times[len(times)//2],
            'p95_ms': times[int(.95*len(times))], 'max_ms': max(times)}


def main():
    base, output = map(Path, sys.argv[1:3])
    bot = Bot.load(base)
    original = copy.deepcopy(bot.context_model)
    original_usefulness = bot._usefulness
    trees = json.loads(Path('results_v3/g68_modelos_experimentales.json').read_text())
    bridges = json.loads(Path('.leobot-data/g69_modelos_experimentales.json').read_text())
    pairs = json.loads(Path('.leobot-data/g70_modelo_experimental.json').read_text())
    references = {n: json.loads(Path(f'results_v3/{n}_desarrollo.json').read_text()) for n in ('g68', 'g69', 'g70')}
    results = {}
    for name in ('baseline', 'forest_0', 'forest_1', 'forest_2', 'competitive', 'phrases'):
        bot.context_model = copy.deepcopy(original)
        bot._usefulness = original_usefulness
        restore = lambda: None
        reference = references['g68']['baseline']
        if name in trees:
            model = trees[name]
            bot._usefulness = lambda f: calibrated(model['calibration'], predict(model['tree'], f))
            reference = references['g68']['candidates'][name]
        elif name in bridges:
            bot.context_model.update(bridges[name])
            reference = references['g69']['candidates'][name]
        elif name == 'phrases':
            bot.context_model['confidence'] = pairs['confidence']
            restore = install(bot, {tuple(q.split('\x1f')): row for q, row in pairs['phrase_bridge'].items()})
            reference = references['g70']['candidate']
        result = measure(bot)
        restore()
        result['matches_reported_counts'] = all(result[k] == reference[k] for k in (
            'core', 'useful_core', 'quotes', 'absent_n', 'quotes_without_data'))
        if not result['matches_reported_counts']:
            raise AssertionError((name, result, reference))
        results[name] = result
        print(name, json.dumps(result), flush=True)
    output.write_text(json.dumps({'scope': 'API pública real con candidatos externos; no promoción ni reserva nueva.',
                                  'results': results}, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()

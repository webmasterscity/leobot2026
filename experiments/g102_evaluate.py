"""G102 constructors on the unchanged common evaluator; no fitting on evaluation."""
import time
BOOT = time.process_time()
import argparse
import hashlib
import json
import resource
from pathlib import Path
from leobot import Bot
from experiments import g97_neural, g97_evaluate
from experiments.g98_route import EvidenceRoute
from experiments.g99_interaction import InteractionRoute
from experiments.g102_context import ContextRoute, ROOT, OUT, NAMES
from experiments.g57_kiosco import contains
from experiments.g97_backups import ABSTAINED

MODES = ('baseline', 'localized', 'lexical_40') + tuple(n+'_'+t for n in NAMES for t in ('40', '90'))
LOADS = []


def factory(bot, name):
    start = time.perf_counter()
    if name == 'localized':
        route = EvidenceRoute(bot, 'localized', root=ROOT/'.leobot-data/g98')
    elif name == 'lexical_40':
        route = InteractionRoute(bot, 'lexical', .4)
    else:
        n, threshold = name.rsplit('_', 1)
        route = ContextRoute(bot, n, float(threshold)/100)
    LOADS.append({'mode': name, 'ms': (time.perf_counter()-start)*1000})
    return route


def raw_choices(items):
    bot = Bot.load(ROOT/'.leobot-data/base_kiosco.json')
    routes = {n: ContextRoute(bot, n) for n in NAMES}
    counts = {n: {'answerable': 0, 'correct_raw': 0, 'absent': 0,
                  'null_on_absent': 0, 'null_on_answerable': 0} for n in NAMES}
    for b in items:
        bot.load_context(b['text'], b.get('instructions', ''))
        for route in routes.values(): route.prepare()
        for conv in b['conversations']:
            history = []
            for t in conv:
                reply = bot.answer(t['cliente'], history)
                if reply['status'] in ABSTAINED:
                    answerable = t.get('accion') == 'responder' and t.get('claves')
                    absent = t.get('accion') in ('abstenerse', 'derivar')
                    if answerable or absent:
                        for n, route in routes.items():
                            raw = route.raw(t['cliente'], history); c = counts[n]
                            if answerable:
                                c['answerable'] += 1
                                c['correct_raw'] += bool(raw and all(contains(bot.context_units[raw['index']]['text'], k) for k in t['claves']))
                                c['null_on_answerable'] += bool(raw and raw['null_selected'])
                            else:
                                c['absent'] += 1
                                c['null_on_absent'] += bool(raw and raw['null_selected'])
                history += [t['cliente'], reply['text']]
    return counts


def run(items, modes):
    LOADS.clear()
    meta = json.loads((OUT/'models.json').read_text())
    for n, info in meta['models'].items():
        assert hashlib.sha256((OUT/f'{n}.npz').read_bytes()).hexdigest() == info['sha256']
    for path, digest in meta['source_sha256'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest
    constructor = g97_neural.NeuralRoute
    g97_neural.NeuralRoute = factory
    try:
        result = g97_evaluate.run(items, modes)
    finally:
        g97_neural.NeuralRoute = constructor
    for name, report in result['reports'].items():
        report['answers_over_5ms'] = sum(r['ms'] >= 5 for r in result['rows'] if r['mode'] == name)
    result.update(experiment='G102', g102_metadata_sha256=hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest(),
                  raw_choices=raw_choices(items), loads=list(LOADS), cpu_s_with_imports_and_raw=time.process_time()-BOOT,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if result['cpu_s_with_imports_and_raw'] > 150: raise TimeoutError('G102 evaluation CPU budget per process')
    if result['peak_rss_kib'] > 3*1024**2: raise MemoryError('G102 evaluation RSS budget')
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dataset'); p.add_argument('--output', required=True)
    p.add_argument('--modes', default=','.join(MODES)); args = p.parse_args()
    path = Path(args.output)
    if path.exists(): raise FileExistsError(path)
    items = json.loads(Path(args.dataset).read_text())['businesses'] if args.dataset else g97_evaluate.common()
    path.write_text(json.dumps(run(items, tuple(args.modes.split(','))), ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__': main()

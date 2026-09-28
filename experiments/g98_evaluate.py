"""G98 uses the unchanged G97 public evaluator with explicit route injection."""
import time
BOOT = time.process_time()
import argparse
import hashlib
import json
from pathlib import Path
import resource
import numpy as np
from leobot import Bot
from experiments import g97_neural, g97_evaluate
from experiments.g97_backups import ABSTAINED
from experiments.g98_route import EvidenceRoute
from experiments.g57_kiosco import contains

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.leobot-data/g98'
MODES = ('baseline', 'original', 'more', 'localized', 'shuffled')


def raw_counts(items, names):
    bot = Bot.load(ROOT/'.leobot-data/base_kiosco.json')
    routes = {n: g97_neural.NeuralRoute(bot, 'trained') if n == 'original'
              else EvidenceRoute(bot, n, root=OUT) for n in names if n != 'baseline'}
    counts = {n: {'answerable':0, 'raw_correct':0, 'absent':0, 'null_on_absent':0,
                  'null_on_answerable':0} for n in routes}
    for b in items:
        bot.load_context(b['text'], b.get('instructions', ''))
        for r in routes.values(): r.prepare()
        for conv in b['conversations']:
            history = []
            for t in conv:
                reply = bot.answer(t['cliente'], history)
                history += [t['cliente'], reply['text']]
                if reply['status'] not in ABSTAINED: continue
                answerable = t.get('accion') == 'responder' and t.get('claves')
                absent = t.get('accion') in ('abstenerse', 'derivar')
                if not answerable and not absent: continue
                for n, route in routes.items():
                    raw = route.raw(t['cliente']); c = counts[n]
                    if answerable:
                        c['answerable'] += 1
                        c['raw_correct'] += bool(raw and all(contains(bot.context_units[raw['index']]['text'], k) for k in t['claves']))
                        c['null_on_answerable'] += bool(raw and raw.get('null_selected'))
                    else:
                        c['absent'] += 1
                        c['null_on_absent'] += bool(raw and raw.get('null_selected'))
    return counts


def run(items, modes):
    metadata = json.loads((OUT/'neural.json').read_text())
    for n, record in metadata['models'].items():
        assert hashlib.sha256((OUT/f'{n}.npz').read_bytes()).hexdigest() == record['sha256']
    original_class = g97_neural.NeuralRoute
    def factory(bot, name):
        return original_class(bot, 'trained') if name == 'original' else EvidenceRoute(bot, name, root=OUT)
    # Only the evaluator's constructor is substituted; metrics, history, status,
    # thresholds, answer copying and original evaluator source stay unchanged.
    g97_neural.NeuralRoute = factory
    try:
        result = g97_evaluate.run(items, modes)
    finally:
        g97_neural.NeuralRoute = original_class
    result['experiment'] = 'G98'
    result['g98_metadata_sha256'] = hashlib.sha256((OUT/'neural.json').read_bytes()).hexdigest()
    result['g98_source_sha256'] = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted((ROOT/'experiments').glob('g98_*.py'))}
    result['raw_choices'] = raw_counts(items, modes)
    result['cpu_s_with_imports_and_raw_diagnostic'] = time.process_time()-BOOT
    result['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if result['cpu_s_with_imports_and_raw_diagnostic'] > 180: raise TimeoutError('G98 evaluation CPU budget')
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--dataset'); p.add_argument('--output', required=True)
    p.add_argument('--modes', default=','.join(MODES)); a = p.parse_args()
    path = Path(a.output)
    if path.exists(): raise FileExistsError(path)
    items = json.loads(Path(a.dataset).read_text())['businesses'] if a.dataset else g97_evaluate.common()
    result = run(items, tuple(a.modes.split(',')))
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__': main()

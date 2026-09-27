"""G81: reuse G68's existing trees to select among PAR2's candidates."""
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from leobot import Bot
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g80_factorized_selection import G79_SHA


def fit_forest(turns, names):
    rows = [{'f': {n: f[n] for n in names}, 'y': y} for t in turns for f, y in t['rows']]
    forest = g68.fit(rows, seed=295825240)
    return {'forest': forest, 'bias': 0., 'weights': {}, 'rows': len(rows)}


def score_forest(model, features, names=None):
    return g68.predict(model['forest'], features)


class ForestBinding:
    def __init__(self, bot):
        self.bot, self.original = bot, bot._selection_score
        bot._selection_score = self.score

    def score(self, model, features):
        return score_forest(model, features) if 'forest' in model else self.original(model, features)

    def restore(self):
        self.bot._selection_score = self.original


def fingerprint():
    files = ('experiments/g81_interaction_selection.py', 'experiments/test_g81_interaction_selection.py',
             'experiments/g80_factorized_selection.py', 'experiments/g79_joint_selection.py',
             'experiments/g68_confianza.py', 'experiments/g75_relational_evidence.py',
             'prereg/G-81-interacciones-para-elegir.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G81 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        binding = ForestBinding(bot)
        result, error = public_measure(bot), None
        binding.restore()
        reference.restore()
    except Exception as exc:
        result, error = None, repr(exc)
    return {'result': result, 'error': error, 'cpu_s': time.process_time()-start,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (805, 810))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g79_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G79_SHA
    old_models = json.loads(previous.read_text())['models']
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    components = Components()
    components.correct_calibration()
    reference = components.bind(bot)
    ns = components.learner
    native = {k: v for k, v in old_models['combined'].items() if k != 'selection'}
    bot.context_model = native
    turns = ns['training_turns'](bot)
    assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
    names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
    print(json.dumps({'stage': 'prepared', 'turns': len(turns), 'cpu_s': time.process_time()-cpu0}), flush=True)
    fits, cache, models = [], {}, {}
    def timed_fit(items, features):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G81 agotó enseñanza')
        start = time.process_time()
        learned = fit_forest(items, features)
        record = {'rows': learned['rows'], 'features': len(features), 'cpu_s': time.process_time()-start}
        fits.append(record)
        (ROOT/'.leobot-data/g81_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': learned}))
        print(json.dumps({'stage': 'fit', **record}), flush=True)
        return learned
    ns['fit'], ns['score'] = timed_fit, score_forest
    model_path = ROOT/'.leobot-data/g81_models.json'
    for name, features, k, data, tag in (
            ('forest', names, 6, turns, 'full'),
            ('seven', ns['G60_FEATURES'], 6, turns, 'seven'),
            ('first', names, 1, turns, 'full'),
            ('shuffled', names, 6, ns['shuffled_labels'](turns), 'shuffled')):
        learned = ns['selection'](data, features, k, cache, tag)
        models[name] = {**native, 'selection': {**ns['table_of'](learned), 'forest': learned['forest']}}
        model_path.write_text(json.dumps({'models': models, 'fits': fits, 'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G81 agotó enseñanza')
    binding = ForestBinding(bot)
    results, raw, evaluation_cpu = {}, {}, 0.
    def measured(name, context, raw_selection=False):
        nonlocal evaluation_cpu
        start = time.process_time()
        bot.context_model = context
        result = public_measure(bot, deadline=start+200-evaluation_cpu)
        results[name] = result
        if raw_selection:
            rows = g68.collect(bot, g68.DEV)
            raw[name] = {'core': sum(t['core'] for t in rows),
                         'correct_first': sum(t['core'] and t['y'] for t in rows)}
        evaluation_cpu += time.process_time()-start
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result, 'raw': raw.get(name)}), flush=True)
        return result
    old_report = json.loads((ROOT/'results_v3/g79_joint_selection.json').read_text())['candidates']
    baseline = measured('baseline', original)
    assert baseline['response_sha256'] == old_report['baseline']['response_sha256']
    assert measured('g79', old_models['combined'])['response_sha256'] == old_report['combined']['response_sha256']
    for name, context in models.items():
        measured(name, context, raw_selection=True)
    start = time.process_time()
    bot.context_model = models['forest']
    bot.load_context('', '')
    candidate = ROOT/'.leobot-data/g81_candidate.json'
    bot.save(candidate)
    evaluation_cpu += time.process_time()-start
    binding.restore()
    restored = measured('restored_g79', old_models['combined'])
    reference.restore()
    disabled = measured('disabled', original)
    del binding, reference, bot, turns, cache, data
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g81_interaction_selection', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'g79_restored_exact': restored['response_sha256'] == results['g79']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['forest']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib'])
    primary = results['forest']
    gates = {'useful_gain': primary['useful_core'] >= 310,
             'absent': primary['quotes_without_data'] <= baseline['quotes_without_data'],
             'selection_gain': raw['forest']['correct_first'] >= 491,
             'ablations': all(primary['useful_core'] >= results[n]['useful_core']+17 for n in ('seven', 'first', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G81', 'scope': 'spent development; external prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g79_models_sha256': G79_SHA,
              'base_sha256': BASE_SHA, 'fits': fits, 'candidates': results, 'selection_without_abstention': raw,
              'controls': controls, 'restart': child, 'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
                       'peak_rss_kib': rss, 'parent_rss_during_child_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g81_interaction_selection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except (TimeoutError, AssertionError) as error:
            (ROOT/'results_v3/g81_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }, indent=2)+'\n')
            raise

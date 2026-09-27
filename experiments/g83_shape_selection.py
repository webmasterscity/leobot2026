"""G83: separately expose human-learned data forms to the existing selector."""
from collections import Counter
import gc
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from leobot import Bot
from leobot.context import PI_BINS, COVER_BINS, _bin
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g80_factorized_selection import G79_SHA
from experiments.g82_shape_coverage import source as shape_source, PAR1, PAR1_CONTEXT_SHA, PAR1_TABLE_SHA


def shape_tables():
    chunk_form, _ = shape_source()
    tables = json.loads((ROOT/'.leobot-data/g82/par1_tablas.json').read_text())['bridge_forms']
    signal = {q: [[s, w] for s, w in rows if s.startswith('#') and w > 0] for q, rows in tables.items()}
    signal = {q: rows for q, rows in signal.items() if rows}
    keys = sorted(signal)
    values = [signal[q] for q in keys]
    random.Random(1).shuffle(values)
    return chunk_form, signal, dict(zip(keys, values))


class ShapeBinding:
    def __init__(self, bot, chunk_form):
        self.bot, self.chunk_form = bot, chunk_form
        self.original, self.units, self.forms, self.frequency = bot._candidates, None, None, None
        bot._candidates = self.candidates

    def candidates(self, order, how, base, asked, terms, question, k):
        candidates = self.original(order, how, base, asked, terms, question, k)
        signal = self.bot.context_model.get('shape_evidence')
        if not signal:
            return candidates
        if self.units is not self.bot.context_units:
            self.units = self.bot.context_units
            self.forms = [{shape for shape in (self.chunk_form(c) for c in unit['text'].split()) if shape}
                          for unit in self.units]
            self.frequency = Counter(shape for forms in self.forms for shape in forms)
        requested = [signal[q] for q in dict.fromkeys(terms) if q in signal]
        for (_, i), features in zip(order, candidates):
            matches = [[(shape, strength) for shape, strength in row if shape in self.forms[i]] for row in requested]
            explained = sum(bool(row) for row in matches)
            present = [item for row in matches for item in row]
            strength = max((value for _, value in present), default=0.)
            selectivity = max((1-(self.frequency[shape]+.5)/(len(self.units)+1) for shape, _ in present), default=0.)
            features.update(shape_expected=str(min(len(requested), 2)), shape_explained=str(min(explained, 2)),
                            shape_unexplained=str(min(len(requested)-explained, 2)),
                            shape_strength=str(_bin(strength, PI_BINS)),
                            shape_selectivity=str(_bin(selectivity, COVER_BINS)))
        return candidates

    def restore(self):
        self.bot._candidates = self.original
        self.units = self.forms = self.frequency = None


def fingerprint():
    files = ('experiments/g83_shape_selection.py', 'experiments/test_g83_shape_selection.py',
             'experiments/g82_shape_coverage.py', 'experiments/g80_factorized_selection.py',
             'experiments/g79_joint_selection.py', 'experiments/g68_confianza.py',
             'experiments/g75_relational_evidence.py', 'prereg/G-83-formas-como-evidencia-del-selector.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G83 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        shapes = ShapeBinding(bot, shape_source()[0])
        result, error = public_measure(bot), None
        shapes.restore()
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
    chunk_form, signal, shuffled = shape_tables()
    shapes = ShapeBinding(bot, chunk_form)
    ns = components.learner
    native = {k: v for k, v in old_models['combined'].items() if k != 'selection'}
    original_fit, fits, models, education = ns['fit'], [], {}, {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G83 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        (ROOT/'.leobot-data/g83_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': fitted}))
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = ROOT/'.leobot-data/g83_models.json'
    for name, table in (('removed', {}), ('learned', signal), ('shuffled', shuffled)):
        context = {**native, 'shape_evidence': table}
        bot.context_model = context
        turns = ns['training_turns'](bot)
        assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        learned = ns['selection'](turns, names, 6)
        models[name] = {**context, 'selection': ns['table_of'](learned)}
        education[name] = {'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns), 'features': names}
        model_path.write_text(json.dumps({'models': models, 'education': education, 'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G83 agotó enseñanza')
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
    for name, context in models.items():
        measured(name, context, raw_selection=True)
        if name == 'removed':
            assert results[name]['response_sha256'] == old_report['combined']['response_sha256']
    start = time.process_time()
    bot.context_model = models['learned']
    bot.load_context('', '')
    candidate = ROOT/'.leobot-data/g83_candidate.json'
    bot.save(candidate)
    evaluation_cpu += time.process_time()-start
    shapes.restore()
    restored = measured('restored_g79', old_models['combined'])
    reference.restore()
    disabled = measured('disabled', original)
    del shapes, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g83_shape_selection', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'g79_restored_exact': restored['response_sha256'] == results['removed']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['learned']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib'])
    primary = results['learned']
    gates = {'useful_gain_retained': primary['useful_core'] >= 326,
             'absent': primary['quotes_without_data'] <= 73,
             'shuffled_gain': primary['useful_core'] >= results['shuffled']['useful_core']+17,
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G83', 'scope': 'spent development; external prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g79_models_sha256': G79_SHA,
              'par1_reference': PAR1, 'par1_context_sha256': PAR1_CONTEXT_SHA, 'par1_table_sha256': PAR1_TABLE_SHA,
              'base_sha256': BASE_SHA, 'education': education, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
                       'peak_rss_kib': rss, 'parent_rss_during_child_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g83_shape_selection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except (TimeoutError, AssertionError) as error:
            (ROOT/'results_v3/g83_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }, indent=2)+'\n')
            raise

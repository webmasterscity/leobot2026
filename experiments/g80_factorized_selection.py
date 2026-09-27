"""G80: conditional candidate choice and independently learned question eligibility.

External experiment only. Reuses the immutable PAR2 optimizer and scorer.
"""
from collections import Counter, defaultdict
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
from experiments.g57_kiosco import businesses, contains, plain
from experiments.g68_confianza import TRAIN, DEV, collect, isotonic
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES

G79_SHA = '3f17e19a3f1f4edeac3b16b00684cca45d4b04f593e3575ec582544ca6abf465'


def pool(candidates):
    """Order-invariant summary of the existing nonlexical candidate features."""
    result = {'n': str(len(candidates))}
    if not candidates:
        return result
    for name in sorted(candidates[0]):
        values = [f[name] for f in candidates]
        if all(v.isdecimal() for v in values):
            numbers = list(map(int, values))
            result['min:'+name], result['max:'+name] = str(min(numbers)), str(max(numbers))
        else:
            counts = Counter(values)
            result['mode:'+name] = min(counts, key=lambda v: (-counts[v], v))
            result['diversity:'+name] = str(min(len(counts), 2))
    return result


def training_turns(bot):
    turns = []
    for bank in TRAIN:
        folder = ROOT / 'results_v3/kiosco' / bank
        for name, text, instructions, conversations in businesses(sorted(p for p in folder.iterdir() if p.is_dir())):
            group = bank+'/'+name
            half = int(hashlib.sha256(group.encode()).hexdigest(), 16) % 2
            bot.load_context(text, instructions)
            for c, conversation in enumerate(conversations):
                for i, turn in enumerate(conversation):
                    action = turn.get('accion', 'responder')
                    if action == 'charla':
                        continue
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    eligible = int(action not in ('abstenerse', 'derivar'))
                    if eligible and not keys or bot._phatic(bot._question_part(turn['cliente'])[1]):
                        continue
                    rows = [(features, int(eligible and all(contains(bot.context_units[j]['text'], k) for k in keys)))
                            for j, features in bot.selection_candidates(turn['cliente'], 6)]
                    turns.append({'id': f'{group}/{c}/{i}', 'group': group, 'half': half,
                                  'eligible': eligible, 'rows': rows,
                                  'pooled': pool([f for f, _ in rows])})
    return turns


def educate(turns, ns):
    """OOF scores only see models taught on other businesses; labels remain distinct."""
    turns = [t for t in turns if t['rows']]
    candidate_names = sorted(turns[0]['rows'][0][0])
    query_names = sorted(turns[0]['pooled'])
    eligible = [t for t in turns if t['eligible']]
    by_group = defaultdict(list)
    for t in turns:
        by_group[t['group']].append(t)
    rng, shuffled = random.Random(1), []
    for group in sorted(by_group):
        items = by_group[group]
        labels = [t['eligible'] for t in items]
        rng.shuffle(labels)
        shuffled.extend({**t, 'eligible': y} for t, y in zip(items, labels))
    query_sets = {name: [{**t, 'rows': [(t['pooled'], t['eligible'])]} for t in items]
                  for name, items in (('learned', turns), ('shuffled', shuffled))}
    points = {'conditional': [], 'learned': [], 'shuffled': []}
    folds, cross_scores = [], []
    for half in (0, 1):
        taught = {t['group'] for t in turns if t['half'] != half}
        scored = {t['group'] for t in turns if t['half'] == half}
        assert not taught & scored
        folds.append({'half': half, 'taught_groups': sorted(taught), 'scored_groups': sorted(scored)})
        model = ns['fit']([t for t in eligible if t['half'] != half], candidate_names)
        for t in turns:
            if t['half'] != half:
                continue
            values = [ns['score'](model, f, candidate_names) for f, _ in t['rows']]
            best = max(range(len(values)), key=lambda i: (values[i], -i))
            y = t['rows'][best][1]
            if t['eligible']:
                points['conditional'].append((values[best], y))
            cross_scores.append({'id': t.get('id'), 'group': t['group'], 'half': half,
                                 'eligible': t['eligible'], 'chosen_correct': y,
                                 'candidate_score': values[best]})
        for name, query_turns in query_sets.items():
            model = ns['fit']([t for t in query_turns if t['half'] != half], query_names)
            for t in query_turns:
                if t['half'] == half:
                    value = ns['score'](model, t['pooled'], query_names)
                    points[name].append((value, t['eligible']))

    conditional = ns['fit'](eligible, candidate_names)
    conditional.update(k=6, cite_from=.4, calibration=isotonic(points['conditional']))
    selection = ns['table_of'](conditional)
    models = {}
    for name, query_turns in query_sets.items():
        model = ns['fit'](query_turns, query_names)
        model.update(bias=round(model['bias'], 6), mode='learned', calibration=isotonic(points[name]))
        models['factorized' if name == 'learned' else name] = {'selection': selection, 'eligibility': model}
    prior = len(eligible)/len(turns)
    models['prior'] = {'selection': selection, 'eligibility': {'mode': 'prior', 'prior': prior}}
    audit = {'turns': len(turns), 'eligible_turns': len(eligible), 'ineligible_turns': len(turns)-len(eligible),
             'eligible_without_correct_candidate': sum(not any(y for _, y in t['rows']) for t in eligible),
             'candidate_rows': sum(len(t['rows']) for t in turns),
             'conditional_rows': sum(len(t['rows']) for t in eligible),
             'candidate_features': candidate_names, 'query_features': query_names,
             'folds': folds, 'cross_scores': cross_scores, 'calibration_points': points,
             'prior': prior, 'shuffled_label_changes': sum(a['eligible'] != b['eligible']
                 for a, b in zip(sorted(turns, key=lambda t: (t['group'], t.get('id', ''))),
                                 sorted(shuffled, key=lambda t: (t['group'], t.get('id', '')))))}
    return models, audit


class GateBinding:
    """Capture features during the same ranking call; retain no previous query."""
    def __init__(self, bot):
        self.bot, self.captured = bot, None
        self.original_rank, self.original_candidates = bot._rank, bot._candidates
        bot._rank, bot._candidates = self.rank, self.candidates

    def candidates(self, *args, **kwargs):
        self.captured = self.original_candidates(*args, **kwargs)
        return self.captured

    def rank(self, *args, **kwargs):
        self.captured = None
        try:
            ranked = self.original_rank(*args, **kwargs)
            model = self.bot.context_model.get('eligibility')
            if ranked is None or model is None or not self.captured:
                return ranked
            if model['mode'] == 'prior':
                probability = model['prior']
            else:
                value = self.bot._selection_score(model, pool(self.captured))
                probability = self.bot._calibrated(model['calibration'], value)
            ranked['useful'] *= probability
            return ranked
        finally:
            self.captured = None

    def restore(self):
        self.bot._rank, self.bot._candidates = self.original_rank, self.original_candidates
        self.captured = None


def fingerprint():
    files = ('experiments/g80_factorized_selection.py', 'experiments/g79_joint_selection.py',
             'experiments/g68_confianza.py', 'experiments/g75_relational_evidence.py',
             'experiments/test_g80_factorized_selection.py', 'prereg/G-80-disponibilidad-y-acierto-separados.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G80 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        gate = GateBinding(bot)
        result, error = public_measure(bot), None
        gate.restore()
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
    ns = components.learner
    reference = components.bind(bot)
    native = {k: v for k, v in old_models['combined'].items() if k != 'selection'}
    bot.context_model = native
    turns = training_turns(bot)
    assert [{'half': t['half'], 'rows': t['rows']} for t in turns] == ns['training_turns'](bot)
    print(json.dumps({'stage': 'prepared', 'turns': len(turns), 'cpu_s': time.process_time()-cpu0}), flush=True)
    original_fit, fits = ns['fit'], []
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G80 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        cost = {'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                'features': len(fitted['weights']), 'iterations': fitted['iterations']}
        fits.append(cost)
        (ROOT/'.leobot-data/g80_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': fitted}))
        print(json.dumps({'stage': 'fit', **cost}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    learned, education = educate(turns, ns)
    models = {name: {**native, **tables} for name, tables in learned.items()}
    model_path = ROOT/'.leobot-data/g80_models.json'
    model_path.write_text(json.dumps({'models': models, 'education': education, 'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G80 agotó enseñanza')
    results, raw, evaluation_cpu = {}, {}, 0.
    def measured(name, context, raw_selection=False):
        nonlocal evaluation_cpu
        start = time.process_time()
        bot.context_model = context
        result = public_measure(bot, deadline=start+200-evaluation_cpu)
        results[name] = result
        if raw_selection:
            rows = collect(bot, DEV)
            raw[name] = {'core': sum(t['core'] for t in rows),
                         'correct_first': sum(t['core'] and t['y'] for t in rows)}
        evaluation_cpu += time.process_time()-start
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result, 'raw': raw.get(name)}), flush=True)
        return result
    old_report = json.loads((ROOT/'results_v3/g79_joint_selection.json').read_text())['candidates']
    baseline = measured('baseline', original)
    assert baseline['response_sha256'] == old_report['baseline']['response_sha256']
    for name in ('selector', 'combined'):
        assert measured(name, old_models[name])['response_sha256'] == old_report[name]['response_sha256']
    gate = GateBinding(bot)
    for name in ('factorized', 'prior', 'shuffled'):
        measured(name, models[name], raw_selection=name == 'factorized')
    start = time.process_time()
    bot.context_model = models['factorized']
    bot.load_context('', '')
    candidate = ROOT/'.leobot-data/g80_candidate.json'
    bot.save(candidate)
    evaluation_cpu += time.process_time()-start
    gate.restore()
    restored = measured('restored_g79', old_models['combined'])
    reference.restore()
    disabled = measured('disabled', original)
    del gate, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g80_factorized_selection', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'g79_restored_exact': restored['response_sha256'] == results['combined']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['factorized']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib'])
    primary = results['factorized']
    gates = {'useful_gain_retained': primary['useful_core'] >= 310,
             'absent': primary['quotes_without_data'] <= baseline['quotes_without_data'],
             'availability_contribution': all(primary['quotes_without_data'] <= results[n]['quotes_without_data']-10
                 and primary['useful_core'] >= results[n]['useful_core']-16 for n in ('prior', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G80', 'scope': 'spent development; external prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g79_models_sha256': G79_SHA,
              'base_sha256': BASE_SHA, 'education': {k: v for k, v in education.items() if k not in ('cross_scores', 'calibration_points')},
              'fits': fits, 'candidates': results, 'selection_without_abstention': raw,
              'controls': controls, 'restart': child, 'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
                       'peak_rss_kib': rss, 'parent_rss_during_child_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g80_factorized_selection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except (TimeoutError, AssertionError) as error:
            (ROOT/'results_v3/g80_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }, indent=2)+'\n')
            raise

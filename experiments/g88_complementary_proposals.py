"""G88: reuse learned alignment proposals with the frozen linear selector."""
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
from experiments import g65_correspondencias as g65
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g85_human_selection import DirectBinding, G84_SHA
from experiments.g87_proposal_coverage import proposed


def proposal_order(scored, alignment, units):
    initial = [i for _, i in scored['order'][:6]]
    pool = proposed(initial, alignment, units)
    original_scores = {i: score for score, i in scored['order']}
    return {**scored, 'order': [(original_scores.get(i, scored['base']), i) for i in pool]}


class ProposalBinding:
    def __init__(self, bot, direct):
        self.bot, self.direct, self.original = bot, direct, bot._scored
        self.units = self.packet = self.shuffled = None
        self.cost = {'proposal_cpu_s': 0., 'calls': 0, 'permutation_preparation_cpu_s': 0.}
        bot._scored = self.scored

    def scored(self, terms, question=''):
        original = self.original(terms, question)
        packet = self.bot.context_model.get('proposal')
        if packet is None:
            return original
        start = time.process_time()
        if packet['mode'] == 'twelve':
            result = {**original, 'order': original['order'][:12]}
        else:
            if not self.direct.prepare():
                raise RuntimeError('G88: faltan asociaciones aprendidas')
            units = self.direct.prepared
            if packet['mode'] == 'shuffled':
                if self.units is not self.bot.context_units or self.packet is not packet:
                    prep = time.process_time()
                    permutation = packet['permutation']
                    self.shuffled = [[permutation[i] for i in row] for row in units]
                    self.units, self.packet = self.bot.context_units, packet
                    self.cost['permutation_preparation_cpu_s'] += time.process_time()-prep
                units = self.shuffled
            scores = g65.alignment_scores(self.direct.decoded[0][0], units, sorted(set(terms)))
            result = proposal_order(original, scores, self.bot.context_units)
        self.cost['proposal_cpu_s'] += time.process_time()-start
        self.cost['calls'] += 1
        return result

    def restore(self):
        self.bot._scored = self.original
        self.units = self.packet = self.shuffled = None


def fingerprint():
    files = ('experiments/g88_complementary_proposals.py', 'experiments/test_g88_complementary_proposals.py',
             'experiments/g87_proposal_coverage.py', 'experiments/g85_human_selection.py',
             'experiments/g84_indirect_alignment.py', 'experiments/g84b_compact_replay.py',
             'experiments/g65_correspondencias.py', 'experiments/g79_joint_selection.py',
             'experiments/g68_confianza.py', 'experiments/g75_relational_evidence.py',
             'prereg/G-88-seleccion-entre-propuestas-complementarias.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G88 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start, prep = time.process_time(), None
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        direct = DirectBinding(bot)
        binding = ProposalBinding(bot, direct)
        result, error = public_measure(bot), None
        prep = {'alignment': dict(direct.cost), 'proposal': dict(binding.cost)}
        binding.restore()
        direct.restore()
        reference.restore()
    except Exception as exc:
        result, error = None, repr(exc)
    return {'result': result, 'error': error, 'cpu_s': time.process_time()-start,
            'preparation_included': prep, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (845, 850))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g84_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G84_SHA
    fixed = json.loads(previous.read_text())['models']['direct']
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    components = Components()
    components.correct_calibration()
    reference = components.bind(bot)
    direct = DirectBinding(bot)
    binding = ProposalBinding(bot, direct)
    ns = components.learner
    native = {key: value for key, value in fixed.items() if key != 'selection'}
    permutation = list(range(len(native['alignment']['answers'])))
    random.Random(1).shuffle(permutation)
    packets = {'six': None, 'twelve': {'mode': 'twelve'}, 'union': {'mode': 'union'},
               'shuffled': {'mode': 'shuffled', 'permutation': permutation}}
    original_fit, fits, models, taught = ns['fit'], [], {}, {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G88 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        (ROOT/'.leobot-data/g88_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': fitted}))
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = ROOT/'.leobot-data/g88_models.json'
    for name, packet in packets.items():
        context = {**native, 'proposal': packet}
        bot.context_model = context
        ns['K'] = 6 if name == 'six' else 12
        start = time.process_time()
        turns = ns['training_turns'](bot)
        assert len(turns) == 3520
        if name == 'six':
            assert sum(len(t['rows']) for t in turns) == 20629
        prep_cost = time.process_time()-start
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        learned = ns['selection'](turns, names, ns['K'])
        models[name] = {**context, 'selection': ns['table_of'](learned)}
        taught[name] = {'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns),
                        'positive_rows': sum(y for t in turns for _, y in t['rows']),
                        'turns_with_positive': sum(any(y for _, y in t['rows']) for t in turns),
                        'features': names, 'preparation_cpu_s': prep_cost}
        model_path.write_text(json.dumps({'models': models, 'education': taught,
                                         'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G88 agotó enseñanza')
    teaching_prep = {'alignment': dict(direct.cost), 'proposal': dict(binding.cost)}
    results, raw, evaluation_cpu = {}, {}, 0.
    def measured(name, context, raw_selection=False):
        nonlocal evaluation_cpu
        start = time.process_time()
        bot.context_model = context
        result = public_measure(bot, deadline=start+240-evaluation_cpu)
        results[name] = result
        if raw_selection:
            rows = g68.collect(bot, g68.DEV)
            raw[name] = {'core': sum(r['core'] for r in rows),
                         'correct_first': sum(r['core'] and r['y'] for r in rows)}
        evaluation_cpu += time.process_time()-start
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result, 'raw': raw.get(name)}), flush=True)
        return result
    baseline = measured('baseline', original)
    previous_report = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())['candidates']
    assert baseline['response_sha256'] == previous_report['baseline']['response_sha256']
    for name, context in models.items():
        measured(name, context, True)
        if name == 'six':
            assert results[name]['response_sha256'] == previous_report['direct']['response_sha256']
    start = time.process_time()
    bot.context_model = models['union']
    bot.load_context('', '')
    readable, candidate = ROOT/'.leobot-data/g88_candidate_readable.json', ROOT/'.leobot-data/g88_candidate.json'
    bot.save(readable)
    evaluation_cpu += time.process_time()-start
    all_prep = {'alignment': dict(direct.cost), 'proposal': dict(binding.cost)}
    binding.restore()
    direct.restore()
    reference.restore()
    disabled = measured('disabled', original)
    del binding, direct, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    compact_run = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(readable), str(candidate)],
                                 cwd=ROOT, capture_output=True, text=True, check=True, timeout=45)
    compact = json.loads(compact_run.stdout)
    process = subprocess.run([sys.executable, '-m', 'experiments.g88_complementary_proposals', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, check=True, timeout=60)
    child = json.loads(process.stdout)
    child_cpu = compact['cpu_s']+child['cpu_s']
    evaluation_cpu += time.process_time()-start+child_cpu
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'six_exact': results['six']['response_sha256'] == previous_report['direct']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['union']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(compact['peak_rss_kib'], child['peak_rss_kib']))
    primary = results['union']
    total_cpu = time.process_time()-cpu0+child_cpu
    gates = {'useful_gain': primary['useful_core'] >= 344, 'absent': primary['quotes_without_data'] <= 73,
             'selection_gain': raw['union']['correct_first'] >= 499,
             'proposal_gain': all(primary['useful_core'] >= results[m]['useful_core']+17
                                  for m in ('six', 'twelve', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 240 and total_cpu <= 840
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1100}
    assert fingerprint() == hashes
    report = {'experiment': 'G88', 'scope': 'spent development; external prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes,
              'g84_models_sha256': G84_SHA, 'base_sha256': BASE_SHA,
              'education': taught, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls,
              'compaction': compact, 'restart': child, 'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'teaching_preparation_included': teaching_prep,
                       'all_preparation_included': all_prep, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': total_cpu, 'wall_s': time.monotonic()-wall0,
                       'peak_rss_kib': rss, 'parent_rss_during_children_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g88_complementary_proposals.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g88_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall,
                'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None),
            }, indent=2)+'\n')
            raise

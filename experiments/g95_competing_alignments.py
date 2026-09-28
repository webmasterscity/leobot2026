"""G95: learned lexical edges competing for answer terms; no answer rule."""
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from leobot import Bot
from leobot.context import COVER_BINS, _bin
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g85_human_selection import DirectBinding, G84_SHA


def maximum_assignment(matrix):
    """Rectangular Hungarian assignment with free unmatched rows and columns."""
    rows = [row for row in matrix if any(value > 0 for value in row)]
    if not rows:
        return 0.
    active = [j for j in range(len(rows[0])) if any(row[j] > 0 for row in rows)]
    n = len(rows)
    weights = [[row[j] for j in active]+[0.]*n for row in rows]
    width = len(weights[0])
    u, v, owner, way = [0.]*(n+1), [0.]*(width+1), [0]*(width+1), [0]*(width+1)
    for i in range(1, n+1):
        owner[0], column = i, 0
        distance, used = [float('inf')]*(width+1), [False]*(width+1)
        while True:
            used[column] = True
            row, delta, next_column = owner[column], float('inf'), 0
            for j in range(1, width+1):
                if used[j]:
                    continue
                cost = -weights[row-1][j-1]-u[row]-v[j]
                if cost < distance[j]:
                    distance[j], way[j] = cost, column
                if distance[j] < delta:
                    delta, next_column = distance[j], j
            for j in range(width+1):
                if used[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    distance[j] -= delta
            column = next_column
            if owner[column] == 0:
                break
        while column:
            previous = way[column]
            owner[column] = owner[previous]
            column = previous
    return sum(weights[owner[j]-1][j-1] for j in range(1, width+1) if owner[j])


class CompetitionBinding:
    def __init__(self, bot, alignment):
        self.bot, self.alignment = bot, alignment
        self.original_candidates, self.original_load = bot._candidates, bot.load_context
        self.packet = self.source = self.columns = None
        self.cost = {'decode_cpu_s': 0., 'feature_cpu_s': 0., 'calls': 0, 'matrices': 0,
                     'maximum_query_terms': 0, 'maximum_answer_terms': 0}
        bot._candidates, bot.load_context = self.candidates, self.load_context

    def prepare(self):
        packet = self.bot.context_model.get('competition')
        if not packet or not self.alignment.prepare():
            self.packet = self.source = self.columns = None
            return False
        if packet is not self.packet or self.source is not self.alignment.packet:
            start = time.process_time()
            columns = self.alignment.decoded[0][1]
            self.columns = list(columns)
            if packet['mode'] == 'shuffled':
                random.Random(packet['seed']).shuffle(self.columns)
            self.packet, self.source = packet, self.alignment.packet
            self.cost['decode_cpu_s'] += time.process_time()-start
        return True

    def load_context(self, *args, **kwargs):
        result = self.original_load(*args, **kwargs)
        self.prepare()
        return result

    def candidates(self, order, how, base, asked, terms, question, k):
        candidates = self.original_candidates(order, how, base, asked, terms, question, k)
        if not self.prepare():
            return candidates
        start = time.process_time()
        model = self.alignment.decoded[0][0]
        query = sorted(set(terms))
        ids = [model['qv'][(q,)] for q in query if (q,) in model['qv']]
        scores, losses = [], []
        for _, index in order[:len(candidates)]:
            answers = self.alignment.prepared[index]
            matrix = []
            for q in ids:
                background = model['background'][q]
                matrix.append([max(0., math.log(p/background)) if (p := self.columns[a].get(q, 0.)) > 0 else 0.
                               for a in answers])
            free = round(sum(max(row, default=0.) for row in matrix), 6)
            competitive = free if self.packet['mode'] == 'free' else round(maximum_assignment(matrix), 6)
            scores.append(competitive/max(1, len(ids)))
            losses.append((free-competitive)/free if free else 0.)
            self.cost['matrices'] += 1
            self.cost['maximum_query_terms'] = max(self.cost['maximum_query_terms'], len(ids))
            self.cost['maximum_answer_terms'] = max(self.cost['maximum_answer_terms'], len(answers))
        for i, features in enumerate(candidates):
            runner = max((score for j, score in enumerate(scores) if j != i), default=0.)
            features.update(assignment_score=str(_bin(scores[i], self.alignment.margins)),
                            assignment_margin=str(_bin(scores[i]-runner, self.alignment.margins)),
                            assignment_loss=str(_bin(losses[i], COVER_BINS)),
                            assignment_known=str(_bin(len(ids)/max(1, len(query)), COVER_BINS)))
        self.cost['feature_cpu_s'] += time.process_time()-start
        self.cost['calls'] += 1
        return candidates

    def restore(self):
        self.bot._candidates, self.bot.load_context = self.original_candidates, self.original_load
        self.packet = self.source = self.columns = None


def fingerprint():
    files = ('experiments/g95_competing_alignments.py', 'experiments/test_g95_competing_alignments.py',
             'experiments/g85_human_selection.py', 'experiments/g84_indirect_alignment.py',
             'experiments/g84b_compact_replay.py', 'experiments/g79_joint_selection.py',
             'experiments/g68_confianza.py', 'experiments/g75_relational_evidence.py',
             'prereg/G-95-competencia-entre-correspondencias.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G95 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    preparation = None
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        alignment = DirectBinding(bot)
        binding = CompetitionBinding(bot, alignment)
        result, error = public_measure(bot), None
        preparation = {'alignment': alignment.cost, 'competition': binding.cost}
        binding.restore()
        alignment.restore()
        reference.restore()
    except Exception as exc:
        result, error = None, repr(exc)
    return {'result': result, 'error': error, 'cpu_s': time.process_time()-start,
            'preparation_included': preparation, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (805, 810))
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
    alignment = DirectBinding(bot)
    binding = CompetitionBinding(bot, alignment)
    ns = components.learner
    native = {k: v for k, v in fixed.items() if k != 'selection'}
    original_fit, fits, models, education = ns['fit'], [], {}, {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G95 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    folder = ROOT/'.leobot-data/g95'
    folder.mkdir(exist_ok=True)
    model_path = folder/'models.json'
    for name in ('removed', 'free', 'assignment', 'shuffled'):
        context = dict(native)
        if name != 'removed':
            context['competition'] = {'mode': name, 'seed': 1}
        bot.context_model = context
        start = time.process_time()
        turns = ns['training_turns'](bot)
        assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        learned = ns['selection'](turns, names, 6)
        models[name] = {**context, 'selection': ns['table_of'](learned)}
        education[name] = {'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns),
                           'features': names, 'preparation_and_learning_cpu_s': time.process_time()-start}
        model_path.write_text(json.dumps({'models': models, 'education': education, 'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G95 agotó enseñanza')
    teaching_computations = dict(binding.cost)
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
    old_report = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())
    baseline = measured('baseline', original)
    assert baseline['response_sha256'] == old_report['candidates']['baseline']['response_sha256']
    for name, context in models.items():
        measured(name, context, raw_selection=True)
        if name == 'removed':
            assert results[name]['response_sha256'] == old_report['candidates']['direct']['response_sha256']
    start = time.process_time()
    bot.context_model = models['assignment']
    bot.load_context('', '')
    readable, candidate = folder/'candidate_readable.json', folder/'candidate.json'
    bot.save(readable)
    evaluation_cpu += time.process_time()-start
    preparation = {'alignment': dict(alignment.cost), 'competition': dict(binding.cost)}
    binding.restore()
    restored = measured('restored_direct', fixed)
    alignment.restore()
    reference.restore()
    disabled = measured('disabled', original)
    del binding, alignment, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(readable), str(candidate)],
                             cwd=ROOT, capture_output=True, text=True, timeout=40, check=True)
    compacted = json.loads(process.stdout)
    process = subprocess.run([sys.executable, '-m', 'experiments.g95_competing_alignments', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+compacted['cpu_s']+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'direct_exact': restored['response_sha256'] == results['removed']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['assignment']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(child['peak_rss_kib'], compacted['peak_rss_kib']))
    total_cpu = time.process_time()-cpu0+child['cpu_s']+compacted['cpu_s']
    primary = results['assignment']
    gates = {'useful_gain': primary['useful_core'] >= 368, 'absent': primary['quotes_without_data'] <= 73,
             'selection_gain': raw['assignment']['correct_first'] >= 491,
             'competition_gain': all(primary['useful_core'] >= results[n]['useful_core']+17 for n in ('free', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and total_cpu <= 800
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G95', 'scope': 'spent development; token competition as learned selection evidence only',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g84_models_sha256': G84_SHA,
              'base_sha256': BASE_SHA, 'education': education, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'compaction': compacted, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'teaching_computations_included': teaching_computations,
                       'preparation_included': preparation, 'total_cpu_s': total_cpu,
                       'wall_s': time.monotonic()-wall0, 'peak_rss_kib': rss,
                       'parent_rss_during_children_kib': parent_rss, 'models_bytes': model_path.stat().st_size,
                       'base_bytes': candidate.stat().st_size, 'previous_g84_cpu_s': old_report['cost']['total_cpu_s']}}
    (ROOT/'results_v3/g95_competing_alignments.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
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
            (ROOT/'results_v3/g95_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

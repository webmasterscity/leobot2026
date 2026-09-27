"""G84: bounded, non-neural composition of learned alignment distributions."""
from collections import Counter
import gc
import hashlib
import heapq
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
from experiments import g65_correspondencias as g65
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g80_factorized_selection import G79_SHA

NEIGHBORS = 8


def normalize(values):
    selected = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:NEIGHBORS]
    total = sum(p for _, p in selected)
    return [[i, round(p/total, 6)] for i, p in sorted(selected) if p > 0 and round(p/total, 6) > 0] if total else []


def compile_direct(model):
    questions, answers = [None]*len(model['qv']), [None]*len(model['av'])
    for (word,), i in model['qv'].items():
        questions[i] = word
    for (word,), i in model['av'].items():
        answers[i] = word
    heaps, total = [[] for _ in answers], [0.]*len(answers)
    for q, row in enumerate(model['prob']):
        for a, p in row.items():
            total[a] += p
            item = (p, -q, q)
            if len(heaps[a]) < NEIGHBORS:
                heapq.heappush(heaps[a], item)
            else:
                heapq.heappushpop(heaps[a], item)
    one = [normalize({q: p for p, _, q in row}) for row in heaps]
    retained = [sum(p for p, _, _ in row)/mass for row, mass in zip(heaps, total) if mass]
    packet = {'questions': questions, 'answers': answers,
              'background': [model['background'][i] for i in range(len(questions))], 'one': one}
    return packet, {'answer_columns': len(answers), 'question_terms': len(questions),
                    'mean_retained_mass': sum(retained)/len(retained), 'minimum_retained_mass': min(retained),
                    'one_edges': sum(map(len, one)), 'one_empty': sum(not row for row in one)}


def compose(one, questions, answers, permutation=None):
    source = {word: i for i, word in enumerate(answers)}
    following = [source.get(word) for word in questions]
    result = []
    for row in one:
        counts = Counter()
        for b, first in row:
            middle = following[b]
            if middle is None:
                continue
            if permutation is not None:
                middle = permutation[middle]
            for c, second in one[middle]:
                counts[c] += first*second
        result.append(normalize(counts))
    return result


def decode(packet, columns):
    prob = [{} for _ in packet['questions']]
    vectors = []
    for a, entries in enumerate(columns):
        total = sum(p for _, p in entries)
        vectors.append({q: p/total for q, p in entries} if total else {})
        for q, p in entries:
            prob[q][a] = p
    model = {'qv': {(w,): i for i, w in enumerate(packet['questions'])},
             'av': {(w,): i for i, w in enumerate(packet['answers'])}, 'prob': prob,
             'background': dict(enumerate(packet['background'])), 'width': 1}
    return model, vectors


def mean_vector(columns, indices):
    values = Counter()
    used = 0
    for i in indices:
        if columns[i]:
            used += 1
            for q, p in columns[i].items():
                values[q] += p
    return {q: p/used for q, p in values.items()} if used else {}


def distance(left, right):
    if not left or not right:
        return 1.
    total = 0.
    for key in sorted(left.keys() | right.keys()):
        p, q = left.get(key, 0.), right.get(key, 0.)
        middle = (p+q)/2
        if p:
            total += .5*p*math.log(p/middle)
        if q:
            total += .5*q*math.log(q/middle)
    return math.sqrt(min(1., max(0., total/math.log(2))))


class AlignmentBinding:
    def __init__(self, bot):
        self.bot = bot
        self.original_candidates, self.original_load = bot._candidates, bot.load_context
        self.margins = self.original_candidates.__func__.__globals__['SELECTION_MARGINS']
        self.packet = self.units = None
        self.decoded = self.prepared = self.composites = None
        self.cost = {'decode_cpu_s': 0., 'context_cpu_s': 0., 'decodes': 0, 'contexts': 0}
        bot._candidates, bot.load_context = self.candidates, self.load_context

    def load_context(self, *args, **kwargs):
        result = self.original_load(*args, **kwargs)
        self.prepare()
        return result

    def prepare(self):
        packet = self.bot.context_model.get('alignment')
        if not packet:
            self.packet = self.units = self.decoded = self.prepared = self.composites = None
            return False
        if packet is not self.packet:
            start = time.process_time()
            self.decoded = [decode(packet, packet['one']), decode(packet, packet['two'])]
            self.packet, self.units = packet, None
            self.cost['decode_cpu_s'] += time.process_time()-start
            self.cost['decodes'] += 1
        if self.units is not self.bot.context_units:
            start = time.process_time()
            self.prepared = g65.prepared_units(self.bot, self.decoded[0][0])
            self.composites = [[mean_vector(columns, ids) for ids in self.prepared] for _, columns in self.decoded]
            self.units = self.bot.context_units
            self.cost['context_cpu_s'] += time.process_time()-start
            self.cost['contexts'] += 1
        return True

    def candidates(self, order, how, base, asked, terms, question, k):
        candidates = self.original_candidates(order, how, base, asked, terms, question, k)
        if not self.prepare():
            return candidates
        query = sorted(set(terms))
        for step, ((model, columns), composites) in enumerate(zip(self.decoded, self.composites), 1):
            known = sum((q,) in model['qv'] for q in query)
            scores = [score/max(1, known) for score in g65.alignment_scores(model, self.prepared, query)]
            indices = [model['av'][(q,)] for q in query if (q,) in model['av']]
            qvector = mean_vector(columns, indices)
            share = sum(bool(columns[i]) for i in indices)/max(1, len(query))
            for (_, i), features in zip(order, candidates):
                runner = max((score for j, score in enumerate(scores) if j != i), default=0.)
                features.update({f'alignment{step}_score': str(_bin(scores[i], self.margins)),
                                 f'alignment{step}_margin': str(_bin(scores[i]-runner, self.margins)),
                                 f'alignment{step}_distance': str(_bin(distance(qvector, composites[i]), COVER_BINS)),
                                 f'alignment{step}_known': str(_bin(share, COVER_BINS))})
        return candidates

    def restore(self):
        self.bot._candidates, self.bot.load_context = self.original_candidates, self.original_load
        self.packet = self.units = self.decoded = self.prepared = self.composites = None


def fingerprint():
    files = ('experiments/g84_indirect_alignment.py', 'experiments/test_g84_indirect_alignment.py',
             'experiments/g65_correspondencias.py', 'experiments/g79_joint_selection.py',
             'experiments/g80_factorized_selection.py', 'experiments/g68_confianza.py',
             'experiments/g75_relational_evidence.py', 'prereg/G-84-correspondencias-indirectas-acotadas.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G84 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    prep = None
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        binding = AlignmentBinding(bot)
        result, error = public_measure(bot), None
        prep = dict(binding.cost)
        binding.restore()
        reference.restore()
    except Exception as exc:
        result, error = None, repr(exc)
    return {'result': result, 'error': error, 'cpu_s': time.process_time()-start,
            'context_preparation_included': prep, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


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
    stage_cost = {'load_cpu_s': time.process_time()-cpu0}
    start = time.process_time()
    examples = g65.examples(bot, ROOT/'.leobot-data/mfaq_es_train.jsonl')
    stage_cost['examples_cpu_s'] = time.process_time()-start
    word_model, education = g65.train(examples, 1)
    stage_cost['alignment_learning_cpu_s'] = education['total_cpu_s']
    start = time.process_time()
    packet, compilation = compile_direct(word_model)
    del word_model, examples
    gc.collect()
    packet['two'] = compose(packet['one'], packet['questions'], packet['answers'])
    permutation = list(range(len(packet['answers'])))
    random.Random(1).shuffle(permutation)
    shuffled = compose(packet['one'], packet['questions'], packet['answers'], permutation)
    compilation.update(two_edges=sum(map(len, packet['two'])), two_empty=sum(not r for r in packet['two']),
                       shuffled_edges=sum(map(len, shuffled)), shuffled_empty=sum(not r for r in shuffled),
                       two_new_edges=sum(len({q for q, _ in second}-{q for q, _ in first})
                                         for first, second in zip(packet['one'], packet['two'])))
    stage_cost['compilation_cpu_s'] = time.process_time()-start
    archive = ROOT/'.leobot-data/g84_alignment.json'
    archive.write_text(json.dumps({'packet': packet, 'shuffled': shuffled, 'education': education,
                                  'compilation': compilation, 'stage_cost': stage_cost,
                                  'source_sha256': g65.MFAQ_SHA}, ensure_ascii=False))
    print(json.dumps({'stage': 'alignment_ready', 'education': education, 'compilation': compilation,
                      'cost': stage_cost}), flush=True)

    components = Components()
    components.correct_calibration()
    reference = components.bind(bot)
    binding = AlignmentBinding(bot)
    ns = components.learner
    native = {k: v for k, v in old_models['combined'].items() if k != 'selection'}
    original_fit, fits, models, selection_education = ns['fit'], [], {}, {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G84 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        (ROOT/'.leobot-data/g84_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': fitted}))
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = ROOT/'.leobot-data/g84_models.json'
    start = time.process_time()
    for name, columns in (('direct', packet['one']), ('indirect', packet['two']), ('shuffled', shuffled)):
        context = {**native, 'alignment': {**packet, 'two': columns}}
        bot.context_model = context
        turns = ns['training_turns'](bot)
        assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        learned = ns['selection'](turns, names, 6)
        models[name] = {**context, 'selection': ns['table_of'](learned)}
        selection_education[name] = {'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns), 'features': names}
        model_path.write_text(json.dumps({'models': models, 'education': selection_education,
                                         'sources_sha256': hashes}, ensure_ascii=False))
    stage_cost['selection_learning_cpu_s'] = time.process_time()-start
    teaching_preparation = dict(binding.cost)
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G84 agotó enseñanza')
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
    bot.context_model = models['indirect']
    bot.load_context('', '')
    candidate = ROOT/'.leobot-data/g84_candidate.json'
    bot.save(candidate)
    evaluation_cpu += time.process_time()-start
    all_preparation = dict(binding.cost)
    binding.restore()
    restored = measured('restored_g79', old_models['combined'])
    reference.restore()
    disabled = measured('disabled', original)
    del binding, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g84_indirect_alignment', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'g79_restored_exact': restored['response_sha256'] == results['g79']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['indirect']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib'])
    primary = results['indirect']
    gates = {'useful_gain': primary['useful_core'] >= 326, 'absent': primary['quotes_without_data'] <= 73,
             'selection_gain': raw['indirect']['correct_first'] >= 491,
             'controls_gain': all(primary['useful_core'] >= results[n]['useful_core']+17 for n in ('direct', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and time.process_time()-cpu0+child['cpu_s'] <= 800
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G84', 'scope': 'spent development; external prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g79_models_sha256': G79_SHA,
              'base_sha256': BASE_SHA, 'education_source_sha256': g65.MFAQ_SHA,
              'alignment_education': education, 'compilation': compilation,
              'selection_education': selection_education, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'teaching_stages': stage_cost,
                       'teaching_preparation_included': teaching_preparation,
                       'all_preparation_included': all_preparation, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
                       'peak_rss_kib': rss, 'parent_rss_during_child_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g84_indirect_alignment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except (TimeoutError, AssertionError, MemoryError) as error:
            (ROOT/'results_v3/g84_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }, indent=2)+'\n')
            raise

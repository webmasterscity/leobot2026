"""G85: teach the unchanged selector with human-localized evidence candidates."""
from collections import Counter, defaultdict
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
from experiments.g57_kiosco import contains
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments import g78_localized_education as g78
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g84_indirect_alignment import AlignmentBinding

G84_SHA = 'fd528ab70a602289c271916835c00c570e21b7b2d5ca0f08207515f2bf0384b7'
FIELDS = ('score', 'margin', 'distance', 'known')


class DirectBinding(AlignmentBinding):
    """Reuse one computation only after confirming that the two tables are equal."""
    def prepare(self):
        active = super().prepare()
        if active and getattr(self, 'checked_packet', None) is not self.packet:
            start = time.process_time()
            if self.packet['one'] != self.packet['two']:
                raise ValueError('G85 requiere dos señales directas idénticas')
            self.checked_packet = self.packet
            key = 'identical_signal_check_cpu_s'
            self.cost[key] = self.cost.get(key, 0.)+time.process_time()-start
        return active

    def candidates(self, *args, **kwargs):
        if not self.prepare():
            return self.original_candidates(*args, **kwargs)
        decoded, composites = self.decoded, self.composites
        try:
            self.decoded, self.composites = decoded[:1], composites[:1]
            candidates = super().candidates(*args, **kwargs)
        finally:
            self.decoded, self.composites = decoded, composites
        for f in candidates:
            for name in FIELDS:
                f['alignment2_'+name] = f['alignment1_'+name]
        return candidates


def covers(context, unit, start, length):
    if not unit or start < 0 or length <= 0:
        return False
    offset = 0
    while True:
        found = context.find(unit, offset)
        if found < 0:
            return False
        if found <= start and start+length <= found+len(unit):
            return True
        offset = found+1


def unit_label(context, unit, answer, start):
    if covers(context, unit, start, len(answer)):
        return 1
    return None if contains(unit, answer) else 0


def select_human():
    path = ROOT/'.leobot-data/sqac_train.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == g78.SOURCE_SHA
    data = json.loads(path.read_text())['data']
    eligible, excluded = [], Counter()
    for article in data:
        for paragraph in article['paragraphs']:
            context = paragraph['context']
            units = g78.segments(context)
            identity = article.get('title') or hashlib.sha256(context.encode()).hexdigest()
            group = hashlib.sha256(json.dumps((article.get('source'), identity), sort_keys=True).encode()).hexdigest()
            for qa in paragraph['qas']:
                if qa['id'] == '6cf3dcd6-b5a3-4516-8f9e-c5c1c6b66628':
                    excluded['published_example'] += 1
                    continue
                answer = (qa.get('answers') or [{}])[0]
                text, start = answer.get('text', ''), answer.get('answer_start')
                if g78.locate(context, text, start, units) is None:
                    excluded['invalid_or_crossing_span'] += 1
                    continue
                if not any(text not in sentence and sentence.strip() for _, _, sentence in units):
                    excluded['no_rival_without_answer'] += 1
                    continue
                eligible.append({'digest': hashlib.sha256(qa['id'].encode()).digest(), 'id': qa['id'],
                                 'group': group, 'question': qa['question'], 'context': context,
                                 'answer': text, 'start': start})
    selected = sorted(eligible, key=lambda q: q['digest'])[:10000]
    ids_sha = hashlib.sha256(json.dumps([q['id'] for q in selected], separators=(',', ':')).encode()).hexdigest()
    return selected, {'articles': len(data), 'eligible': len(eligible), 'selected': len(selected),
                      'groups': len({q['group'] for q in selected}), 'exclusions': dict(excluded),
                      'selected_ids_sha256': ids_sha, 'source_sha256': g78.SOURCE_SHA}


def human_turns(bot):
    selected, source = select_human()
    by_context = defaultdict(list)
    for qa in selected:
        by_context[qa['context']].append(qa)
    turns, excluded, ambiguous, positive_rows = [], Counter(), 0, 0
    for context, questions in sorted(by_context.items()):
        bot.load_context(context, '')
        for qa in questions:
            rows = []
            for i, features in bot.selection_candidates(qa['question'], 6):
                label = unit_label(context, bot.context_units[i]['text'], qa['answer'], qa['start'])
                if label is None:
                    ambiguous += 1
                else:
                    rows.append((features, label))
            if not any(y for _, y in rows):
                excluded['no_positive_candidate'] += 1
                continue
            if not any(not y for _, y in rows):
                excluded['no_negative_candidate'] += 1
                continue
            turns.append({'half': -1, 'rows': rows})
            positive_rows += sum(y for _, y in rows)
    return turns, {'source': source, 'contexts': len(by_context), 'turns': len(turns),
                   'rows': sum(len(t['rows']) for t in turns), 'positive_rows': positive_rows,
                   'ambiguous_candidate_rows_excluded': ambiguous, 'excluded_turns': dict(excluded)}


def teach(ns, turns, human):
    """Additional examples affect fits, never OOF calibration observations."""
    original_fit = ns['fit']
    ns['fit'] = lambda items, names: original_fit(items+human, names)
    try:
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        return ns['selection'](turns, names, 6)
    finally:
        ns['fit'] = original_fit


def fingerprint():
    files = ('experiments/g85_human_selection.py', 'experiments/test_g85_human_selection.py',
             'experiments/g84_indirect_alignment.py', 'experiments/g84b_compact_replay.py',
             'experiments/g78_localized_education.py', 'experiments/g79_joint_selection.py',
             'experiments/g68_confianza.py', 'experiments/g75_relational_evidence.py',
             'prereg/G-85-educar-selector-con-evidencia-humana.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G85 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    prep = None
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        binding = DirectBinding(bot)
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
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g84_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G84_SHA
    fixed = json.loads(previous.read_text())['models']['direct']
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    bot.context_model = fixed
    components = Components()
    components.correct_calibration()
    reference = components.bind(bot)
    ns = components.learner
    legacy = AlignmentBinding(bot)
    stage = {}
    start = time.process_time()
    expected_turns = ns['training_turns'](bot)
    legacy.restore()
    del legacy
    binding = DirectBinding(bot)
    turns = ns['training_turns'](bot)
    assert expected_turns == turns, 'La optimización cambia rasgos o etiquetas'
    parity = {'exact': True, 'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns)}
    assert parity['turns'] == 3520 and parity['rows'] == 20629
    del expected_turns
    stage['parity_and_business_preparation_cpu_s'] = time.process_time()-start
    print(json.dumps({'stage': 'parity', **parity, 'cpu_s': stage}), flush=True)
    start = time.process_time()
    human, education = human_turns(bot)
    old_education = json.loads((ROOT/'results_v3/g78_localized_education.json').read_text())['education']
    for key in ('articles', 'eligible', 'selected', 'groups', 'exclusions', 'source_sha256'):
        assert education['source'][key] == old_education[key], 'El conjunto de enseñanza difiere de G78'
    stage['human_preparation_cpu_s'] = time.process_time()-start
    (ROOT/'.leobot-data/g85_human_checkpoint.json').write_text(json.dumps({'education': education, 'cost': stage}, ensure_ascii=False))
    print(json.dumps({'stage': 'human_ready', 'education': education, 'cost': stage}), flush=True)
    shuffled = ns['shuffled_labels'](human)
    education['shuffled_label_changes'] = sum(y1 != y2 for t1, t2 in zip(human, shuffled)
                                             for (_, y1), (_, y2) in zip(t1['rows'], t2['rows']))
    original_fit, fits, models = ns['fit'], [], {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G85 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        (ROOT/'.leobot-data/g85_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': fitted}))
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = ROOT/'.leobot-data/g85_models.json'
    start = time.process_time()
    for name, extra in (('without_human', []), ('human', human), ('shuffled', shuffled)):
        learned = teach(ns, turns, extra)
        models[name] = {**fixed, 'selection': ns['table_of'](learned)}
        model_path.write_text(json.dumps({'models': models, 'education': education, 'sources_sha256': hashes}, ensure_ascii=False))
    stage['selection_learning_cpu_s'] = time.process_time()-start
    teaching_preparation = dict(binding.cost)
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G85 agotó enseñanza')
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
    old_report = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())['candidates']
    baseline = measured('baseline', original)
    assert baseline['response_sha256'] == old_report['baseline']['response_sha256']
    for name, context in models.items():
        measured(name, context, raw_selection=True)
        if name == 'without_human':
            assert results[name]['response_sha256'] == old_report['direct']['response_sha256'], 'G84 directo no reproduce'
    start = time.process_time()
    bot.context_model = models['human']
    bot.load_context('', '')
    readable, candidate = ROOT/'.leobot-data/g85_candidate_readable.json', ROOT/'.leobot-data/g85_candidate.json'
    bot.save(readable)
    evaluation_cpu += time.process_time()-start
    all_preparation = dict(binding.cost)
    binding.restore()
    reference.restore()
    disabled = measured('disabled', original)
    del binding, reference, bot, turns, human, shuffled, extra
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(readable), str(candidate)],
                             cwd=ROOT, capture_output=True, text=True, timeout=40, check=True)
    compacted = json.loads(process.stdout)
    process = subprocess.run([sys.executable, '-m', 'experiments.g85_human_selection', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+compacted['cpu_s']+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'features_exact': parity['exact'],
                'without_human_exact': results['without_human']['response_sha256'] == old_report['direct']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['human']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(child['peak_rss_kib'], compacted['peak_rss_kib']))
    primary = results['human']
    gates = {'useful_gain': primary['useful_core'] >= 344, 'absent': primary['quotes_without_data'] <= 73,
             'selection_gain': raw['human']['correct_first'] >= 499,
             'education_gain': all(primary['useful_core'] >= results[n]['useful_core']+17 for n in ('without_human', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200
                       and time.process_time()-cpu0+child['cpu_s']+compacted['cpu_s'] <= 800
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G85', 'scope': 'spent development; human education at selector; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g84_models_sha256': G84_SHA,
              'base_sha256': BASE_SHA, 'education': education, 'parity': parity, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'compaction': compacted, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'teaching_stages': stage,
                       'teaching_preparation_included': teaching_preparation,
                       'all_preparation_included': all_preparation, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': time.process_time()-cpu0+child['cpu_s']+compacted['cpu_s'],
                       'wall_s': time.monotonic()-wall0, 'peak_rss_kib': rss,
                       'parent_rss_during_children_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g85_human_selection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except (TimeoutError, AssertionError, MemoryError) as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g85_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }, indent=2)+'\n')
            raise

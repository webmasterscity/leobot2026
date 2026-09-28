"""G94: fixed selector educated with atomic human FAQ answers and rival texts."""
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
from experiments import g65_correspondencias as g65
from experiments import g68_confianza as g68
from experiments.g57_kiosco import plain
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g85_human_selection import DirectBinding, G84_SHA, teach, replay


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def rivals(own, alternatives):
    own = ' '+own+' '
    return [a for a in alternatives if own not in ' '+a+' ' and ' '+a+' ' not in own]


def exercise(bot, question, answers, own):
    ordered = sorted(answers, key=digest)
    expected = Counter(plain(answer) for answer in ordered)
    bot.load_context('\n'.join(ordered), '')
    if len(expected) != 6 or len(bot.context_units) != 6 or \
            Counter(plain(u['text']) for u in bot.context_units) != expected or \
            any(u['kind'] in ('question', 'heading') for u in bot.context_units):
        return None, 'layout_changed'
    rows = [(features, int(plain(bot.context_units[i]['text']) == own))
            for i, features in bot.selection_candidates(question, 6)]
    if not any(label for _, label in rows):
        return None, 'positive_not_proposed'
    if not any(not label for _, label in rows):
        return None, 'negative_not_proposed'
    return {'half': -1, 'rows': rows}, None


def faq_turns(bot, deadline):
    started = time.process_time()
    raw = g65.examples(bot, ROOT/'.leobot-data/mfaq_es_train.jsonl', raw=True)
    sample = sorted(raw, key=lambda row: digest(*row))[:8000]
    excluded, accepted = Counter(), []
    for domain, question, answer in sample:
        if time.process_time() > deadline:
            raise TimeoutError('G94 agotó preparación')
        if len(answer.split()) > 64:
            excluded['long_answer'] += 1
            continue
        units = bot._layout_units(answer, 'context')
        if len(units) != 1 or units[0]['kind'] in ('question', 'heading') or \
                not plain(units[0]['text']) or plain(units[0]['text']) != plain(answer):
            excluded['not_one_whole_unit'] += 1
            continue
        accepted.append({'id': digest(domain, question, answer), 'domain': domain,
                         'question': question, 'answer': answer, 'own': plain(answer)})
    question_answers = defaultdict(set)
    for row in accepted:
        question_answers[row['domain'], plain(row['question'])].add(row['own'])
    unambiguous = [row for row in accepted if len(question_answers[row['domain'], plain(row['question'])]) == 1]
    excluded['question_with_multiple_answers'] = len(accepted)-len(unambiguous)
    groups = defaultdict(dict)
    for row in unambiguous:
        groups[row['domain']].setdefault(row['own'], row['answer'])
    eligible = []
    for row in unambiguous:
        alternatives = rivals(row['own'], sorted(groups[row['domain']]))
        if len(alternatives) < 5:
            excluded['fewer_than_five_rivals'] += 1
            continue
        eligible.append({**row, 'rivals': alternatives})
    selected = sorted(eligible, key=lambda r: r['id'])[:4000]
    by_domain = defaultdict(list)
    for row in selected:
        by_domain[row['domain']].append(row)
    plans, fallback = [], 0
    for domain, queries in sorted(by_domain.items()):
        if time.process_time() > deadline:
            raise TimeoutError('G94 agotó propuesta de rivales')
        texts = groups[domain]
        bot.load_context('\n'.join(texts[k] for k in sorted(texts)), '')
        for row in queries:
            scores = {}
            order = bot._scored(bot.context_terms(row['question']), row['question'])['order']
            for score, index in order:
                key = plain(bot.context_units[index]['text'])
                if key in row['rivals']:
                    scores[key] = max(score, scores.get(key, -float('inf')))
            hard = sorted(scores, key=lambda key: (-scores[key], key))[:5]
            missing = sorted((k for k in row['rivals'] if k not in hard), key=lambda k: digest(row['id'], k))
            fallback += 5-len(hard)
            hard += missing[:5-len(hard)]
            random = sorted(row['rivals'], key=lambda key: digest(row['id'], key))[:5]
            plans.append((row, {'hard': [row['answer']]+[texts[k] for k in hard],
                                'random': [row['answer']]+[texts[k] for k in random]}))
    turns, ids, domains, differences = {'random': [], 'hard': []}, [], set(), 0
    for row, documents in sorted(plans, key=lambda item: item[0]['id']):
        if time.process_time() > deadline:
            raise TimeoutError('G94 agotó preparación de ejercicios')
        pair, errors = {}, []
        for name in ('random', 'hard'):
            turn, error = exercise(bot, row['question'], documents[name], row['own'])
            pair[name] = turn
            if error:
                excluded[name+'_'+error] += 1
                errors.append(error)
        if errors:
            excluded['joint_exclusion'] += 1
            continue
        for name in turns:
            turns[name].append(pair[name])
        ids.append(row['id'])
        domains.add(row['domain'])
        differences += set(map(plain, documents['hard'])) != set(map(plain, documents['random']))
    return turns, {'raw_examples': len(raw), 'sampled': len(sample), 'atomic_answers': len(accepted),
                    'unambiguous': len(unambiguous), 'eligible_before_cap': len(eligible), 'selected': len(selected),
                    'selected_ids_sha256': digest([row['id'] for row in selected]),
                    'common_turns': len(ids), 'common_domains': len(domains), 'common_ids_sha256': digest(ids),
                    'different_documents': differences, 'unproposed_rivals_filled_by_hash': fallback,
                    'excluded': dict(excluded), 'preparation_cpu_s': time.process_time()-started,
                    'rows': {name: sum(len(t['rows']) for t in rows) for name, rows in turns.items()}}


def fingerprint():
    files = ('experiments/g94_faq_selection.py', 'experiments/test_g94_faq_selection.py',
             'experiments/g85_human_selection.py', 'experiments/g84_indirect_alignment.py',
             'experiments/g84b_compact_replay.py', 'experiments/g65_correspondencias.py',
             'experiments/g79_joint_selection.py', 'experiments/g68_confianza.py',
             'experiments/g75_relational_evidence.py',
             'prereg/G-94-enseñar-con-respuestas-de-negocio-competidoras.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G94 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


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
    binding = DirectBinding(bot)
    ns = components.learner
    extra, education = faq_turns(bot, cpu0+600)
    folder = ROOT/'.leobot-data/g94'
    folder.mkdir(exist_ok=True)
    available = education['common_turns'] >= 1000 and education['common_domains'] >= 50
    print(json.dumps({'stage': 'faq_ready', 'education': education, 'available': available}), flush=True)
    (folder/'education.json').write_text(json.dumps(education, indent=2)+'\n')
    if not available:
        report = {'experiment': 'G94', 'scope': 'source feasibility failed; no selector fits or DEV evaluation',
                  'repository_engine_sha': ENGINE, 'sources_sha256': hashes, 'base_sha256': BASE_SHA,
                  'education': education, 'gates': {'availability': False}, 'passes': False,
                  'cost': {'cpu_s': time.process_time()-cpu0, 'wall_s': time.monotonic()-wall0,
                           'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           'previous_g84_cpu_s': json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())['cost']['total_cpu_s']}}
        assert fingerprint() == hashes
        (ROOT/'results_v3/g94_faq_selection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        return
    turns = ns['training_turns'](bot)
    assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
    extra['shuffled'] = ns['shuffled_labels'](extra['hard'])
    education['shuffled_label_changes'] = sum(y != z for t, u in zip(extra['hard'], extra['shuffled'])
                                               for (_, y), (_, z) in zip(t['rows'], u['rows']))
    original_fit, fits, models = ns['fit'], [], {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G94 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = folder/'models.json'
    for name in ('removed', 'random', 'hard', 'shuffled'):
        learned = teach(ns, turns, extra.get(name, []))
        models[name] = {**fixed, 'selection': ns['table_of'](learned)}
        model_path.write_text(json.dumps({'models': models, 'education': education, 'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G94 agotó enseñanza')
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
    bot.context_model = models['hard']
    bot.load_context('', '')
    readable, candidate = folder/'candidate_readable.json', folder/'candidate.json'
    bot.save(readable)
    evaluation_cpu += time.process_time()-start
    preparation = dict(binding.cost)
    binding.restore()
    reference.restore()
    disabled = measured('disabled', original)
    del binding, reference, bot, turns, extra
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(readable), str(candidate)],
                             cwd=ROOT, capture_output=True, text=True, timeout=40, check=True)
    compacted = json.loads(process.stdout)
    process = subprocess.run([sys.executable, '-m', 'experiments.g94_faq_selection', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+compacted['cpu_s']+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'direct_exact': results['removed']['response_sha256'] == old_report['candidates']['direct']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['hard']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(child['peak_rss_kib'], compacted['peak_rss_kib']))
    total_cpu = time.process_time()-cpu0+child['cpu_s']+compacted['cpu_s']
    primary = results['hard']
    gates = {'availability': available, 'useful_gain': primary['useful_core'] >= 368,
             'absent': primary['quotes_without_data'] <= 73, 'selection_gain': raw['hard']['correct_first'] >= 491,
             'hard_negative_gain': all(primary['useful_core'] >= results[n]['useful_core']+17 for n in ('random', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and total_cpu <= 800
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    report = {'experiment': 'G94', 'scope': 'spent business development; weak rival labels; unchanged selector',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g84_models_sha256': G84_SHA,
              'base_sha256': BASE_SHA, 'education': education, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'compaction': compacted, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'preparation_included': preparation, 'total_cpu_s': total_cpu,
                       'wall_s': time.monotonic()-wall0, 'peak_rss_kib': rss,
                       'parent_rss_during_children_kib': parent_rss, 'models_bytes': model_path.stat().st_size,
                       'base_bytes': candidate.stat().st_size, 'previous_g84_cpu_s': old_report['cost']['total_cpu_s']}}
    (ROOT/'results_v3/g94_faq_selection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
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
            (ROOT/'results_v3/g94_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

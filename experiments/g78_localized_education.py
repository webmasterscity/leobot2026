"""G78 re-educates stable relevance tables using human-labeled evidence spans."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import gc
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from leobot import Bot
from leobot.context import _SENTENCE_END
from experiments.g57_educar_kiosco import PI_MIN, RARE, BRIDGE_SUPPORT, BRIDGE_LIFT, BRIDGE_TOP
from experiments.g68_confianza import TRAIN, DEV, collect, metrics
from experiments.g74_relation_coverage import ROOT, BASE_SHA, ENGINE
from experiments.g75_relational_evidence import fit_confidence, public_measure, check_budget

SOURCE_SHA = '1d5c76176646e2ae7bdcd8b5ec6f18349102a9363aa25ad7d0e48262d7480d43'
WEIGHTS = (.25, .5, .75, 1.)


def segments(text):
    result, start = [], 0
    for boundary in _SENTENCE_END.finditer(text):
        result.append((start, boundary.start(), text[start:boundary.start()]))
        start = boundary.end()
    result.append((start, len(text), text[start:]))
    return result


def locate(text, answer, start, units):
    if not isinstance(start, int) or start < 0 or not answer or text[start:start+len(answer)] != answer:
        return None
    return next((i for i, (lo, hi, _) in enumerate(units) if lo <= start and start+len(answer) <= hi), None)


def education_examples(bot):
    path = ROOT / '.leobot-data/sqac_train.json'
    if sha256(path.read_bytes()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('SQAC distinto de F4')
    data = json.loads(path.read_text())['data']
    eligible, excluded = [], Counter()
    for article in data:
        for paragraph in article['paragraphs']:
            context = paragraph['context']
            units = segments(context)
            identity = article.get('title') or sha256(context.encode()).hexdigest()
            group = sha256(json.dumps((article.get('source'), identity), sort_keys=True).encode()).hexdigest()
            for qa in paragraph['qas']:
                if qa['id'] == '6cf3dcd6-b5a3-4516-8f9e-c5c1c6b66628':
                    excluded['published_example'] += 1
                    continue
                answer = (qa.get('answers') or [{}])[0]
                text, start = answer.get('text', ''), answer.get('answer_start')
                own = locate(context, text, start, units)
                if own is None:
                    excluded['invalid_or_crossing_span'] += 1
                    continue
                other = [i for i, (_, _, sentence) in enumerate(units) if text not in sentence and sentence.strip()]
                if not other:
                    excluded['no_rival_without_answer'] += 1
                    continue
                choose = lambda salt: min(other, key=lambda i: sha256(f'{qa["id"]}:{salt}:{i}'.encode()).digest())
                eligible.append((sha256(qa['id'].encode()).digest(), group, qa['question'],
                                 units[own][2], context, units[choose(0)][2], units[choose(1)][2]))
    chosen = sorted(eligible)[:10000]
    cache = {}
    def terms(text):
        if text not in cache:
            cache[text] = frozenset(bot.context_terms(text))
        return cache[text]
    observations = {name: [] for name in ('localized', 'paragraph', 'shuffled')}
    for _, domain, q, own, paragraph, rival, wrong in chosen:
        query, negative = terms(q), terms(rival)
        for mode, text in (('localized', own), ('paragraph', paragraph), ('shuffled', wrong)):
            observations[mode].append((domain, query, terms(text), negative))
    return observations, {'articles': len(data), 'eligible': len(eligible), 'selected': len(chosen),
                          'groups': len({r[1] for r in chosen}), 'exclusions': dict(excluded),
                          'wrong_equals_rival': sum(r[5] == r[6] for r in chosen),
                          'tokenized_texts': len(cache), 'source_sha256': SOURCE_SHA}


def count_table(rows):
    """Same G57/G59 excess, support, lift and truncation, with explicit rivals."""
    nq, na, own, other = Counter(), Counter(), Counter(), Counter()
    by_group = defaultdict(list)
    qdom, adom = Counter(), Counter()
    for domain, qs, ans, rival in rows:
        nq.update(qs)
        na.update(ans)
        own.update(qs & ans)
        other.update(qs & rival)
        by_group[domain].append((qs, ans, rival))
    for entries in by_group.values():
        qdom.update(set().union(*(q for q, _, _ in entries)))
        adom.update(set().union(*(a for _, a, _ in entries)))
    delta = {q: round(max(0., (own[q]+1)/(n+2)-(other[q]+1)/(n+2)), 4)
             for q, n in sorted(nq.items()) if n >= PI_MIN}
    rare = [q for q, n in nq.items() if RARE[0] <= n <= RARE[1]]
    den = sum(nq[q] for q in rare)+2
    rare_delta = round(max(0., (sum(own[q] for q in rare)+1)/den-(sum(other[q] for q in rare)+1)/den), 4)
    qok, aok = {q for q, n in qdom.items() if n >= BRIDGE_SUPPORT}, {a for a, n in adom.items() if n >= BRIDGE_SUPPORT}
    positive, background, support = Counter(), Counter(), Counter()
    for domain, entries in sorted(by_group.items()):
        local = set()
        for qs, ans, rival in entries:
            for q in sorted(qs & qok):
                for a in sorted((ans & aok)-qs):
                    positive[(q, a)] += 1
                    local.add((q, a))
                for a in sorted((rival & aok)-qs):
                    background[(q, a)] += 1
        support.update(local)
    kept = defaultdict(list)
    for (q, a), domains in sorted(support.items()):
        if domains < BRIDGE_SUPPORT:
            continue
        conditional = positive[(q, a)]/nq[q]
        prior = na[a]/len(rows)
        if conditional/prior < BRIDGE_LIFT:
            continue
        weight = max(0., conditional-background[(q, a)]/nq[q])
        if weight > 0:
            kept[q].append((weight, a))
    bridge = {q: '|'.join(f'{a}:{p:.4f}' for p, a in sorted(entries, key=lambda x: (-x[0], x[1]))[:BRIDGE_TOP])
              for q, entries in sorted(kept.items())}
    return {'delta': delta, 'rare_delta': rare_delta, 'bridge': bridge}, {
        'examples': len(rows), 'groups': len(by_group), 'delta_terms': len(delta),
        'bridge_words': len(bridge), 'associations': sum(v.count('|')+1 for v in bridge.values()),
        'rare_delta': rare_delta, 'cooccurrences': len(positive)}


def parsed_bridge(table):
    return {q: {a: float(p) for a, p in (item.rsplit(':', 1) for item in row.split('|') if item)}
            for q, row in table.items()}


def mix_tables(original, learned, weight):
    if not weight:
        return original
    left, right = parsed_bridge(original['bridge']), parsed_bridge(learned['bridge'])
    mixed = {}
    for q in sorted(set(left) | set(right)):
        terms = set(left.get(q, {})) | set(right.get(q, {}))
        values = [((1-weight)*left.get(q, {}).get(a, 0.)+weight*right.get(q, {}).get(a, 0.), a) for a in terms]
        values = [(p, a) for p, a in values if p > 0]
        if values:
            mixed[q] = '|'.join(f'{a}:{p:.4f}' for p, a in sorted(values, key=lambda x: (-x[0], x[1]))[:BRIDGE_TOP])
    return {**original, 'bridge': mixed,
            'delta': {q: (1-weight)*original['delta'].get(q, original['rare_delta'])
                        + weight*learned['delta'].get(q, learned['rare_delta'])
                      for q in sorted(set(original['delta']) | set(learned['delta']))},
            'rare_delta': (1-weight)*original['rare_delta']+weight*learned['rare_delta']}


def fingerprint():
    files = ('experiments/g78_localized_education.py', 'experiments/g75_relational_evidence.py',
             'experiments/g68_confianza.py', 'experiments/g57_educar_kiosco.py',
             'prereg/G-78-educacion-con-evidencia-localizada.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G78 no congelado')
    return {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in files}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (505, 510))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes = fingerprint()
    cpu0, wall0 = time.process_time(), time.monotonic()
    base = ROOT / '.leobot-data/base_kiosco.json'
    if sha256(base.read_bytes()).hexdigest() != BASE_SHA:
        raise RuntimeError('Base distinta')
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    observations, education = education_examples(bot)
    preparation = time.process_time()-cpu0
    print(json.dumps({'stage': 'prepared', 'education': education, 'cpu_s': preparation}), flush=True)
    tables, costs = {}, {}
    checkpoint = ROOT / '.leobot-data/g78_tables.json'
    for mode, rows in observations.items():
        check_budget(cpu0+300)
        start = time.process_time()
        tables[mode], costs[mode] = count_table(rows)
        costs[mode]['cpu_s'] = time.process_time()-start
        checkpoint.write_text(json.dumps({'tables': tables, 'education': education, 'counts': costs,
                                          'sources_sha256': hashes}, ensure_ascii=False))
        print(json.dumps({'stage': 'learned', 'mode': mode, 'counts': costs[mode]}), flush=True)
    teaching_cpu = time.process_time()-cpu0
    del observations
    start = time.process_time()
    deadline = start+200
    baseline_rows = collect(bot, TRAIN)
    baseline_fit = metrics(baseline_rows, [r['baseline_p'] for r in baseline_rows])
    baseline = public_measure(bot, deadline=deadline)
    assert (baseline['useful_core'], baseline['quotes_without_data']) == (269, 74)
    choices, fits, chosen = {}, {}, {}
    for mode, table in tables.items():
        best = (baseline_fit['useful_core'], -baseline_fit['quotes_without_data'], 0.)
        choices[mode], chosen[mode], fits[mode] = 0., original, {}
        for weight in WEIGHTS:
            check_budget(deadline)
            bot.context_model = mix_tables(original, table, weight)
            rows = collect(bot, TRAIN)
            fitted, probabilities = fit_confidence(rows, ())
            result = metrics(rows, probabilities)
            fits[mode][str(weight)] = result
            candidate = (result['useful_core'], -result['quotes_without_data'], -weight)
            if fitted is not None and result['quotes_without_data'] <= baseline_fit['quotes_without_data'] and candidate > best:
                conf = {**fitted['model'], 'calibration': fitted['calibration'], 'cite_from': .4, 'rows': len(rows)}
                best, choices[mode], chosen[mode] = candidate, weight, {**bot.context_model, 'confidence': conf}
            print(json.dumps({'stage': 'selection', 'mode': mode, 'weight': weight,
                              'useful': result['useful_core'], 'absent': result['quotes_without_data']}), flush=True)
    selection_cpu = time.process_time()-start
    start = time.process_time()
    results, raw = {}, {}
    for mode, model in chosen.items():
        bot.context_model = model
        results[mode] = public_measure(bot, deadline=deadline)
        rows = collect(bot, DEV)
        raw[mode] = {'core': sum(r['core'] for r in rows), 'correct_first': sum(r['core'] and r['y'] for r in rows)}
        print(json.dumps({'stage': 'measured', 'mode': mode, 'weight': choices[mode],
                          'result': results[mode], 'raw': raw[mode]}), flush=True)
    path = ROOT / '.leobot-data/g78_models.json'
    path.write_text(json.dumps(chosen, ensure_ascii=False))
    bot.context_model = chosen['localized']
    bot.load_context('', '')
    candidate_path = ROOT / '.leobot-data/g78_candidate.json'
    bot.save(candidate_path)
    del bot
    gc.collect()
    parent_rss = int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                          if line.startswith('VmRSS:')))
    child_code = '''import json,resource,sys,time
from leobot import Bot
from experiments.g75_relational_evidence import public_measure
t=time.process_time()
try:
 b=Bot.load(sys.argv[1]); result=public_measure(b); error=None
except Exception as exc:
 result=None; error=repr(exc)
print(json.dumps({'result':result,'error':error,'cpu_s':time.process_time()-t,
 'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
'''
    replay = subprocess.run([sys.executable, '-c', child_code, str(candidate_path)],
                            cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'},
                            text=True, capture_output=True, timeout=40, check=True)
    child = json.loads(replay.stdout)
    deadline -= child['cpu_s']
    bot = Bot.load(base)
    disabled = public_measure(bot, deadline=deadline)
    controls = {'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['localized']['response_sha256'],
                'disabled_exact': disabled['response_sha256'] == baseline['response_sha256']}
    evaluation_cpu = time.process_time()-start+child['cpu_s']
    primary = results['localized']
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib'])
    gates = {'gain': primary['useful_core'] >= baseline['useful_core']+.05*baseline['core'],
             'paragraph_gain': primary['useful_core'] >= results['paragraph']['useful_core']+.02*baseline['core'],
             'shuffled_gain': primary['useful_core'] >= results['shuffled']['useful_core']+.02*baseline['core'],
             'absent': primary['quotes_without_data'] <= baseline['quotes_without_data'],
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 300 and selection_cpu+evaluation_cpu <= 200 and rss <= 1024**2
                       and time.monotonic()-wall0 <= 700}
    assert fingerprint() == hashes
    report = {'experiment': 'G78', 'scope': 'spent development; learned tables only; no promotion',
              'engine_sha': ENGINE, 'engine_unchanged': True, 'base_sha256': BASE_SHA, 'sources_sha256': hashes,
              'education': education, 'counting': costs, 'baseline': baseline, 'training_baseline': baseline_fit,
              'training_choices': fits, 'chosen_weights': choices, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'restart': child, 'gates': gates,
              'passes': all(gates.values()), 'cost': {'preparation_cpu_s': preparation,
                  'teaching_total_cpu_s': teaching_cpu, 'selection_cpu_s': selection_cpu,
                  'evaluation_cpu_s': evaluation_cpu, 'total_cpu_s': time.process_time()-cpu0+child['cpu_s'],
                  'wall_s': time.monotonic()-wall0, 'peak_rss_kib': rss, 'model_bytes': path.stat().st_size,
                  'base_bytes': candidate_path.stat().st_size, 'parent_rss_during_child_kib': parent_rss}}
    (ROOT / 'results_v3/g78_localized_education.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'results': results, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    start_cpu, start_wall = time.process_time(), time.monotonic()
    try:
        main()
    except TimeoutError as error:
        (ROOT / 'results_v3/g78_interruption.json').write_text(json.dumps({
            'status': 'interrupted_budget', 'error': str(error), 'cpu_s': time.process_time()-start_cpu,
            'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }, ensure_ascii=False, indent=2)+'\n')
        raise

"""G-13: local symbolic span/role induction from explicit MASSIVE annotations."""
from __future__ import annotations

import io
import json
import math
import os
import random
import re
import resource
import statistics
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g12_massive_source_gate import SEEDS, SPAN, source


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '310462a79fa181ff83c643a8d356c7b8155fd37a25e80a77ba3ca9b29305c4a5'
WORD = re.compile(r"\w+(?:[-’']\w+)*", re.UNICODE)
MAX_WIDTH = 6
MAX_CANDIDATES = 1000


def norm(word):
    return ''.join(char for char in unicodedata.normalize('NFD', word.casefold())
                   if not unicodedata.combining(char))


def parse_row(item):
    text = item['utt']
    tokens = [(norm(match.group()), match.start(), match.end())
              for match in WORD.finditer(text)]
    annotated = item['annot_utt']
    rebuilt, spans = [], []
    cursor = 0
    for match in SPAN.finditer(annotated):
        rebuilt.append(annotated[cursor:match.start()])
        start = sum(map(len, rebuilt))
        value = match.group(2).strip()
        rebuilt.append(value)
        spans.append((start, start+len(value), match.group(1).strip()))
        cursor = match.end()
    rebuilt.append(annotated[cursor:])
    if ''.join(rebuilt) != text:
        raise RuntimeError('Anotación no reconstruye frase')
    gold = []
    for left, right, role in spans:
        chosen = [idx for idx, (_, a, b) in enumerate(tokens) if a >= left and b <= right]
        if not chosen or chosen != list(range(chosen[0], chosen[-1]+1)):
            raise RuntimeError('Fragmento sin tokens alineables')
        gold.append((chosen[0], chosen[-1]+1, role))
    return {'scenario': item['scenario'], 'text': text,
            'tokens': [tok for tok, _, _ in tokens], 'gold': gold}


def load_rows(raw):
    rows = []
    for line in io.BytesIO(raw):
        item = json.loads(line)
        if item['partition'] == 'train':
            rows.append(parse_row(item))
    return rows


def candidates(row):
    size = len(row['tokens'])
    for start in range(size):
        for end in range(start+1, min(size, start+MAX_WIDTH)+1):
            yield start, end


def features(row, start, end, context=True):
    seq = row['tokens']
    words = seq[start:end]
    first, last = words[0], words[-1]
    out = ['first='+first, 'last='+last, 'length='+str(end-start),
           'prefix='+first[:3], 'suffix='+last[-3:]]
    if end-start <= 3:
        out.append('phrase='+' '.join(words))
    if any(char.isdigit() for word in words for char in word):
        out.append('shape=digit')
    if context:
        out.extend(('left='+(seq[start-1] if start else '<start>'),
                    'right='+(seq[end] if end < len(seq) else '<end>')))
        if start >= 2:
            out.append('left2='+seq[start-2]+' '+seq[start-1])
        if end+1 < len(seq):
            out.append('right2='+seq[end]+' '+seq[end+1])
    return out


def fit(rows, with_context=True):
    role_examples = Counter()
    feature_positive = defaultdict(Counter)
    domains = defaultdict(set)
    positive_spans = 0
    for row in rows:
        for start, end, role in row['gold']:
            if end-start > MAX_WIDTH:
                continue
            positive_spans += 1
            role_examples[role] += 1
            for feature in features(row, start, end, with_context):
                feature_positive[feature][role] += 1
                domains[(feature, role)].add(row['scenario'])
    role_domains = defaultdict(set)
    for row in rows:
        for _, _, role in row['gold']:
            role_domains[role].add(row['scenario'])
    eligible = sorted(role for role, count in role_examples.items()
                      if count >= 20 and len(role_domains[role]) >= 3)
    promising = {feature for feature, counts in feature_positive.items()
                 if any(count >= 5 and len(domains[(feature, role)]) >= 2
                        for role, count in counts.items() if role in eligible)}
    occurrence = Counter()
    total_candidates = 0
    for row in rows:
        for start, end in candidates(row):
            total_candidates += 1
            for feature in features(row, start, end, with_context):
                if feature in promising:
                    occurrence[feature] += 1
    priors = {role: math.log((role_examples[role]+1)/
                             (total_candidates-role_examples[role]+1))
              for role in eligible}
    weights = defaultdict(dict)
    for feature in sorted(promising):
        total = occurrence[feature]
        if total < 20:
            continue
        for role, support in sorted(feature_positive[feature].items()):
            if role not in priors or support < 5 or len(domains[(feature, role)]) < 2:
                continue
            odds = math.log((support+1)/(total-support+1))
            lift = odds-priors[role]
            if lift > 0:
                weights[feature][role] = min(4.0, lift)
    return {'roles': eligible, 'priors': priors, 'weights': dict(weights),
            'positive_spans': positive_spans, 'total_candidates': total_candidates,
            'promoted_features': sum(map(len, weights.values()))}


def choose_nonoverlap(size, proposed):
    ending = defaultdict(list)
    for start, end, role, score in proposed:
        ending[end].append((start, role, score))
    best = [(0.0, tuple()) for _ in range(size+1)]
    for end in range(1, size+1):
        options = [best[end-1]]
        for start, role, score in ending[end]:
            prior, spans = best[start]
            options.append((prior+score, spans+((start,end,role),)))
        best[end] = max(options, key=lambda item: (item[0], -len(item[1]), item[1]))
    return list(best[size][1])


def predict(model, row):
    proposed = []
    evaluated = 0
    for start, end in candidates(row):
        evidence = defaultdict(list)
        for feature in features(row, start, end, model['with_context']):
            for role, weight in model['weights'].get(feature, {}).items():
                evidence[role].append(weight)
        evaluated += len(evidence)
        if evaluated > MAX_CANDIDATES:
            return [], evaluated, True
        for role, found in evidence.items():
            score = model['priors'][role] + sum(sorted(found, reverse=True)[:4])
            if score > 0:
                proposed.append((start, end, role, score))
    return choose_nonoverlap(len(row['tokens']), proposed), evaluated, False


def train_model(rows, context=True):
    model = fit(rows, context)
    model['with_context'] = context
    return model


def memory_model(rows, eligible):
    counts = defaultdict(Counter)
    role_count = Counter()
    for row in rows:
        for start, end, role in row['gold']:
            if role in eligible:
                counts[' '.join(row['tokens'][start:end])][role] += 1
                role_count[role] += 1
    lookup = {text: next(iter(roles)) for text, roles in counts.items() if len(roles) == 1}
    mode = sorted(role_count.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return lookup, set(counts), mode


def memory_predict(row, lookup, known, mode=None):
    proposed = []
    for start, end in candidates(row):
        text = ' '.join(row['tokens'][start:end])
        if text in known:
            role = mode if mode is not None else lookup.get(text)
            if role is not None:
                proposed.append((start, end, role, end-start))
    return choose_nonoverlap(len(row['tokens']), proposed)


def measures(rows, preds, eligible, seen_texts):
    counts = {name: Counter() for name in preds}
    per_role = {name: defaultdict(Counter) for name in preds}
    for idx, row in enumerate(rows):
        gold_all = set(row['gold'])
        gold = {item for item in gold_all if item[2] in eligible}
        gold_novel = {item for item in gold
                      if ' '.join(row['tokens'][item[0]:item[1]]) not in seen_texts}
        for name, predictions in preds.items():
            got_all = set(predictions[idx])
            got = {item for item in got_all if item[2] in eligible}
            got_novel = {item for item in got
                         if ' '.join(row['tokens'][item[0]:item[1]]) not in seen_texts}
            stat = counts[name]
            stat['tp'] += len(gold & got)
            stat['pred'] += len(got)
            stat['gold'] += len(gold)
            stat['novel_tp'] += len(gold_novel & got_novel)
            stat['novel_pred'] += len(got_novel)
            stat['novel_gold'] += len(gold_novel)
            stat['all_tp'] += len(gold_all & got_all)
            stat['all_pred'] += len(got_all)
            stat['all_gold'] += len(gold_all)
            stat['utterance_exact'] += got_all == gold_all
            for role in eligible:
                g = {item for item in gold if item[2] == role}
                p = {item for item in got if item[2] == role}
                per_role[name][role]['tp'] += len(g & p)
                per_role[name][role]['pred'] += len(p)
                per_role[name][role]['gold'] += len(g)
    def f1(tp, pred, gold):
        return 2*tp/(pred+gold) if pred+gold else 0.0
    report = {}
    for name, stat in counts.items():
        report[name] = {**dict(stat),
                        'f1': f1(stat['tp'], stat['pred'], stat['gold']),
                        'novel_f1': f1(stat['novel_tp'], stat['novel_pred'], stat['novel_gold']),
                        'all_f1': f1(stat['all_tp'], stat['all_pred'], stat['all_gold']),
                        'precision': stat['tp']/stat['pred'] if stat['pred'] else 0.0,
                        'recall': stat['tp']/stat['gold'] if stat['gold'] else 0.0}
    role_report = {role: {'gold': per_role['treatment'][role]['gold'],
                          'f1': f1(per_role['treatment'][role]['tp'],
                                   per_role['treatment'][role]['pred'],
                                   per_role['treatment'][role]['gold'])}
                   for role in eligible}
    return report, role_report


def synthetic_counterevidence():
    def row(scenario, word, role):
        return {'scenario': scenario, 'text': 'pre '+word+' post',
                'tokens': ['pre', word, 'post'], 'gold': [(1,2,role)]}
    before = [row('a'+str(i%3), 'qiva', 'role_a') for i in range(30)]
    before += [row('b'+str(i%3), 'zelu', 'role_b') for i in range(30)]
    after = before+[row('c'+str(i%3), 'qiva', 'role_b') for i in range(90)]
    after += [row('d'+str(i%3), 'zelu', 'role_a') for i in range(90)]
    first, second = fit(before), fit(after)
    key = 'phrase=qiva'
    old = first['weights'].get(key, {}).get('role_a', 0)
    new_a = second['weights'].get(key, {}).get('role_a', 0)
    new_b = second['weights'].get(key, {}).get('role_b', 0)
    return {'before_a': old, 'after_a': new_a, 'after_b': new_b,
            'reversed': old > 0 and new_b > new_a}


def renaming_probe(model, rows, predicted, eligible):
    tested = stable = original_correct = renamed_correct = abstained = 0
    for row, before in zip(rows, predicted):
        for start, end, role in row['gold']:
            if tested >= 100:
                break
            if end-start != 1 or role not in eligible:
                continue
            changed = {**row, 'tokens': list(row['tokens'])}
            changed['tokens'][start] = 'qivanuevo'+str(tested)
            after = predict(model, changed)[0]
            first_label = next((label for a,b,label in before if (a,b)==(start,end)), None)
            second_label = next((label for a,b,label in after if (a,b)==(start,end)), None)
            stable += first_label == second_label
            original_correct += first_label == role
            renamed_correct += second_label == role
            abstained += second_label is None
            tested += 1
        if tested >= 100:
            break
    return {'sampled_one_token_spans': tested, 'same_label': stable,
            'original_correct': original_correct, 'renamed_correct': renamed_correct,
            'renamed_abstained': abstained}


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del ensayo')
    raw, archive_bytes, _ = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente cambió')
    rows = load_rows(raw)
    del raw
    names = sorted({row['scenario'] for row in rows})
    random.Random(int(h0[:8], 16) ^ seed ^ 0x69B).shuffle(names)
    heldout = set(names[:max(3, round(.2*len(names)))])
    train = [row for row in rows if row['scenario'] not in heldout]
    test = [row for row in rows if row['scenario'] in heldout]
    del rows
    read_cpu = time.process_time()-cpu0
    tick = time.process_time()
    treatment = train_model(train, True)
    teach_cpu = time.process_time()-tick
    tick = time.process_time()
    ablation = train_model(train, False)
    ablation_cpu = time.process_time()-tick
    rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x39A)
    by_db = defaultdict(list)
    for row in train:
        by_db[row['scenario']].append(row)
    shuffled = []
    for db, items in sorted(by_db.items()):
        labels = [role for item in items for _, _, role in item['gold']]
        rng.shuffle(labels)
        cursor = 0
        for item in items:
            n = len(item['gold'])
            shuffled.append({**item, 'gold': [(a,b,role) for (a,b,_),role
                                              in zip(item['gold'], labels[cursor:cursor+n])]})
            cursor += n
    tick = time.process_time()
    shuffled_model = train_model(shuffled, True)
    shuffled_cpu = time.process_time()-tick
    lookup, seen_texts, modal = memory_model(train, set(treatment['roles']))
    with tempfile.NamedTemporaryFile(mode='w+', encoding='utf8') as stream:
        json.dump(treatment, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        stream.seek(0)
        restored = json.load(stream)
    restart_same = restored == treatment
    treatment = restored
    predictions = {key: [] for key in ('treatment','ablation','shuffled','memory','mode','fresh')}
    latency, checked_total, timeouts = [], 0, Counter()
    over_10ms = Counter()
    candidate_limit = Counter()
    inference_tick = time.process_time()
    for row in test:
        start = time.perf_counter_ns()
        picked, checked, over = predict(treatment, row)
        elapsed = (time.perf_counter_ns()-start)/1e6
        latency.append(elapsed)
        predictions['treatment'].append(picked)
        checked_total += checked
        timeouts['treatment'] += over
        over_10ms['treatment'] += elapsed > 10
        candidate_limit['treatment'] += over
        for name, model in (('ablation', ablation), ('shuffled', shuffled_model)):
            check_start = time.perf_counter_ns()
            found, _, over = predict(model, row)
            predictions[name].append(found)
            timeouts[name] += over
            over_10ms[name] += (time.perf_counter_ns()-check_start)/1e6 > 10
            candidate_limit[name] += over
        predictions['memory'].append(memory_predict(row, lookup, seen_texts))
        predictions['mode'].append(memory_predict(row, lookup, seen_texts, modal))
        predictions['fresh'].append([])
    inference_cpu = time.process_time()-inference_tick
    eval_tick = time.process_time()
    stats, by_role = measures(test, predictions, set(treatment['roles']), seen_texts)
    renaming = renaming_probe(treatment, test, predictions['treatment'], set(treatment['roles']))
    eval_cpu = time.process_time()-eval_tick
    probe = synthetic_counterevidence()
    gold_over6 = sum(end-start > MAX_WIDTH for row in test for start,end,_ in row['gold'])
    eligible_well_supported = sum(detail['gold'] >= 20 and detail['f1'] >= .30
                                  for detail in by_role.values())
    p95 = sorted(latency)[int((len(latency)-1)*.95)]
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu <= 120 and wall <= 180 and rss <= 256*1024 and p95 <= 10 and max(latency) <= 1000
    best_control = max(stats[name]['f1'] for name in ('ablation','shuffled','memory','mode','fresh'))
    gate = (budget and restart_same and probe['reversed'] and
            stats['treatment']['f1'] >= .55 and
            stats['treatment']['f1']-best_control >= .15 and
            stats['treatment']['novel_f1'] >= .35 and
            stats['treatment']['novel_f1']-stats['memory']['novel_f1'] >= .10 and
            eligible_well_supported >= 3 and
            checked_total <= MAX_CANDIDATES*len(test) and
            not any(timeouts.values()))
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'development_span_role_learner',
              'preregistration': 'prereg/G-13-vinculos-de-papeles.md',
              'seed': seed, 'source_spanish_sha256': SOURCE_SHA,
              'source_archive_bytes': archive_bytes,
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'training_scenarios': len(names)-len(heldout),
              'heldout_scenarios': len(heldout),
              'training_utterances': len(train), 'test_utterances': len(test),
              'eligible_roles': len(treatment['roles']),
              'positive_spans': treatment['positive_spans'],
              'training_candidate_spans': treatment['total_candidates'],
              'promoted_features': treatment['promoted_features'],
              'shuffled_promoted_features': shuffled_model['promoted_features'],
              'stats': stats, 'per_role': by_role,
              'gold_spans_over6': gold_over6,
              'well_supported_roles_at_f1_030': eligible_well_supported,
              'counterevidence_probe': probe, 'restart_same': restart_same,
              'renaming_probe': renaming,
              'timeouts_or_candidate_abstentions': dict(timeouts),
              'response_over_10ms': dict(over_10ms),
              'candidate_limit_exceeded': dict(candidate_limit),
              'model_sha256': sha256(json.dumps(treatment, ensure_ascii=False,
                                               sort_keys=True).encode()).hexdigest(),
              'candidate_evaluations': checked_total,
              'read_cpu_s': round(read_cpu, 6),
              'treatment_teach_cpu_s': round(teach_cpu, 6),
              'ablation_teach_cpu_s': round(ablation_cpu, 6),
              'shuffled_teach_cpu_s': round(shuffled_cpu, 6),
              'inference_cpu_s': round(inference_cpu, 6),
              'evaluation_cpu_s': round(eval_cpu, 6),
              'p50_ms': round(statistics.median(latency), 6),
              'p95_ms': round(p95, 6), 'budget_ok': budget,
              'max_ms': round(max(latency), 6),
              'gate_pass': gate, 'cpu_total_s': round(cpu, 6),
              'wall_total_s': round(wall, 6), 'max_rss_kib': rss}
    path = ROOT / f'results_v3/g13_span_roles_seed{seed}_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: output[key] for key in ('seed','test_utterances','eligible_roles',
        'stats','promoted_features','gold_spans_over6','counterevidence_probe',
        'candidate_evaluations','p95_ms','budget_ok','gate_pass','cpu_total_s',
        'wall_total_s','max_rss_kib')}, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el ensayo')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python -m experiments.g13_span_roles 719|787|853')
    main(int(sys.argv[1]))

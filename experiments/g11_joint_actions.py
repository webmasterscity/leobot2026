"""G-11: joint decoding of learned lexical actions; no motor edits."""
from __future__ import annotations

import json
import math
import os
import random
import resource
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g9_structure_gate import signature
from experiments.g9b_compositional_learner import (ACTION_NAMES, NUMBER, QUOTE,
                                                  bounded_call, tokens)
from experiments.g10_cross_domain_lexicon import learn, phrases, predict, balanced_stats


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (521, 587, 641)
LAMBDAS = (0, .25, .5, 1, 2)
BITS = tuple(tuple(bool(mask & (1 << idx)) for idx in range(len(ACTION_NAMES)))
             for mask in range(1 << len(ACTION_NAMES)))


def local_scores(model, question):
    best = [0.0] * len(ACTION_NAMES)
    count = 0
    for phrase in sorted(phrases(question)):
        weights = model['weights'].get(phrase)
        if weights is None:
            continue
        count += 1
        for idx, weight in enumerate(weights):
            if abs(weight) > abs(best[idx]):
                best[idx] = weight
    return [base+evidence for base, evidence in zip(model['prior'], best)], count


def pair_affinity(rows):
    n = len(rows)
    total = [0] * len(ACTION_NAMES)
    counts = {(i, j): [0, 0, 0, 0] for i in range(len(ACTION_NAMES))
              for j in range(i+1, len(ACTION_NAMES))}
    for row in rows:
        values = row['signature'][3]
        for idx, value in enumerate(values):
            total[idx] += bool(value)
        for i, j in counts:
            counts[(i, j)][2*int(bool(values[i]))+int(bool(values[j]))] += 1
    weights = {}
    for (i, j), table in sorted(counts.items()):
        for left in (0, 1):
            for right in (0, 1):
                joint = (table[2*left+right]+1)/(n+4)
                p_left = ((total[i] if left else n-total[i])+1)/(n+2)
                p_right = ((total[j] if right else n-total[j])+1)/(n+2)
                weights[(i, j, left, right)] = math.log(joint/(p_left*p_right))
    pair = []
    for vector in BITS:
        pair.append(sum(weights[(i, j, int(vector[i]), int(vector[j]))]
                        for i, j in counts)/(len(ACTION_NAMES)-1))
    return pair, weights


def joint_predict(model, question, lam):
    local, examined = local_scores(model['lexicon'], question)
    if examined > 1000:
        return None, examined
    # Only 2**8 typed action vectors; tie breaks toward the simpler vector.
    ranked = max(range(len(BITS)), key=lambda k: (
        sum(local[i] for i, value in enumerate(BITS[k]) if value)
        + lam*model['pair_scores'][k],
        -sum(BITS[k]), -k))
    return BITS[ranked], examined+len(BITS)


def folds_for(rows, seed):
    dbs = sorted({row['db_id'] for row in rows})
    random.Random(seed).shuffle(dbs)
    assignment = {db: idx % 3 for idx, db in enumerate(dbs)}
    return assignment


def fit_with_cv(rows, seed):
    start = time.process_time()
    assignment = folds_for(rows, seed)
    scores = Counter()
    evaluated = 0
    for fold in range(3):
        learned = [row for row in rows if assignment[row['db_id']] != fold]
        valid = [row for row in rows if assignment[row['db_id']] == fold]
        model = {'lexicon': learn(learned), 'pair_scores': pair_affinity(learned)[0]}
        for item in valid:
            local, _ = local_scores(model['lexicon'], item['question'])
            independent = [sum(local[i] for i, value in enumerate(BITS[k]) if value)
                           for k in range(len(BITS))]
            for lam in LAMBDAS:
                chosen = max(range(len(BITS)), key=lambda k: (
                    independent[k]+lam*model['pair_scores'][k],
                    -sum(BITS[k]), -k))
                scores[lam] += BITS[chosen] == item['signature'][3]
            evaluated += 1
    chosen = sorted(LAMBDAS, key=lambda lam: (-scores[lam], lam))[0]
    final = {'lexicon': learn(rows), 'pair_scores': pair_affinity(rows)[0],
             'lambda': chosen}
    return final, {'correct_by_lambda': {str(k): scores[k] for k in LAMBDAS},
                   'validation_questions': evaluated,
                   'selected_lambda': chosen,
                   'cpu_s': round(time.process_time()-start, 6)}


def counterevidence_probe():
    i, j = 0, 1
    def rows(a, b, count, prefix):
        vector = tuple(value if idx == i else b if idx == j else False
                       for idx, value in enumerate([a]*len(ACTION_NAMES)))
        return [{'signature': (1, (0,), False, vector),
                 'db_id': prefix+str(k%3), 'question': 'qiva'} for k in range(count)]
    before = rows(True, True, 20, 'a')+rows(False, False, 20, 'b')
    after = before+rows(True, False, 80, 'c')+rows(False, True, 80, 'd')
    first = pair_affinity(before)[1][(i, j, 1, 1)]
    second = pair_affinity(after)[1][(i, j, 1, 1)]
    return {'before': first, 'after': second,
            'sign_reversed': first > 0 > second}


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX+'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambió')
    by_db = defaultdict(dict)
    for row in json.loads(raw):
        by_db[row['db_id']].setdefault(row['query'].strip().casefold(), row)
    eligible = sorted(db for db, items in by_db.items() if len(items) >= 20)
    rng = random.Random(int(h0[:8], 16)^seed^0x69B)
    rng.shuffle(eligible)
    heldout = set(eligible[:max(20, round(.2*len(eligible)))])
    training, test = [], []
    for db in sorted(eligible):
        for row in by_db[db].values():
            item = {'db_id': db, 'question': row['question']}
            if db in heldout:
                test.append((item, row['sql']))
            else:
                item['signature'] = signature(row['sql'])[0]
                training.append(item)
    read_cpu = time.process_time()-cpu0
    model, selection = fit_with_cv(training, seed)
    # The shuffled control selects its own parameter on its own training folds.
    by_train_db = defaultdict(list)
    for row in training:
        by_train_db[row['db_id']].append(row)
    shuffled = []
    for db, items in sorted(by_train_db.items()):
        labels = [item['signature'] for item in items]
        rng.shuffle(labels)
        shuffled.extend({**item, 'signature': label}
                        for item, label in zip(items, labels))
    shuffled_model, shuffled_selection = fit_with_cv(shuffled, seed)
    mode = Counter(row['signature'][3] for row in training).most_common(1)[0][0]
    majority = tuple(sum(row['signature'][3][i] for row in training) >= len(training)/2
                     for i in range(len(ACTION_NAMES)))
    with tempfile.NamedTemporaryFile(mode='w+', encoding='utf8') as stream:
        json.dump(model, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        stream.seek(0)
        restored = json.load(stream)
    restart_same = restored == model
    model = restored
    inference_start = time.process_time()
    observations, family = [], {'join_filter': Counter(), 'aggregate_order': Counter()}
    latency, candidates, rename_eligible, rename_agree = [], 0, 0, 0
    for item, gold_sql in test:
        tick = time.perf_counter_ns()
        response, timeout = bounded_call(joint_predict, model, item['question'], model['lambda'])
        latency.append((time.perf_counter_ns()-tick)/1e6)
        treatment, checked = response if response is not None else (None, 1000)
        if timeout:
            treatment = None
        candidates += checked
        separate, _ = bounded_call(predict, model['lexicon'], item['question'])
        separate = separate[0] if separate is not None else None
        ctrl, _ = bounded_call(joint_predict, shuffled_model, item['question'],
                               shuffled_model['lambda'])
        ctrl = ctrl[0] if ctrl is not None else None
        changed = NUMBER.sub(' 987654321 ', QUOTE.sub(' "opaque" ', item['question']))
        if tokens(changed) == tokens(item['question']):
            rename_eligible += 1
            renamed, _ = bounded_call(joint_predict, model, changed, model['lambda'])
            rename_agree += renamed is not None and renamed[0] == treatment
        gold = signature(gold_sql)[0][3]
        observations.append({'gold': gold, 'treatment': treatment,
                             'independent': separate, 'shuffled': ctrl,
                             'mode': mode, 'majority': majority,
                             'fresh': (False,)*len(ACTION_NAMES)})
        gold_actions = dict(zip(ACTION_NAMES, gold))
        for name, present in (('join_filter', gold_actions['join'] and gold_actions['filter']),
                              ('aggregate_order', gold_actions['aggregate'] and gold_actions['order'])):
            if present:
                family[name]['questions'] += 1
                family[name]['treatment_correct'] += treatment == gold
                family[name]['independent_correct'] += separate == gold
    inference_cpu = time.process_time()-inference_start
    names = ('treatment','independent','shuffled','mode','majority','fresh')
    exact = {name: sum(row[name] == row['gold'] for row in observations) for name in names}
    details = balanced_stats(observations)
    macro = {name: statistics.mean(stats[name] for stats in details.values())
             for name in ('treatment', 'shuffled', 'majority', 'fresh')}
    family_out = {name: dict(count) for name, count in family.items()}
    improvements = {}
    for name, count in family.items():
        n = count['questions']
        improvements[name] = ((count['treatment_correct']-count['independent_correct'])/n
                              if n else None)
    p95 = sorted(latency)[int((len(latency)-1)*.95)]
    probe = counterevidence_probe()
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu <= 40 and wall <= 70 and rss <= 256*1024 and p95 <= 10
    gate = (budget and selection['selected_lambda'] != 0 and restart_same and
            probe['sign_reversed'] and rename_eligible/len(test) >= .99 and
            rename_agree == rename_eligible and
            exact['treatment']/len(test) >= .40 and
            (exact['treatment']-exact['independent'])/len(test) >= .05 and
            all((exact['treatment']-exact[name])/len(test) >= .10
                for name in ('shuffled', 'mode')) and macro['treatment'] >= .65 and
            all(count['questions'] >= 10 for count in family.values()) and
            any(value is not None and value >= .05 for value in improvements.values()) and
            all(value is not None and value >= -.02 for value in improvements.values()))
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'development_joint_action_decode',
              'preregistration': 'prereg/G-11-decodificacion-conjunta.md',
              'seed': seed, 'engine_tree': h0, 'engine_unchanged': unchanged,
              'training_databases': len(eligible)-len(heldout),
              'heldout_databases': len(heldout),
              'training_demonstrations': len(training), 'test_questions': len(test),
              'selection': selection, 'shuffled_selection': shuffled_selection,
              'exact_action_vector': exact, 'macro_balanced_accuracy': macro,
              'family': family_out, 'family_gain': improvements,
              'rename_eligible': rename_eligible,
              'rename_unrecognized': len(test)-rename_eligible,
              'rename_agree': rename_agree,
              'counterevidence_probe': probe, 'restart_same': restart_same,
              'candidate_evaluations': candidates,
              'read_cpu_s': round(read_cpu, 6),
              'inference_cpu_s': round(inference_cpu, 6),
              'p50_ms': round(statistics.median(latency), 6),
              'p95_ms': round(p95, 6), 'budget_ok': budget,
              'gate_pass': gate, 'cpu_total_s': round(cpu, 6),
              'wall_total_s': round(wall, 6), 'max_rss_kib': rss}
    path = ROOT / f'results_v3/g11_joint_seed{seed}_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el ensayo')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python -m experiments.g11_joint_actions 521|587|641')
    main(int(sys.argv[1]))

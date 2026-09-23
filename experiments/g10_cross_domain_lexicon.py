"""G-10: preregistered feasibility of lexical action evidence across databases."""
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
from experiments.g9b_compositional_learner import ACTION_NAMES, tokens, bounded_call


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (311, 389, 457)
MAX_CANDIDATES = 1000


def phrases(question):
    seq = tokens(question)
    return {'\x1f'.join(seq[i:i+n]) for n in (1, 2, 3)
            for i in range(len(seq)-n+1)}


def learn(rows):
    """Estimate auditable token/action likelihoods from complete demonstrations."""
    totals = [0] * len(ACTION_NAMES)
    features = {}
    for row in rows:
        actions = row['signature'][3]
        for idx, present in enumerate(actions):
            totals[idx] += bool(present)
        for phrase in phrases(row['question']):
            slot = features.get(phrase)
            if slot is None:
                slot = [0, [0] * len(ACTION_NAMES), set()]
                features[phrase] = slot
            slot[0] += 1
            slot[2].add(row['db_id'])
            for idx, present in enumerate(actions):
                slot[1][idx] += bool(present)
    n = len(rows)
    prior = [math.log((count+1)/(n-count+1)) for count in totals]
    weights = {}
    for phrase, (occurrences, positive, databases) in sorted(features.items()):
        if occurrences < 8 or len(databases) < 3:
            continue
        row_weights = []
        for idx, count in enumerate(positive):
            pos_total = totals[idx]
            neg_total = n-pos_total
            p_present_if_pos = (count+1)/(pos_total+2)
            p_present_if_neg = (occurrences-count+1)/(neg_total+2)
            row_weights.append(math.log(p_present_if_pos/p_present_if_neg))
        weights[phrase] = row_weights
    return {'prior': prior, 'weights': weights,
            'candidate_phrases': len(features), 'promoted_phrases': len(weights),
            'education_examples': n}


def predict(model, question):
    best = [0.0] * len(ACTION_NAMES)
    examined = 0
    for phrase in sorted(phrases(question)):
        weights = model['weights'].get(phrase)
        if weights is None:
            continue
        examined += 1
        if examined > MAX_CANDIDATES:
            return None, examined
        for idx, weight in enumerate(weights):
            if abs(weight) > abs(best[idx]):
                best[idx] = weight
    return tuple(model['prior'][idx] + best[idx] >= 0
                 for idx in range(len(ACTION_NAMES))), examined


def balanced_stats(rows):
    details = {}
    for idx, action in enumerate(ACTION_NAMES):
        positives = [row for row in rows if row['gold'][idx]]
        negatives = [row for row in rows if not row['gold'][idx]]
        if not positives or not negatives:
            continue
        details[action] = {}
        for name in ('treatment', 'shuffled', 'majority', 'fresh'):
            tp = sum(row[name] is not None and row[name][idx] for row in positives)
            tn = sum(row[name] is not None and not row[name][idx] for row in negatives)
            details[action][name] = .5 * (tp/len(positives)+tn/len(negatives))
    return details


def counterevidence_probe():
    """Local synthetic update test; it does not measure motor rollback."""
    def row(db, word, action):
        values = tuple(action if name == 'filter' else False for name in ACTION_NAMES)
        return {'db_id': db, 'question': word,
                'signature': (1, (0,), False, values)}
    before_rows = [row('a'+str(i % 3), 'qiva', False) for i in range(9)]
    before_rows += [row('b'+str(i % 3), 'zelu', True) for i in range(9)]
    after_rows = before_rows + [row('c'+str(i % 3), 'qiva', True) for i in range(30)]
    after_rows += [row('d'+str(i % 3), 'zelu', False) for i in range(30)]
    key = 'qiva'
    idx = ACTION_NAMES.index('filter')
    first = learn(before_rows)['weights'].get(key, [0]*len(ACTION_NAMES))[idx]
    second = learn(after_rows)['weights'].get(key, [0]*len(ACTION_NAMES))[idx]
    return {'before': first, 'after': second,
            'sign_reversed': first < 0 < second}


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del ensayo')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambió')
    by_db = defaultdict(dict)
    for row in json.loads(raw):
        by_db[row['db_id']].setdefault(row['query'].strip().casefold(), row)
    eligible = sorted(db for db, rows in by_db.items() if len(rows) >= 20)
    rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x69B)
    rng.shuffle(eligible)
    heldout = set(eligible[:max(20, round(.2*len(eligible)))])
    train, test = [], []
    for db in sorted(eligible):
        for item in by_db[db].values():
            row = {'db_id': db, 'question': item['question']}
            if db in heldout:
                test.append((row, item['sql']))
            else:
                row['signature'] = signature(item['sql'])[0]
                train.append(row)
    reading_cpu = time.process_time()-cpu0
    tick = time.process_time()
    model = learn(train)
    training_cpu = time.process_time()-tick
    counts = Counter(item['signature'][3] for item in train)
    priors = tuple(sum(sig[idx]*count for sig, count in counts.items()) >= len(train)/2
                   for idx in range(len(ACTION_NAMES)))
    shuffled_rows = []
    grouped = defaultdict(list)
    for item in train:
        grouped[item['db_id']].append(item)
    for db, items in sorted(grouped.items()):
        labels = [item['signature'] for item in items]
        rng.shuffle(labels)
        shuffled_rows.extend({**item, 'signature': label}
                             for item, label in zip(items, labels))
    tick = time.process_time()
    shuffled = learn(shuffled_rows)
    shuffled_cpu = time.process_time()-tick
    with tempfile.NamedTemporaryFile(mode='w+', encoding='utf8') as stream:
        json.dump(model, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        stream.seek(0)
        restored = json.load(stream)
    restart_same = restored == model
    model = restored
    before_eval_cpu = time.process_time()
    observations, latencies, candidates = [], [], 0
    renamed_same = True
    from experiments.g9b_compositional_learner import NUMBER, QUOTE
    for item, sql in test:
        tick = time.perf_counter_ns()
        response, exceeded = bounded_call(predict, model, item['question'])
        latencies.append((time.perf_counter_ns()-tick)/1e6)
        treated, checked = response if response is not None else (None, MAX_CANDIDATES)
        if exceeded:
            treated = None
        candidates += checked
        control_response, _ = bounded_call(predict, shuffled, item['question'])
        control = control_response[0] if control_response is not None else None
        renamed = NUMBER.sub(' 987654321 ', QUOTE.sub(' "opaque" ', item['question']))
        renamed_response, _ = bounded_call(predict, model, renamed)
        renamed_same &= (renamed_response is not None and renamed_response[0] == treated)
        gold = signature(sql)[0][3]
        observations.append({'gold': gold, 'treatment': treated,
                             'shuffled': control, 'majority': priors,
                             'fresh': (False,)*len(ACTION_NAMES)})
    inference_cpu = time.process_time()-before_eval_cpu
    action_stats = balanced_stats(observations)
    macro = {name: statistics.mean(v[name] for v in action_stats.values())
             for name in ('treatment', 'shuffled', 'majority', 'fresh')}
    exact = {name: sum(row[name] == row['gold'] for row in observations)
             for name in macro}
    gains = {action: metrics['treatment'] - max(metrics['shuffled'], metrics['majority'])
             for action, metrics in action_stats.items()}
    p95 = sorted(latencies)[int((len(latencies)-1)*.95)]
    probe = counterevidence_probe()
    cpu_total, wall_total = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu_total <= 30 and wall_total <= 60 and rss <= 256*1024 and p95 <= 10
    gate = (budget and restart_same and renamed_same and probe['sign_reversed'] and
            macro['treatment'] >= .65 and
            macro['treatment'] - max(macro['shuffled'], macro['majority']) >= .10 and
            exact['treatment']/len(test) >= .40 and
            (exact['treatment']-exact['shuffled'])/len(test) >= .10 and
            sum(delta >= .10 for delta in gains.values()) >= 2)
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'kind': 'development_cross_domain_lexical_gate',
              'preregistration': 'prereg/G-10-senal-lexica-entre-dominios.md',
              'seed': seed, 'engine_tree': h0, 'engine_unchanged': unchanged,
              'training_databases': len(eligible)-len(heldout),
              'heldout_databases': len(heldout),
              'training_demonstrations': len(train), 'test_questions': len(test),
              'candidate_phrases': model['candidate_phrases'],
              'promoted_phrases': model['promoted_phrases'],
              'shuffled_promoted_phrases': shuffled['promoted_phrases'],
              'exact_action_vector': exact, 'macro_balanced_accuracy': macro,
              'balanced_by_action': action_stats, 'action_gains': gains,
              'candidate_evaluations': candidates,
              'counterevidence_probe': probe,
              'restart_same': restart_same, 'renamed_values_same': renamed_same,
              'reading_cpu_s': round(reading_cpu, 6),
              'treatment_training_cpu_s': round(training_cpu, 6),
              'shuffled_training_cpu_s': round(shuffled_cpu, 6),
              'inference_cpu_s': round(inference_cpu, 6),
              'p50_ms': round(statistics.median(latencies), 6),
              'p95_ms': round(p95, 6), 'budget_ok': budget,
              'gate_pass': gate, 'cpu_total_s': round(cpu_total, 6),
              'wall_total_s': round(wall_total, 6), 'max_rss_kib': rss}
    path = ROOT / f'results_v3/g10_lexicon_seed{seed}_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el ensayo')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python -m experiments.g10_cross_domain_lexicon 311|389|457')
    main(int(sys.argv[1]))

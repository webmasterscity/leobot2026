"""G-21: induce role-bearing lexical fragments; oracle entity spans only."""
from __future__ import annotations

import json
import os
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g15_redfm_source_gate import source
from experiments.g16_frozen_document_learning import SOURCE_SHA, split_articles
from experiments.g19_lexical_relation_gate import (
    H0, eligible_labels, fit, instance, predict, renamed, samples,
    shuffled_labels, type_predictor,
)
from experiments.g20_weak_pair_gate import pair_of, weak_examples


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-21-operadores-lexicos-contrastivos.md'
SEEDS = (1217, 1277)


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g21_lexical_operators.py'))


def cues(example):
    order = next((value for value in example['features']
                  if value in ('order:SO', 'order:OS')), None)
    if order is None:
        return ()
    prefixes = ('m1:', 'm2:', 'l1:', 'r1:')
    return tuple((feature, order) for feature in sorted(example['features'])
                 if feature.startswith(prefixes))


def induce(examples, labels):
    type_labels = defaultdict(set)
    for example, label in zip(examples, labels):
        type_labels[example['types']].add(label)
    support = defaultdict(Counter)
    articles = defaultdict(lambda: defaultdict(set))
    ambiguous = defaultdict(Counter)
    for example, label in zip(examples, labels):
        for key in cues(example):
            support[key][label] += 1
            articles[key][label].add(example['article'])
            if len(type_labels[example['types']]) >= 2:
                ambiguous[key][label] += 1
    promoted = {}
    for key in sorted(support):
        counts = support[key]
        total = sum(counts.values())
        winner = min(counts, key=lambda label: (-counts[label], label))
        if (counts[winner] >= 6 and len(articles[key][winner]) >= 4
                and counts[winner] / total >= .90
                and ambiguous[key][winner] >= 3):
            promoted[key] = winner
    report = {
        'candidate_operators': len(support),
        'promoted_operators': len(promoted),
        'operators_with_conflicts': sum(len(labels) >= 2 for labels in support.values()),
        'promoted_predicates': len(set(promoted.values())),
        'promoted_support_episodes': sum(support[key][label]
                                         for key, label in promoted.items()),
        'promoted_counterevidence_episodes': sum(
            sum(support[key].values()) - support[key][label]
            for key, label in promoted.items()),
    }
    return promoted, report


def operator_predict(model, features):
    order = next((value for value in features
                  if value in ('order:SO', 'order:OS')), None)
    if order is None:
        return None, 0
    matched = [model[(feature, order)]
               for feature in sorted(features)
               if (feature, order) in model]
    found = set(matched)
    return (next(iter(found)) if len(found) == 1 else None), len(matched)


def digest(values):
    raw = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()
    return sha256(raw).hexdigest()


def score(test, training, treatment, shuffled, centroid, type_choice):
    types = defaultdict(set)
    memory = {}
    for example in training:
        types[example['types']].add(example['label'])
        memory.setdefault(example['pair'], example['label'])
    counts = Counter()
    per_relation = defaultdict(Counter)
    predictions = defaultdict(list)
    latency_ms = []
    for example in test:
        gold = example['label']
        tick = time.perf_counter()
        answer, matched = operator_predict(treatment, example['features'])
        latency_ms.append((time.perf_counter()-tick)*1000)
        alternatives = {
            'treatment': answer,
            'centroid': predict(centroid, example['features']),
            'type': type_choice(example),
            'shuffled': operator_predict(shuffled, example['features'])[0],
            'memory': memory.get(example['pair']),
            'fresh': None,
        }
        for name, value in alternatives.items():
            predictions[name].append(value)
            counts[name + '_correct_all'] += value == gold
        counts['cases'] += 1
        counts['matched_rules'] += matched
        per_relation[gold]['cases'] += 1
        if answer is None:
            continue
        counts['answered'] += 1
        per_relation[gold]['answered'] += 1
        per_relation[gold]['correct'] += answer == gold
        for name, value in alternatives.items():
            counts[name + '_correct_answered'] += value == gold
        if len(types[example['types']]) >= 2:
            counts['confused_answered'] += 1
            for name, value in alternatives.items():
                counts[name + '_correct_confused'] += value == gold
    ordered_latencies = sorted(latency_ms)
    report = {
        'counts': dict(counts),
        'per_relation': {label: dict(value)
                         for label, value in sorted(per_relation.items())},
        'prediction_sha256': {name: digest(values)
                              for name, values in sorted(predictions.items())},
        'treatment_p50_ms': statistics.median(latency_ms) if latency_ms else None,
        'treatment_p95_ms': (ordered_latencies[int((len(ordered_latencies)-1)*.95)]
                             if ordered_latencies else None),
        'treatment_max_ms': max(latency_ms) if latency_ms else None,
    }
    return report, predictions['treatment']


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    if not frozen():
        raise RuntimeError('Motor o evaluador no congelado')
    raw = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente cambió')
    rows = [json.loads(line) for line in raw.splitlines()]
    train_rows, test_rows, train_articles, test_articles = split_articles(rows, H0, seed)
    load_cpu = time.process_time()-cpu0

    tick = time.process_time()
    clear_all, clear_structure = samples(train_rows)
    eligible = eligible_labels(clear_all)
    clear = [value for value in clear_all if value['label'] in eligible]
    weak_all, weak_structure = weak_examples(train_rows)
    weak = [value for value in weak_all if value['label'] in eligible]
    training = clear + weak
    labels = [example['label'] for example in training]
    treatment, treatment_induction = induce(training, labels)
    shuffled_labels_ = shuffled_labels(training, int(H0[:8], 16) ^ seed ^ 0x21A)
    shuffled, shuffled_induction = induce(training, shuffled_labels_)
    centroid = fit(training, labels)
    type_choice, _, _ = type_predictor(training)
    acquisition_cpu = time.process_time()-tick

    tick = time.process_time()
    test_all, test_structure = samples(test_rows)
    seen_pairs = {pair_of(relation) for row in train_rows
                  for relation in row.get('relations') or ()}
    test = [value for value in test_all
            if value['label'] in eligible
            and pair_of(value['relation']) not in seen_pairs]
    report, predictions = score(test, training, treatment, shuffled, centroid, type_choice)
    renaming_same = True
    rename_checked = 0
    for example, predicted in zip(test, predictions):
        renamed_row, renamed_relation = renamed(example['row'], example['relation'])
        altered = instance(renamed_row, renamed_relation)
        rename_checked += 1
        if altered is None or operator_predict(treatment, altered['features'])[0] != predicted:
            renaming_same = False
            break
    inference_cpu = time.process_time()-tick

    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    counts = report['counts']
    n = counts.get('cases', 0)
    answered = counts.get('answered', 0)
    confused = counts.get('confused_answered', 0)
    best_control = max(counts.get(name + '_correct_answered', 0)
                       for name in ('type', 'centroid', 'shuffled'))
    best_confused = max(counts.get(name + '_correct_confused', 0)
                        for name in ('type', 'centroid', 'shuffled'))
    hit_relations = sum(value.get('correct', 0) > 0
                        for value in report['per_relation'].values())
    budget = cpu <= 30 and wall <= 60 and rss <= 128*1024
    gate = (budget and n >= 60 and len(eligible) >= 5
            and answered/n >= .20
            and counts.get('treatment_correct_answered', 0)/answered >= .80
            and (counts.get('treatment_correct_answered', 0)-best_control)/answered >= .15
            and hit_relations >= 5 and confused >= 20
            and counts.get('treatment_correct_confused', 0)/confused >= .70
            and (counts.get('treatment_correct_confused', 0)-best_confused)/confused >= .15
            and renaming_same)
    unchanged = frozen()
    output = {
        'kind': 'G21_oracle_span_lexical_operator_gate',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': SOURCE_SHA,
        'seed': seed,
        'training_articles': train_articles,
        'heldout_articles': test_articles,
        'clear_structure': clear_structure,
        'weak_structure': weak_structure,
        'test_structure': test_structure,
        'clear_training_episodes': len(clear),
        'weak_training_episodes': len(weak),
        'eligible_relations': len(eligible),
        'eligible_heldout_novel_pairs': n,
        'treatment_induction': treatment_induction,
        'shuffled_induction': shuffled_induction,
        'report': report,
        'rename_checked': rename_checked,
        'renaming_same': renaming_same,
        'answered': answered,
        'hit_relations': hit_relations,
        'coverage': answered/n if n else 0,
        'precision': (counts.get('treatment_correct_answered', 0)/answered
                      if answered else 0),
        'best_control_precision_answered': best_control/answered if answered else 0,
        'confused_answered': confused,
        'load_cpu_s': round(load_cpu, 6),
        'acquisition_cpu_s': round(acquisition_cpu, 6),
        'inference_cpu_s': round(inference_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
        'gate_pass': gate and unchanged,
    }
    path = ROOT / ('results_v3/g21_lexical_seed' + str(seed)
                   + '_hashseed' + os.environ.get('PYTHONHASHSEED', 'unset') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in output.items() if k != 'report'},
                     ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante el ensayo')


if __name__ == '__main__':
    main(int(sys.argv[1]))

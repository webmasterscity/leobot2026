"""G-20: test whether extra weakly aligned examples rescue lexical relation learning."""
from __future__ import annotations

import json
import os
import random
import resource
import sys
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g15_redfm_source_gate import SEEDS, source
from experiments.g16_frozen_document_learning import SOURCE_SHA, split_articles
from experiments.g19_lexical_relation_gate import (
    H0, eligible_labels, evaluate, fit, instance, predict, renamed, samples,
    shuffled_labels, type_predictor,
)


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-20-supervision-de-pares-ambiguos.md'


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g20_weak_pair_gate.py'))


def pair_of(relation):
    return (str(relation['subject'].get('uri') or relation['subject']['surfaceform']),
            str(relation['object'].get('uri') or relation['object']['surfaceform']))


def weak_examples(rows):
    examples = []
    stats = Counter()
    for row in rows:
        relations = row.get('relations') or ()
        if len(relations) < 2:
            continue
        stats['multi_paragraphs'] += 1
        by_pair = defaultdict(set)
        for relation in relations:
            by_pair[pair_of(relation)].add(str(relation['predicate']['uri']))
        for relation in relations:
            stats['candidate_triples'] += 1
            if len(by_pair[pair_of(relation)]) != 1:
                stats['ambiguous_pair_skipped'] += 1
                continue
            value = instance(row, relation)
            if value is None:
                stats['context_skipped'] += 1
            else:
                examples.append(value)
    stats['weak_eligible'] = len(examples)
    return examples, dict(stats)


def with_ablation(test, full_training, single_model, full_model, shuffled, type_choice):
    report, full_predictions = evaluate(test, full_training, full_model, shuffled,
                                        type_choice)
    counts = report['counts']
    confused = report['confused_type']
    type_labels = defaultdict(set)
    for example in full_training:
        type_labels[example['types']].add(example['label'])
    ablation_predictions = []
    for example in test:
        value = predict(single_model, example['features'])
        ablation_predictions.append(value)
        counts['ablation_correct'] = counts.get('ablation_correct', 0) + (value == example['label'])
        counts['ablation_abstained'] = counts.get('ablation_abstained', 0) + (value is None)
        if len(type_labels[example['types']]) >= 2:
            confused['ablation_correct'] = confused.get('ablation_correct', 0) + (
                value == example['label'])
    report['counts'] = counts
    report['confused_type'] = confused
    return report, full_predictions, ablation_predictions


def digest(values):
    return sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def main(seed):
    if seed not in (977, 1039) or seed not in SEEDS:
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
    single_all, single_structure = samples(train_rows)
    allowed = eligible_labels(single_all)
    single = [example for example in single_all if example['label'] in allowed]
    weak_all, weak_structure = weak_examples(train_rows)
    weak = [example for example in weak_all if example['label'] in allowed]
    full = single + weak
    full_model = fit(full, [item['label'] for item in full])
    single_model = fit(single, [item['label'] for item in single])
    shuffled = fit(full, shuffled_labels(full, int(H0[:8], 16) ^ seed ^ 0x20A))
    type_choice, _, _ = type_predictor(full)
    acquisition_cpu = time.process_time()-tick

    tick = time.process_time()
    test_all, test_structure = samples(test_rows)
    seen_pairs = {pair_of(relation) for row in train_rows
                  for relation in row.get('relations') or ()}
    test = [example for example in test_all
            if example['label'] in allowed and example['pair'] not in seen_pairs]
    report, treatment_predictions, ablation_predictions = with_ablation(
        test, full, single_model, full_model, shuffled, type_choice)
    renaming_same = True
    renaming_checked = 0
    for example, prediction in zip(test, treatment_predictions):
        altered_row, altered_rel = renamed(example['row'], example['relation'])
        other = instance(altered_row, altered_rel)
        renaming_checked += 1
        if other is None or predict(full_model, other['features']) != prediction:
            renaming_same = False
            break
    prediction_cpu = time.process_time()-tick

    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    counts, confused = report['counts'], report['confused_type']
    cases = counts.get('cases', 0)
    confused_cases = confused.get('cases', 0)
    best_control = max(counts.get(name + '_correct', 0)
                       for name in ('ablation', 'type', 'shuffled'))
    best_confused = max(confused.get(name + '_correct', 0)
                        for name in ('ablation', 'type', 'shuffled'))
    hits = sum(value.get('candidate_correct', 0) > 0
               for value in report['per_relation'].values())
    budget = cpu <= 30 and wall <= 60 and rss <= 128*1024
    gate = (budget and cases >= 60 and len(allowed) >= 5
            and counts.get('candidate_correct', 0)/cases >= .45
            and (counts.get('candidate_correct', 0)-best_control)/cases >= .10
            and hits >= 5 and confused_cases >= 20
            and (confused.get('candidate_correct', 0)-best_confused)/confused_cases >= .10
            and renaming_same)
    unchanged = frozen()
    output = {
        'kind': 'G20_weak_lexical_training_oracle_span_only',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': SOURCE_SHA,
        'seed': seed,
        'training_articles': train_articles,
        'heldout_articles': test_articles,
        'single_structure': single_structure,
        'weak_structure': weak_structure,
        'test_structure': test_structure,
        'single_training_examples': len(single),
        'weak_training_examples': len(weak),
        'eligible_relations': len(allowed),
        'eligible_heldout_novel_pairs': cases,
        'full_features': full_model[2],
        'single_features': single_model[2],
        'treatment_prediction_sha256': digest(treatment_predictions),
        'ablation_prediction_sha256': digest(ablation_predictions),
        'report': report,
        'renaming_checked': renaming_checked,
        'renaming_same': renaming_same,
        'relations_with_hit': hits,
        'treatment_accuracy': counts.get('candidate_correct', 0)/cases if cases else 0,
        'best_control_accuracy': best_control/cases if cases else 0,
        'confused_type_cases': confused_cases,
        'confused_type_advantage': ((confused.get('candidate_correct', 0)-best_confused)
                                    / confused_cases if confused_cases else None),
        'load_cpu_s': round(load_cpu, 6),
        'acquisition_cpu_s': round(acquisition_cpu, 6),
        'prediction_cpu_s': round(prediction_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
        'gate_pass': gate and unchanged,
    }
    path = ROOT / ('results_v3/g20_weak_seed' + str(seed) + '_hashseed'
                   + os.environ.get('PYTHONHASHSEED', 'unset') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in output.items()
                      if key != 'report'}, ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante el ensayo')


if __name__ == '__main__':
    main(int(sys.argv[1]))

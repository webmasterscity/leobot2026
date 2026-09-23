"""G-19: bounded oracle-span diagnostic of lexical relation induction."""
from __future__ import annotations

import json
import math
import os
import random
import re
import resource
import sys
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g15_redfm_source_gate import SEEDS, relation_id, source
from experiments.g16_frozen_document_learning import SOURCE_SHA, split_articles
from leobot.language import normalize


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-19-senal-lexica-relacional.md'
H0 = '1f3187f2ced4c97364503187d074815f33612326'


def check_frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g19_lexical_relation_gate.py'))


def renamed(row, relation):
    """Change every occurrence of either entity surface without shifting offsets."""
    text = row['text']
    names = [str(relation[k]['surfaceform']) for k in ('subject', 'object')]
    replacements = {names[0]: '¤' * len(names[0]),
                    names[1]: '§' * len(names[1])}
    for name in sorted(replacements, key=lambda value: (-len(value), value)):
        if not name:
            continue
        text = re.sub(re.escape(name), replacements[name], text, flags=re.IGNORECASE)
    updated = {**row, 'text': text}
    rel = {**relation}
    for key in ('subject', 'object'):
        entity = {**relation[key]}
        a, b = entity['boundaries']
        entity['surfaceform'] = text[int(a):int(b)]
        rel[key] = entity
    return updated, rel


def scrub(segment, names):
    norm = normalize(segment)
    for name in sorted({normalize(value) for value in names if value},
                       key=lambda value: (-len(value), value)):
        norm = re.sub(r'(?<!\w)' + re.escape(name) + r'(?!\w)', ' ', norm)
    return normalize(norm)


def instance(row, relation):
    text = row['text']
    subject, object_ = relation['subject'], relation['object']
    try:
        sa, sb = map(int, subject['boundaries'])
        oa, ob = map(int, object_['boundaries'])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= sa < sb <= len(text) and 0 <= oa < ob <= len(text)):
        return None
    if sa < oa:
        first, second, order = (sa, sb), (oa, ob), 'SO'
    else:
        first, second, order = (oa, ob), (sa, sb), 'OS'
    if first[1] > second[0]:
        return None
    between = text[first[1]:second[0]]
    if len(between) > 160 or any(mark in between for mark in '.?!\n'):
        return None
    names = (subject['surfaceform'], object_['surfaceform'])
    middle = scrub(between, names).split()[:24]
    before = scrub(text[:first[0]], names).split()[-3:]
    after = scrub(text[second[1]:], names).split()[:3]
    features = {f'm1:{token}' for token in middle}
    features.update(f'm2:{a}|{b}' for a, b in zip(middle, middle[1:]))
    features.update(f'l{j}:{token}' for j, token in enumerate(reversed(before), 1))
    features.update(f'r{j}:{token}' for j, token in enumerate(after, 1))
    features.add(f'order:{order}')
    return {
        'label': relation_id(relation),
        'features': frozenset(features),
        'types': (subject.get('type'), object_.get('type')),
        'pair': (str(subject.get('uri')), str(object_.get('uri'))),
        'article': row['uri'],
        'row': row,
        'relation': relation,
    }


def samples(rows):
    out = []
    structural = Counter()
    for row in rows:
        relations = row.get('relations') or ()
        if len(relations) != 1:
            structural['incompatible_multi_or_empty'] += 1
            continue
        structural['single_triple'] += 1
        value = instance(row, relations[0])
        if value is None:
            structural['span_context_ineligible'] += 1
        else:
            out.append(value)
    structural['eligible'] = len(out)
    return out, dict(structural)


def eligible_labels(training):
    counts = Counter(example['label'] for example in training)
    articles = defaultdict(set)
    for example in training:
        articles[example['label']].add(example['article'])
    return {label for label, count in counts.items()
            if count >= 5 and len(articles[label]) >= 3}


def fit(training, labels):
    n = len(training)
    df = Counter(feature for example in training
                 for feature in sorted(example['features']))
    idf = {feature: 1.0 + math.log((n + 1) / (count + 1))
           for feature, count in df.items()}
    sums = defaultdict(Counter)
    label_count = Counter()
    for example, label in zip(training, labels):
        label_count[label] += 1
        sums[label].update(sorted(example['features']))
    centers = {}
    for label in sorted(sums):
        values = {feature: sums[label][feature] * idf[feature] / label_count[label]
                  for feature in sorted(sums[label])}
        norm = math.sqrt(sum(value * value for value in values.values()))
        centers[label] = ({feature: value / norm for feature, value in values.items()}
                          if norm else {})
    return centers, idf, len(df)


def predict(model, features):
    centers, idf, _ = model
    q = {feature: idf[feature] for feature in sorted(features) if feature in idf}
    norm = math.sqrt(sum(value * value for value in q.values()))
    if norm == 0:
        return None
    ranked = sorted(
        ((sum(value * center.get(feature, 0.0) for feature, value in q.items()) / norm,
          label)
         for label, center in centers.items()),
        key=lambda pair: (-pair[0], pair[1]),
    )
    if not ranked or ranked[0][0] <= 0:
        return None
    if len(ranked) > 1 and abs(ranked[0][0] - ranked[1][0]) <= 1e-12:
        return None
    return ranked[0][1]


def shuffled_labels(training, seed):
    by_type = defaultdict(list)
    for index, example in enumerate(training):
        by_type[example['types']].append(index)
    values = [example['label'] for example in training]
    rng = random.Random(seed)
    for _, indexes in sorted(by_type.items(), key=lambda pair: repr(pair[0])):
        labels = [values[index] for index in indexes]
        rng.shuffle(labels)
        for index, label in zip(indexes, labels):
            values[index] = label
    return values


def type_predictor(training):
    by_type = defaultdict(Counter)
    global_count = Counter(example['label'] for example in training)
    for example in training:
        by_type[example['types']][example['label']] += 1

    def choose(example):
        counts = by_type.get(example['types']) or global_count
        if not counts:
            return None
        return min(counts, key=lambda label: (-counts[label], -global_count[label], label))

    return choose, by_type, global_count


def evaluate(test, training, model, shuffled, type_choice):
    known_pairs = {}
    for example in training:
        known_pairs.setdefault(example['pair'], example['label'])
    counts = Counter()
    confused = Counter()
    matrix = Counter()
    per_relation = defaultdict(Counter)
    candidate_predictions = []
    type_labels = defaultdict(set)
    for example in training:
        type_labels[example['types']].add(example['label'])
    for example in test:
        gold = example['label']
        predictions = {
            'candidate': predict(model, example['features']),
            'shuffled': predict(shuffled, example['features']),
            'type': type_choice(example),
            'memory': known_pairs.get(example['pair']),
            'fresh': None,
        }
        candidate_predictions.append(predictions['candidate'])
        counts['cases'] += 1
        per_relation[gold]['cases'] += 1
        for name, value in predictions.items():
            counts[name + '_correct'] += value == gold
            counts[name + '_abstained'] += value is None
            per_relation[gold][name + '_correct'] += value == gold
        matrix[(gold, predictions['candidate'] or 'ABSTAIN')] += 1
        if len(type_labels[example['types']]) >= 2:
            confused['cases'] += 1
            for name, value in predictions.items():
                confused[name + '_correct'] += value == gold
    report = {
        'counts': dict(counts),
        'confused_type': dict(confused),
        'per_relation': {key: dict(value) for key, value in sorted(per_relation.items())},
        'error_matrix': [{'gold': gold, 'predicted': pred, 'count': count}
                         for (gold, pred), count in sorted(matrix.items())],
    }
    return report, candidate_predictions


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    wall0, cpu0 = time.monotonic(), time.process_time()
    if not check_frozen():
        raise RuntimeError('Motor o evaluador no congelado')
    raw = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente distinta')
    rows = [json.loads(line) for line in raw.splitlines()]
    training_rows, test_rows, train_articles, test_articles = split_articles(rows, H0, seed)
    load_cpu = time.process_time() - cpu0

    tick = time.process_time()
    training_all, train_structure = samples(training_rows)
    allowed = eligible_labels(training_all)
    training = [example for example in training_all if example['label'] in allowed]
    labels = [example['label'] for example in training]
    model = fit(training, labels)
    shuffled = fit(training, shuffled_labels(training, int(H0[:8], 16) ^ seed ^ 0x19A))
    type_choice, _, _ = type_predictor(training)
    acquisition_cpu = time.process_time() - tick

    tick = time.process_time()
    test_all, test_structure = samples(test_rows)
    seen_pairs = {example['pair'] for example in training_all}
    test = [example for example in test_all
            if example['label'] in allowed and example['pair'] not in seen_pairs]
    report, predictions = evaluate(test, training, model, shuffled, type_choice)
    renaming_same = True
    renaming_checked = 0
    for example, prediction in zip(test, predictions):
        altered_row, altered_rel = renamed(example['row'], example['relation'])
        other = instance(altered_row, altered_rel)
        renaming_checked += 1
        if other is None or predict(model, other['features']) != prediction:
            renaming_same = False
            break
    prediction_cpu = time.process_time() - tick

    total_cpu, total_wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    counts, confused = report['counts'], report['confused_type']
    cases = counts.get('cases', 0)
    best_control = max(counts.get(name + '_correct', 0)
                       for name in ('type', 'memory', 'shuffled'))
    confused_cases = confused.get('cases', 0)
    confused_control = max(confused.get(name + '_correct', 0)
                           for name in ('type', 'shuffled'))
    relations_with_hit = sum(value.get('candidate_correct', 0) > 0
                             for value in report['per_relation'].values())
    budget = total_cpu <= 30 and total_wall <= 60 and rss <= 128*1024
    gate = (budget and cases >= 60 and len(allowed) >= 5 and
            counts.get('candidate_correct', 0) / cases >= .40 and
            (counts.get('candidate_correct', 0) - best_control) / cases >= .15 and
            relations_with_hit >= 5 and confused_cases >= 20 and
            (confused.get('candidate_correct', 0) - confused_control) / confused_cases >= .10
            and renaming_same)
    unchanged = check_frozen()
    output = {
        'kind': 'G19_oracle_span_lexical_signal_only',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': SOURCE_SHA,
        'seed': seed,
        'training_articles': train_articles,
        'heldout_articles': test_articles,
        'training_structure': train_structure,
        'heldout_structure': test_structure,
        'training_examples': len(training),
        'eligible_relations': len(allowed),
        'eligible_heldout_novel_pairs': cases,
        'features': model[2],
        'report': report,
        'renaming_checked': renaming_checked,
        'renaming_same': renaming_same,
        'relations_with_hit': relations_with_hit,
        'candidate_accuracy': counts.get('candidate_correct', 0) / cases if cases else 0,
        'best_control_accuracy': best_control / cases if cases else 0,
        'confused_type_cases': confused_cases,
        'confused_type_advantage': ((confused.get('candidate_correct', 0)-confused_control)
                                    / confused_cases if confused_cases else None),
        'load_cpu_s': round(load_cpu, 6),
        'acquisition_cpu_s': round(acquisition_cpu, 6),
        'prediction_cpu_s': round(prediction_cpu, 6),
        'cpu_total_s': round(total_cpu, 6),
        'wall_total_s': round(total_wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
        'gate_pass': gate and unchanged,
    }
    path = ROOT / ('results_v3/g19_lexical_seed'
                   + str(seed) + '_hashseed' + os.environ.get('PYTHONHASHSEED', 'unset')
                   + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('report',)}, ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante el ensayo')


if __name__ == '__main__':
    main(int(sys.argv[1]))

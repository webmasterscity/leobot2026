"""F-18 development: bounded symbolic order graph over human Spanish pairs."""
from __future__ import annotations

import json
import resource
import statistics
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from experiments.f18_pawsx_inventory import REVISION, rows, tokens
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE = 'e818e96cbdb7877483999a4f9bcf2545f716fd9d64bae09aacf14ac32e344df9'
MAX_PROGRAMS = 256
ORDER_BLIND = ('set_overlap', 'multiset_overlap', 'length_ratio', 'unique_coverage')
ORDERED = ORDER_BLIND + ('lcs_ratio', 'inversion_fraction',
                         'adjacency_preserved', 'mean_displacement')


def partition(data: list[dict], tree: str) -> dict[str, list[dict]]:
    parents = {row['sentence1']: row['sentence1'] for row in data}

    def root(value: str) -> str:
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    def union(left: str, right: str) -> None:
        a, b = root(left), root(right)
        if a != b:
            parents[max(a, b)] = min(a, b)

    pairs = {(row['sentence1'], row['sentence2']) for row in data}
    for left, right in pairs:
        if (right, left) in pairs and right in parents:
            union(left, right)
    components = defaultdict(list)
    for anchor in parents:
        components[root(anchor)].append(anchor)
    ranked = sorted(components.values(), key=lambda group: (
        sha256((tree + ':F18:es:' + min(group)).encode()).hexdigest(), min(group)))
    assigned = {}
    anchor_count = 0
    for component in ranked:
        split = 'fit' if anchor_count < 1100 else ('validation' if anchor_count < 1450
                                                  else 'development')
        for anchor in component:
            assigned[anchor] = split
        anchor_count += len(component)
    result = {key: [] for key in ('fit', 'validation', 'development')}
    for row in data:
        result[assigned[row['sentence1']]].append(row)
    pair_split = {}
    for split, group in result.items():
        for row in group:
            pair = tuple(sorted((row['sentence1'], row['sentence2'])))
            if pair in pair_split and pair_split[pair] != split:
                raise RuntimeError('Fuga de pareja invertida entre particiones')
            pair_split[pair] = split
    return result


def structural_features(first: str, second: str) -> dict[str, float]:
    one, two = tokens(first), tokens(second)
    c1, c2 = Counter(one), Counter(two)
    unique1, unique2 = set(one), set(two)
    common = unique1 & unique2
    positions2 = {word: index for index, word in enumerate(two)
                  if c1[word] == c2[word] == 1}
    aligned_pairs = [(index, positions2[word]) for index, word in enumerate(one)
                     if word in positions2]
    aligned = [position for _, position in aligned_pairs]
    possible = len(aligned) * (len(aligned) - 1) // 2
    inverted = sum(left > right for index, left in enumerate(aligned)
                   for right in aligned[index + 1:])
    adjacent = sum(right == left + 1 for left, right in zip(aligned, aligned[1:]))
    displacement = sum(abs(index / max(1, len(one) - 1) -
                           position / max(1, len(two) - 1))
                       for index, position in aligned_pairs)
    matcher = SequenceMatcher(None, one, two, autojunk=False)
    return {
        'set_overlap': len(common) / max(1, len(unique1 | unique2)),
        'multiset_overlap': sum(min(c1[word], c2[word]) for word in c1 | c2) /
                            max(1, sum(max(c1[word], c2[word]) for word in c1 | c2)),
        'length_ratio': min(len(one), len(two)) / max(1, len(one), len(two)),
        'unique_coverage': len(aligned) / max(1, len(common)),
        'lcs_ratio': matcher.ratio(),
        'inversion_fraction': inverted / max(1, possible),
        'adjacency_preserved': adjacent / max(1, len(aligned) - 1),
        'mean_displacement': displacement / max(1, len(aligned)),
    }


def values(data: list[dict]) -> list[tuple[dict[str, float], str]]:
    return [(structural_features(row['sentence1'], row['sentence2']), row['label'])
            for row in data]


def predicate(program: tuple, feature: dict[str, float]) -> bool:
    name, threshold, direction = program
    value = feature[name]
    return value > threshold if direction == 'gt' else value <= threshold


def predict(program: dict, feature: dict[str, float]) -> str | None:
    for rule in program['rules']:
        if predicate(rule['predicate'], feature):
            return rule['label']
    return program['default']


def metric(program: dict, data: list[tuple[dict[str, float], str]]) -> dict:
    per_label = Counter()
    correct = Counter()
    attempts = 0
    for feature, gold in data:
        per_label[gold] += 1
        answer = predict(program, feature)
        if answer is not None:
            attempts += 1
            correct[gold] += answer == gold
    total = len(data)
    good = sum(correct.values())
    return {'total': total, 'attempts': attempts, 'correct': good,
            'macro_accuracy': round(sum(correct[label] / max(1, per_label[label])
                                        for label in ('0', '1')) / 2, 6),
            'precision': round(good / attempts, 6) if attempts else None,
            'coverage': round(attempts / max(1, total), 6)}


def thresholds(data: list[tuple[dict[str, float], str]], names: tuple[str, ...]) -> list[tuple]:
    result = set()
    for name in names:
        ordered = sorted(feature[name] for feature, _ in data)
        for quantile in (0.1, 0.25, 0.5, 0.75, 0.9):
            value = ordered[min(len(ordered) - 1, int(quantile * len(ordered)))]
            for direction in ('gt', 'le'):
                result.add((name, value, direction))
    return sorted(result)


def rank(metric_: dict, program: dict) -> tuple:
    return (-metric_['macro_accuracy'], -(metric_['precision'] or 0),
            len(program['rules']), json.dumps(program, sort_keys=True))


def search(fit: list[tuple[dict[str, float], str]],
           validation: list[tuple[dict[str, float], str]],
           names: tuple[str, ...]) -> dict:
    started = time.process_time()
    predicates = thresholds(fit, names)
    majority = min(('0', '1'), key=lambda label: (-sum(gold == label for _, gold in fit),
                                                  label))
    stumps = []
    for pred in predicates:
        for label in ('0', '1'):
            for default in (None, '0', '1'):
                program = {'rules': [{'predicate': pred, 'label': label}],
                           'default': default}
                result = metric(program, fit)
                stumps.append((rank(result, program), program))
    stumps.sort(key=lambda item: item[0])
    # One rule is the complete first stage. The second stage combines only
    # distinct top predicates; this is a fixed search policy, not test tuning.
    candidates = [item[1] for item in stumps[:128]]
    seen = {json.dumps(item, sort_keys=True) for item in candidates}
    for _, first in stumps[:16]:
        for _, second in stumps[:16]:
            if first['rules'][0]['predicate'] == second['rules'][0]['predicate']:
                continue
            program = {'rules': [first['rules'][0], second['rules'][0]],
                       'default': majority}
            key = json.dumps(program, sort_keys=True)
            if key not in seen:
                candidates.append(program)
                seen.add(key)
            if len(candidates) == MAX_PROGRAMS:
                break
        if len(candidates) == MAX_PROGRAMS:
            break
    if len(candidates) > MAX_PROGRAMS:
        raise RuntimeError('Presupuesto de programas')
    best_safe = best_raw = None
    for program in candidates:
        result = metric(program, validation)
        ranked = rank(result, program)
        choice = (ranked, program, result)
        if best_raw is None or ranked < best_raw[0]:
            best_raw = choice
        if result['coverage'] >= 0.5 and (result['precision'] or 0) >= 0.8:
            if best_safe is None or ranked < best_safe[0]:
                best_safe = choice
    return {'features': list(names), 'predicates': len(predicates),
            'stumps_evaluated': len(stumps), 'programs_evaluated': len(candidates),
            'best_raw': {'program': best_raw[1], 'metric': best_raw[2]},
            'best_safe': {'program': best_safe[1], 'metric': best_safe[2]}
            if best_safe else None,
            'search_cpu_s': round(time.process_time() - started, 6)}


def majority_control(data: list[tuple[dict[str, float], str]]) -> dict:
    count = Counter(label for _, label in data)
    label = min(('0', '1'), key=lambda item: (-count[item], item))
    return {'rules': [], 'default': label}


def subset_score(program: dict, data: list[tuple[dict[str, float], str]],
                 kind: str) -> dict:
    if kind == 'high_overlap':
        picked = [row for row in data if row[0]['set_overlap'] >= 0.8]
    else:
        picked = [row for row in data if row[0]['set_overlap'] == 1.0 and
                  row[0]['multiset_overlap'] == 1.0 and
                  row[0]['lcs_ratio'] < 1.0]
    return metric(program, picked)


def main() -> None:
    wall = time.monotonic()
    cpu = time.process_time()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    source = rows()
    digest = sha256(json.dumps(source, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()).hexdigest()
    if digest != EXPECTED_SOURCE:
        raise RuntimeError('Fuente de datos cambió')
    parts = partition(source, tree)
    fit = values(parts['fit'])
    validation = values(parts['validation'])
    # Development stays unopened if validation does not meet the preregistered
    # precision/coverage gate in both treatment and its matched control.
    treatment = search(fit, validation, ORDERED)
    no_order = search(fit, validation, ORDER_BLIND)
    majority = majority_control(fit)
    control_val = metric(majority, validation)
    best = treatment['best_safe']
    control = no_order['best_safe'] or no_order['best_raw']
    candidate_gate = (best is not None and
                      best['metric']['macro_accuracy'] >= 0.75 and
                      best['metric']['macro_accuracy'] >=
                      control['metric']['macro_accuracy'] + 0.05 and
                      subset_score(best['program'], validation,
                                   'high_overlap')['macro_accuracy'] >=
                      subset_score(control['program'], validation,
                                   'high_overlap')['macro_accuracy'] + 0.05)
    development = None
    if candidate_gate:
        dev = values(parts['development'])
        treated = metric(best['program'], dev)
        baseline = metric(control['program'], dev)
        treated_high = subset_score(best['program'], dev, 'high_overlap')
        base_high = subset_score(control['program'], dev, 'high_overlap')
        treated_bag = subset_score(best['program'], dev, 'same_bag')
        base_bag = subset_score(control['program'], dev, 'same_bag')
        gate = (treated['macro_accuracy'] >= 0.75 and
                (treated['precision'] or 0) >= 0.8 and treated['coverage'] >= 0.5 and
                treated['macro_accuracy'] >= baseline['macro_accuracy'] + 0.05 and
                treated_high['macro_accuracy'] >= base_high['macro_accuracy'] + 0.05 and
                treated_bag['macro_accuracy'] >= base_bag['macro_accuracy'] - 0.05)
        development = {'treatment': treated, 'no_order': baseline,
                       'high_overlap_treatment': treated_high,
                       'high_overlap_no_order': base_high,
                       'same_bag_treatment': treated_bag,
                       'same_bag_no_order': base_bag, 'gate_passed': gate}
    unchanged = (git('rev-parse', 'HEAD:leobot') == tree and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {
        'preregistration': 'prereg/F-18-orden-relacional-espanol.md',
        'kind': 'development_only', 'source_revision': REVISION,
        'source_sha256': digest, 'engine_tree': tree, 'engine_unchanged': unchanged,
        'partition_rows': {name: len(part) for name, part in parts.items()},
        'partition_sentence1': {name: len({row['sentence1'] for row in part})
                                for name, part in parts.items()},
        'treatment': treatment, 'no_order': no_order,
        'majority_validation': control_val,
        'candidate_gate_passed': bool(candidate_gate),
        'development': development,
        'reserved_test': 'unopened',
        'english_transfer': 'pending_only_if_development_passes',
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'f18_order_dev.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({
        'partition_rows': output['partition_rows'],
        'treatment_best_raw': treatment['best_raw'],
        'treatment_best_safe': treatment['best_safe'],
        'no_order_best': control,
        'candidate_gate_passed': output['candidate_gate_passed'],
        'development': development,
        'cpu_total_s': output['cpu_total_s'],
        'wall_total_s': output['wall_total_s'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

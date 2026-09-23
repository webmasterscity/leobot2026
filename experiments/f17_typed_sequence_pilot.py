"""F-17 development pilot: one bounded sequence interpreter, two evidence types.

This file is outside the motor. Its programs are data; only the evaluator calls
the stdlib target functions to obtain observations.
"""
from __future__ import annotations

import json
import math
import random
import resource
import statistics
import time
from collections import defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from experiments.f14_revision_baselines import LABELS, groups, score
from experiments.f14_revision_dev import episodes
from experiments.f14_typed_edit_learner import TypedEditLearner, _tokens
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
MAX_CANDIDATES = 64


def scan(program: dict, record: dict) -> int:
    """Interpret a typed scan/fold description without executing generated code."""
    if set(program) != {'source', 'pattern', 'match', 'overlap', 'reduce'}:
        raise ValueError('Descripción inválida')
    source = record[program['source']]
    pattern = record[program['pattern']]
    if type(source) not in (str, tuple) or type(pattern) is not type(source):
        raise ValueError('Tipos de secuencia incompatibles')
    if program['match'] not in ('contiguous', 'item') or type(program['overlap']) is not bool:
        raise ValueError('Barrido inválido')
    if program['reduce'] not in ('count', 'first', 'last', 'any'):
        raise ValueError('Reductor inválido')
    if len(source) > 256 or len(pattern) > 256:
        raise ValueError('Presupuesto de secuencia agotado')
    if program['match'] == 'contiguous':
        positions = []
        cursor = 0
        step = 1 if program['overlap'] else max(1, len(pattern))
        while cursor <= len(source) - len(pattern):
            if source[cursor:cursor + len(pattern)] == pattern:
                positions.append(cursor)
                cursor += step
            else:
                cursor += 1
    else:
        wanted = set(pattern)
        positions = [index for index, item in enumerate(source) if item in wanted]
    reducer = program['reduce']
    if reducer == 'count':
        return len(positions)
    if reducer == 'first':
        return positions[0] if positions else -1
    if reducer == 'last':
        return positions[-1] if positions else -1
    return int(bool(positions))


def tool_programs() -> list[dict]:
    return [
        {'source': source, 'pattern': pattern, 'match': match,
         'overlap': overlap, 'reduce': reducer}
        for source, pattern in (('arg0', 'arg1'), ('arg1', 'arg0'))
        for match in ('contiguous', 'item')
        for overlap in (False, True)
        for reducer in ('count', 'first', 'last', 'any')
    ]


def language_programs() -> list[dict]:
    return [
        {'source': source, 'pattern': pattern, 'match': match,
         'overlap': False, 'reduce': reducer}
        for source in ('other_old', 'other_new', 'retained')
        for pattern in ('removed', 'added')
        for match in ('contiguous', 'item')
        for reducer in ('count', 'any')
    ]


def tool_rows(tree: str) -> list[tuple[dict, dict]]:
    seed = int(sha256((tree + ':F17:tool:dev').encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    rows = []
    for index in range(64):
        if index % 8 == 0:
            letter = rng.choice('abcde')
            text = letter * rng.randrange(2, 9)
            fragment = letter * rng.randrange(1, 4)
        else:
            text = ''.join(rng.choices('abcde', k=rng.randrange(3, 13)))
            mode = index % 4
            if mode == 0:
                fragment = ''
            elif mode == 1:
                start = rng.randrange(len(text))
                fragment = text[start:start + rng.randrange(1, 4)]
            else:
                fragment = ''.join(rng.choices('abcde', k=rng.randrange(1, 4)))
        record = {'arg0': text, 'arg1': fragment}
        # Only the external evaluator observes these actual tool outputs.
        rows.append((record, {'find': text.find(fragment),
                              'count': text.count(fragment)}))
    rng.shuffle(rows)
    return rows


def tool_learning(rows: list[tuple[dict, dict]]) -> dict:
    started = time.process_time()
    specs = tool_programs()
    if len(specs) > MAX_CANDIDATES:
        raise RuntimeError('Espacio fuera de presupuesto')
    report = {'candidates_available': len(specs), 'train': 32,
              'validation': 32, 'methods': {}}
    for target in ('find', 'count'):
        acquired = []
        for expression in specs:
            if all(scan(expression, row) == outputs[target]
                   for row, outputs in rows[:32]):
                acquired.append(expression)
        valid = [expression for expression in acquired
                 if all(scan(expression, row) == outputs[target]
                        for row, outputs in rows[32:])]
        times = []
        correct = attempted = 0
        for row, outputs in rows[32:]:
            tick = time.perf_counter()
            values = {scan(expression, row) for expression in valid}
            prediction = next(iter(values)) if len(values) == 1 else None
            times.append((time.perf_counter() - tick) * 1000)
            attempted += prediction is not None
            correct += prediction == outputs[target] if prediction is not None else 0
        report['methods'][target] = {
            'consistent_train': len(acquired),
            'consistent_validation': len(valid),
            'programs': valid, 'attempted': attempted,
            'correct': correct, 'validation_total': 32,
            'p50_ms': round(statistics.median(times), 6),
            'p95_ms': round(sorted(times)[(95 * len(times) + 99) // 100 - 1], 6),
        }
    report['search_cpu_s'] = round(time.process_time() - started, 6)
    return report


def edit_record(before: dict, after: dict) -> dict:
    removed, added, retained = [], [], []
    other_old, other_new = [], []
    for side in ('sentence1', 'sentence2'):
        old = _tokens(before[side])
        new = _tokens(after[side])
        if old == new:
            continue
        other = 'sentence2' if side == 'sentence1' else 'sentence1'
        other_old.extend(_tokens(before[other]))
        other_new.extend(_tokens(after[other]))
        for kind, a, b, c, d in SequenceMatcher(
                None, old, new, autojunk=False).get_opcodes():
            if kind == 'equal':
                retained.extend(old[a:b])
            else:
                removed.extend(old[a:b])
                added.extend(new[c:d])
    return {key: tuple(value) for key, value in (
        ('removed', removed), ('added', added), ('retained', retained),
        ('other_old', other_old), ('other_new', other_new))}


def language_learning(tree: str) -> dict:
    started = time.process_time()
    train, validation, _, _ = groups(tree)
    fit_rows = episodes(train)
    validation_rows = episodes(validation)
    base = TypedEditLearner(LABELS)
    base_fit = base.fit(fit_rows)
    previous = json.loads((ROOT / 'results_v3' / 'f14_margin_diagnostic.json').read_text())
    families = tuple(previous['best_raw_families'])
    specs = language_programs()
    if len(specs) > MAX_CANDIDATES:
        raise RuntimeError('Espacio fuera de presupuesto')
    fit_cpu = time.process_time() - started
    started_relations = time.process_time()
    evidence = defaultdict(set)
    for group, before, after, _ in fit_rows:
        record = edit_record(before, after)
        old, new = before['gold_label'], after['gold_label']
        for index, expression in enumerate(specs):
            bucket = min(2, scan(expression, record))
            evidence[(old, new, index, bucket)].add(group)
    weights = {}
    for old in LABELS:
        for index, expression in enumerate(specs):
            for bucket in (0, 1, 2):
                for label in LABELS:
                    positive = evidence[(old, label, index, bucket)]
                    negative = set().union(*(
                        evidence[(old, other, index, bucket)]
                        for other in LABELS if other != label))
                    if len(positive | negative) < 3:
                        continue
                    pos_total = len(base.group_counts[(old, label)])
                    neg_total = len(set().union(*(
                        base.group_counts[(old, other)]
                        for other in LABELS if other != label)))
                    odds = math.log((len(positive) + 1) / (pos_total + 2)) - math.log(
                        (len(negative) + 1) / (neg_total + 2))
                    weights[(old, index, bucket, label)] = max(-3.0, min(3.0, odds))
    relation_cpu = time.process_time() - started_relations
    started_validation = time.process_time()
    prepared = []
    for _, before, after, side in validation_rows:
        record = edit_record(before, after)
        buckets = [min(2, scan(expression, record)) for expression in specs]
        prior, parts = base._family_scores(before, after, side)
        prepared.append((before, after, side, buckets,
                         {label: prior[label] + sum(parts[f][label] for f in families)
                          for label in LABELS}))
    best_safe = best_raw = None
    candidates = 0
    for index, expression in enumerate(specs):
        for weight in (1.0, 2.0):
            for margin in (0.0, 1.0):
                candidates += 1
                predictions = []
                for before, after, side, buckets, baseline in prepared:
                    bucket = buckets[index]
                    ranking = sorted(((baseline[label] + weight * weights.get(
                        (before['gold_label'], index, bucket, label), 0.0), label)
                        for label in LABELS), key=lambda row: (-row[0], row[1]))
                    predicted = (ranking[0][1] if ranking[0][0] - ranking[1][0] > margin
                                 else None)
                    predictions.append((before, after, side, predicted))
                metric = score(predictions)
                rank = (-metric['macro_accuracy'], -metric['correct'], index, weight, margin)
                choice = {'expression': expression, 'weight': weight,
                          'margin': margin, 'metric': metric}
                if best_raw is None or rank < best_raw[0]:
                    best_raw = (rank, choice)
                if metric['coverage'] >= 0.5 and (metric['precision'] or 0) >= 0.8:
                    if best_safe is None or rank < best_safe[0]:
                        best_safe = (rank, choice)
    validation_cpu = time.process_time() - started_validation
    return {
        'groups_train': len(train), 'groups_validation': len(validation),
        'fit_edges': len(fit_rows), 'validation_edges': len(validation_rows),
        'base_fit': base_fit, 'base_families': list(families),
        'typed_expressions': len(specs), 'searched_descriptions': candidates,
        'best_safe': best_safe[1] if best_safe else None,
        'best_raw_diagnostic': best_raw[1],
        'fit_cpu_s': round(fit_cpu, 6),
        'relation_cpu_s': round(relation_cpu, 6),
        'validation_cpu_s': round(validation_cpu, 6),
    }


def main() -> None:
    started_cpu = time.process_time()
    started_wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    tools = tool_learning(tool_rows(tree))
    language = language_learning(tree)
    safe = language['best_safe']
    gate = (safe is not None and
            safe['metric']['macro_accuracy'] >= 0.675 and
            safe['metric']['same_label']['correct'] /
            max(1, safe['metric']['same_label']['total']) >= 0.9 and
            all(item['correct'] >= 31 and item['attempted'] >= 31
                for item in tools['methods'].values()))
    unchanged = (git('rev-parse', 'HEAD:leobot') == tree and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {
        'preregistration': 'prereg/F-17-sintesis-tipado-secuencias.md',
        'kind': 'development_only', 'engine_tree': tree,
        'engine_unchanged': unchanged, 'tool': tools, 'language': language,
        'development_gate_passed': bool(gate and unchanged),
        'reserved_human_test': 'unopened', 'reserved_tool_cases': 'ungenerated',
        'adversarial_persistence_transfer': 'pending_only_if_gate_passes',
        'cpu_total_s': round(time.process_time() - started_cpu, 6),
        'wall_total_s': round(time.monotonic() - started_wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'f17_typed_sequence_dev.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({
        'tool': {name: {key: item[key] for key in
                        ('consistent_train', 'consistent_validation', 'attempted', 'correct')}
                 for name, item in tools['methods'].items()},
        'language_best_safe': language['best_safe'],
        'language_best_raw': language['best_raw_diagnostic'],
        'development_gate_passed': output['development_gate_passed'],
        'cpu_total_s': output['cpu_total_s'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

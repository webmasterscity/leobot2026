"""F-19 development: induce variable role-order motifs from grouped contrasts."""
from __future__ import annotations

import json
import resource
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from experiments.f18_order_learner_dev import (
    EXPECTED_SOURCE, metric, partition, structural_features,
)
from experiments.f18_pawsx_inventory import rows as spanish_rows, tokens
from experiments.f19_english_contrast_inventory import page
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
MAX_MOTIFS = 256


def english_rows() -> list[dict]:
    inventory = json.loads((ROOT / 'results_v3' /
                            'f19_english_contrast_inventory.json').read_text())
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(page, inventory['sample_pages']))
    if any(total != inventory['source_total'] for _, _, total in fetched):
        raise RuntimeError('Fuente inglesa cambiante')
    result = [row for _, rows, _ in fetched for row in rows]
    digest = sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()).hexdigest()
    if digest != inventory['sample_sha256']:
        raise RuntimeError('Muestra inglesa cambió')
    return result


def document_frequency(rows: list[dict]) -> Counter:
    frequency = Counter()
    for row in rows:
        frequency.update(set(tokens(row['sentence1'])) | set(tokens(row['sentence2'])))
    return frequency


def motifs(first: str, second: str, frequency: Counter) -> set[tuple]:
    """Anti-unify symbol names; retain only typed variable-order relations."""
    one, two = tokens(first), tokens(second)
    if len(one) > 48 or len(two) > 48:
        return set()
    c1, c2 = Counter(one), Counter(two)
    positions = {word: index for index, word in enumerate(two)
                 if c1[word] == c2[word] == 1}
    aligned = [(index, positions[word], word) for index, word in enumerate(one)
               if word in positions]
    result = set()
    for index, (src_u, tgt_u, word_u) in enumerate(aligned):
        for src_v, tgt_v, word_v in aligned[index + 1:]:
            if tgt_u < tgt_v:
                continue
            class_u = 'common' if frequency[word_u] >= 5 else 'rare'
            class_v = 'common' if frequency[word_v] >= 5 else 'rare'
            gap = 'adjacent' if src_v - src_u == 1 else (
                'near' if src_v - src_u <= 3 else 'far')
            result.add(('pair', class_u, class_v, gap))
            for src_p, tgt_p, word_p in aligned[index + 1:]:
                if src_p >= src_v:
                    break
                if tgt_v < tgt_p < tgt_u:
                    class_p = 'common' if frequency[word_p] >= 5 else 'rare'
                    result.add(('bridge', class_u, class_p, class_v, gap))
    return result


def split_contrasts(rows: list[dict], tree: str) -> tuple[dict, dict, dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row['sentence1']].append(row)
    contrast = {anchor: examples for anchor, examples in groups.items()
                if {item['label'] for item in examples} == {'0', '1'}}
    ranked = sorted(contrast, key=lambda anchor: (
        sha256((tree + ':F19:en:' + anchor).encode()).hexdigest(), anchor))
    fit = {anchor: contrast[anchor] for anchor in ranked[:90]}
    valid = {anchor: contrast[anchor] for anchor in ranked[90:]}
    return fit, valid, groups


def acquire(fit: dict, frequency: Counter) -> tuple[list[dict], dict]:
    started = time.process_time()
    support = {'0': defaultdict(set), '1': defaultdict(set)}
    for anchor, examples in fit.items():
        by_label = {'0': set(), '1': set()}
        for row in examples:
            by_label[row['label']].update(motifs(anchor, row['sentence2'], frequency))
        for label, opposite in (('0', '1'), ('1', '0')):
            for motif in by_label[label] - by_label[opposite]:
                support[label][motif].add(anchor)
    proposals = []
    for motif in set(support['0']) | set(support['1']):
        zero = len(support['0'][motif])
        one = len(support['1'][motif])
        total = zero + one
        if total < 3 or max(zero, one) / total < 0.8:
            continue
        label = '0' if zero > one else '1'
        proposals.append({'motif': motif, 'label': label, 'support': max(zero, one),
                          'counter_support': min(zero, one)})
    proposals.sort(key=lambda row: (-row['support'] + row['counter_support'],
                                    row['counter_support'], len(row['motif']), row['motif']))
    if len(proposals) > MAX_MOTIFS:
        proposals = proposals[:MAX_MOTIFS]
    return proposals, {'contrast_groups': len(fit),
                       'raw_motifs': len(set(support['0']) | set(support['1'])),
                       'eligible_motifs': len(proposals),
                       'acquisition_cpu_s': round(time.process_time() - started, 6)}


def decide(found: set[tuple], program: list[dict], margin: int) -> str | None:
    votes = Counter()
    for row in program:
        if tuple(row['motif']) in found:
            votes[row['label']] += row['support'] - row['counter_support']
    if abs(votes['0'] - votes['1']) < margin or not sum(votes.values()):
        return None
    return '0' if votes['0'] > votes['1'] else '1'


def evaluate(rows: list[dict], frequency: Counter, program: list[dict],
             margin: int) -> dict:
    measures = Counter()
    total_by_label = Counter()
    answered_by_label = Counter()
    for row in rows:
        gold = row['label']
        found = motifs(row['sentence1'], row['sentence2'], frequency)
        answer = decide(found, program, margin)
        total_by_label[gold] += 1
        if answer is not None:
            measures['attempts'] += 1
            measures['correct'] += answer == gold
            answered_by_label[gold] += answer == gold
    total = len(rows)
    return {'total': total, 'attempts': measures['attempts'],
            'correct': measures['correct'],
            'precision': round(measures['correct'] / measures['attempts'], 6)
            if measures['attempts'] else None,
            'coverage': round(measures['attempts'] / max(1, total), 6),
            'macro_accuracy': round(sum(answered_by_label[label] /
                                        max(1, total_by_label[label])
                                        for label in ('0', '1')) / 2, 6)}


def choose(rows: list[dict], frequency: Counter, proposals: list[dict]) -> dict:
    started = time.process_time()
    best_safe = best_raw = None
    searched = 0
    for count in sorted({min(cap, len(proposals))
                         for cap in (8, 16, 32, 64, 128, 256)}):
        subset = proposals[:count]
        if not subset:
            break
        for margin in (1, 3, 5):
            result = evaluate(rows, frequency, subset, margin)
            searched += 1
            rank = (-result['macro_accuracy'], -(result['precision'] or 0),
                    count, margin)
            choice = (rank, count, margin, result)
            if best_raw is None or rank < best_raw[0]:
                best_raw = choice
            if result['coverage'] >= 0.5 and (result['precision'] or 0) >= 0.8:
                if best_safe is None or rank < best_safe[0]:
                    best_safe = choice
    def summarize(choice):
        return ({'max_motifs': choice[1], 'margin': choice[2],
                 'metric': choice[3]} if choice else None)
    return {'programs_searched': searched,
            'best_safe': summarize(best_safe), 'best_raw': summarize(best_raw),
            'validation_cpu_s': round(time.process_time() - started, 6)}


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    english = english_rows()
    fit, validation, all_groups = split_contrasts(english, tree)
    frequency = document_frequency(english)
    proposals, acquisition = acquire(fit, frequency)
    english_valid = [row for rows_ in validation.values() for row in rows_]
    selected = choose(english_valid, frequency, proposals)
    # The Spanish development and official test remain unopened unless both
    # visible selection gates pass. The visible Spanish validation is not a holdout.
    spanish = None
    english_gate = selected['best_safe'] is not None
    if english_gate:
        source = spanish_rows()
        digest = sha256(json.dumps(source, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':')).encode()).hexdigest()
        if digest != EXPECTED_SOURCE:
            raise RuntimeError('Fuente española cambió')
        parts = partition(source, tree)
        spanish_fit = parts['fit']
        spanish_validation = parts['validation']
        spanish_frequency = document_frequency(spanish_fit)
        # Apply the English-acquired variable motifs without Spanish labels.
        choice = selected['best_safe']
        english_prior = evaluate(spanish_validation, spanish_frequency,
                                 proposals[:choice['max_motifs']], choice['margin'])
        prior_f18 = json.loads((ROOT / 'results_v3' / 'f18_order_dev.json').read_text())
        old_program = prior_f18['treatment']['best_raw']['program']
        prepared = [(structural_features(row['sentence1'], row['sentence2']),
                     row['label']) for row in spanish_validation]
        old_result = metric(old_program, prepared)
        spanish = {'english_prior': english_prior, 'f18_baseline': old_result,
                   'visible_gate_passed': bool(
                       (english_prior['precision'] or 0) >= 0.8 and
                       english_prior['coverage'] >= 0.5 and
                       english_prior['macro_accuracy'] >= 0.763 and
                       english_prior['macro_accuracy'] >= old_result['macro_accuracy'] + 0.05)}
    unchanged = (git('rev-parse', 'HEAD:leobot') == tree and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {
        'preregistration': 'prereg/F-19-vinculos-de-roles-contrastivos.md',
        'kind': 'development_only', 'engine_tree': tree, 'engine_unchanged': unchanged,
        'english_rows': len(english), 'english_contrast_fit': len(fit),
        'english_contrast_validation': len(validation),
        'english_source_groups': len(all_groups),
        'english_validation_rows': len(english_valid),
        'acquisition': acquisition, 'promotable_motifs': proposals,
        'selection': selected, 'english_gate_passed': english_gate,
        'spanish_visible': spanish,
        'spanish_development': 'unopened', 'spanish_test': 'unopened',
        'transfer_test': 'pending_only_if_visible_gates_pass',
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'f19_role_binding_dev.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('promotable_motifs',)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

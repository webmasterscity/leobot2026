"""Read-only feasibility inventory for human-translated Spanish PAWS-X dev."""
from __future__ import annotations

import json
import re
import resource
import statistics
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
DATASET = 'google/xtreme'
REVISION = 'ec5f1f46e9af79639a90684a7a70a956c4998f04'
CONFIG = 'PAWS-X.es'


def tokens(text: str) -> list[str]:
    return re.findall(r'[^\W_]+', text.casefold())


def inversion_fraction(one: list[str], two: list[str]) -> float | None:
    """Count changed order among uniquely aligned words; no word identities in score."""
    first_counts, second_counts = Counter(one), Counter(two)
    positions = {word: index for index, word in enumerate(two)
                 if first_counts[word] == second_counts[word] == 1}
    aligned = [positions[word] for word in one if word in positions]
    total = len(aligned) * (len(aligned) - 1) // 2
    if not total:
        return None
    inversions = sum(left > right for index, left in enumerate(aligned)
                     for right in aligned[index + 1:])
    return inversions / total


def rows() -> list[dict]:
    result = []
    total = None
    while total is None or len(result) < total:
        query = urlencode({'dataset': DATASET, 'config': CONFIG,
                           'split': 'validation', 'revision': REVISION,
                           'offset': len(result), 'length': 100})
        with urlopen('https://datasets-server.huggingface.co/rows?' + query,
                     timeout=15) as response:
            page = json.load(response)
        if total is None:
            total = page['num_rows_total']
        if page['num_rows_total'] != total or not page['rows']:
            raise RuntimeError('Fuente incompleta o cambiante')
        result.extend(item['row'] for item in page['rows'])
    if len(result) != total:
        raise RuntimeError('Número de filas inconsistente')
    return result


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    data = rows()
    labels = Counter()
    same_bag = Counter()
    high_overlap = Counter()
    order_scores = defaultdict(list)
    anchors = defaultdict(lambda: defaultdict(int))
    pair_labels = defaultdict(set)
    for row in data:
        if set(row) != {'sentence1', 'sentence2', 'label'} or row['label'] not in ('0', '1'):
            raise RuntimeError('Formato inesperado de PAWS-X')
        first, second, label = row['sentence1'], row['sentence2'], row['label']
        labels[label] += 1
        one, two = tokens(first), tokens(second)
        same_words = Counter(one) == Counter(two) and one != two
        if same_words:
            same_bag[label] += 1
        union = set(one) | set(two)
        similar_words = bool(union and len(set(one) & set(two)) / len(union) >= 0.8)
        if similar_words:
            high_overlap[label] += 1
        inversion = inversion_fraction(one, two)
        if inversion is not None:
            order_scores[('all', label)].append(inversion)
            if similar_words:
                order_scores[('high_overlap', label)].append(inversion)
            if same_words:
                order_scores[('same_bag', label)].append(inversion)
        anchors[first][label] += 1
        pair_labels[(first, second)].add(label)
    contrast_anchors = [group for group in anchors.values()
                        if group['0'] and group['1']]
    source_digest = sha256(json.dumps(data, ensure_ascii=False,
                                      sort_keys=True, separators=(',', ':'))
                           .encode('utf8')).hexdigest()
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'source_feasibility_only', 'source': DATASET,
        'revision': REVISION, 'config': CONFIG, 'split': 'validation',
        'source_url': 'https://huggingface.co/datasets/google/xtreme',
        'engine_tree': tree, 'rows': len(data), 'canonical_sha256': source_digest,
        'labels': dict(labels), 'same_word_multiset_changed_order': dict(same_bag),
        'high_token_set_overlap_jaccard_ge_08': dict(high_overlap),
        'word_order_inversion': {
            subset: {label: {
                'count': len(order_scores[(subset, label)]),
                'median': round(statistics.median(order_scores[(subset, label)]), 6)
                if order_scores[(subset, label)] else None,
                'fraction_gt_025': round(sum(value > 0.25 for value in
                                            order_scores[(subset, label)]) /
                                         len(order_scores[(subset, label)]), 6)
                if order_scores[(subset, label)] else None,
            } for label in ('0', '1')}
            for subset in ('all', 'high_overlap', 'same_bag')
        },
        'distinct_sentence1': len(anchors),
        'sentence1_with_both_labels': len(contrast_anchors),
        'rows_on_contrast_sentence1': sum(sum(group.values()) for group in contrast_anchors),
        'identical_pairs_with_conflicting_labels': sum(len(values) > 1
                                                     for values in pair_labels.values()),
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'f18_pawsx_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

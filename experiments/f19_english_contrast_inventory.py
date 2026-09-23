"""Read-only sample of independent English PAWS-X train contrasts."""
from __future__ import annotations

import json
import random
import resource
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from experiments.f18_pawsx_inventory import DATASET, REVISION, tokens
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'PAWS-X.en'


def page(number: int) -> tuple[int, list[dict], int]:
    query = urlencode({'dataset': DATASET, 'config': CONFIG,
                       'split': 'train', 'revision': REVISION,
                       'offset': number * 100, 'length': 100})
    with urlopen('https://datasets-server.huggingface.co/rows?' + query,
                 timeout=15) as response:
        data = json.load(response)
    return number, [item['row'] for item in data['rows']], data['num_rows_total']


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    total = page(0)[2]
    rng = random.Random(int(sha256((tree + ':F19:en:inventory').encode())
                            .hexdigest()[:16], 16))
    selected = sorted(rng.sample(range((total + 99) // 100), 50))
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(page, selected))
    if any(size != total for _, _, size in fetched):
        raise RuntimeError('Fuente cambiante')
    data = [row for _, rows, _ in fetched for row in rows]
    labels = Counter()
    same_words = Counter()
    high_overlap = Counter()
    anchor = defaultdict(lambda: defaultdict(int))
    for row in data:
        if set(row) != {'sentence1', 'sentence2', 'label'} or row['label'] not in ('0', '1'):
            raise RuntimeError('Esquema inesperado')
        first, second, label = row['sentence1'], row['sentence2'], row['label']
        labels[label] += 1
        one, two = tokens(first), tokens(second)
        if Counter(one) == Counter(two) and one != two:
            same_words[label] += 1
        union = set(one) | set(two)
        if union and len(set(one) & set(two)) / len(union) >= 0.8:
            high_overlap[label] += 1
        anchor[first][label] += 1
    contrast = [values for values in anchor.values() if values['0'] and values['1']]
    digest = sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()).hexdigest()
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'source_feasibility_only', 'engine_tree': tree,
        'dataset': DATASET, 'revision': REVISION, 'config': CONFIG,
        'split': 'train', 'source_total': total,
        'sample_pages': selected, 'sample_rows': len(data),
        'sample_sha256': digest, 'labels': dict(labels),
        'same_word_multiset_changed_order': dict(same_words),
        'high_token_set_overlap_jaccard_ge_08': dict(high_overlap),
        'distinct_sentence1': len(anchor),
        'sentence1_with_both_labels': len(contrast),
        'rows_on_contrast_sentence1': sum(sum(group.values()) for group in contrast),
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'f19_english_contrast_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in output.items()
                      if key != 'sample_pages'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

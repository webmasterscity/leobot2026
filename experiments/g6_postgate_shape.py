"""Postgate diagnosis: coverage loss from grammar shape versus candidate ranking."""
from __future__ import annotations

import json
import random
import resource
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_denotation_feasibility import SEEDS, simple_gold
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch


ROOT = Path(__file__).resolve().parents[1]


def main():
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0:
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambiante')
    schema = {item['db_id']: item for item in json.loads(
        fetch(PREFIX + 'tables_es.json', 2_000_000))}
    selected = {item['db_id'] for item in json.loads((
        ROOT / 'results_v3' / 'g6_multispider_inventory.json').read_text())[
            'sampled_databases']}
    by_db = defaultdict(list)
    for row in json.loads(raw):
        if row['db_id'] in selected:
            by_db[row['db_id']].append(row)
    reports = []
    for seed in SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x6606)
        random_rows = []
        for db in sorted(selected):
            items = by_db[db]
            sampled = rng.sample(items, min(5, len(items)))
            random_rows.extend(sampled)
            used = {id(item) for item in sampled}
            simple = [item for item in items if id(item) not in used and
                      simple_gold(item, schema[db]) is not None]
            rng.sample(simple, min(5, len(simple)))
        reports.append({'seed': seed, 'random_tasks': len(random_rows),
                        'random_structurally_expressible': sum(
                            simple_gold(row, schema[row['db_id']]) is not None
                            for row in random_rows)})
    if git('rev-parse', 'HEAD:leobot') != h0:
        raise RuntimeError('Motor cambió')
    output = {'kind': 'postgate_diagnostic_only',
              'source_result': 'results_v3/g6_denotation_feasibility.json',
              'engine_tree': h0, 'reports': reports,
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3' / 'g6_postgate_shape.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

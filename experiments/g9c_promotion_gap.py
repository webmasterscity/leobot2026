"""Postgate diagnosis only: why did G-9c promote no lexical actions?"""
from __future__ import annotations

import json
import random
import resource
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g9_structure_gate import signature
from experiments.g9b_compositional_learner import SEEDS, components, educational_model


ROOT = Path(__file__).resolve().parents[1]


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambiada')
    by_db = defaultdict(dict)
    for row in json.loads(raw):
        by_db[row['db_id']].setdefault(row['query'].strip().casefold(), row)
    eligible = sorted(db for db, items in by_db.items() if len(items) >= 20)
    reports = []
    for seed in SEEDS:
        dbs = list(eligible)
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x69B)
        rng.shuffle(dbs)
        heldout = set(dbs[:max(20, round(.2*len(dbs)))])
        train = []
        for db in sorted(set(dbs)-heldout):
            for row in by_db[db].values():
                sig, _ = signature(row['sql'])
                train.append({'db_id': db, 'question': row['question'],
                              'signature': sig, 'fields': components(sig)})
        model = educational_model(train)
        reports.append({'seed': seed, 'education_examples': len(train),
                        'contrast_pairs': model['contrast_pairs'],
                        'candidate_rules': model['candidate_rules'],
                        'promoted_rules': model['promoted_rules'],
                        'gates': model['postgate_diagnostic']})
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    result = {'kind': 'postgate_diagnostic_only',
              'source_result': 'results_v3/g9c_learner_seed*_hashseed*.json',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'reports': reports,
              'cpu_total_s': round(time.process_time()-cpu0, 6),
              'wall_total_s': round(time.monotonic()-wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3/g9c_promotion_gap.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado en diagnóstico')


if __name__ == '__main__':
    main()

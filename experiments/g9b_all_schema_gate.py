"""G-9b preregistered structure recurrence across every eligible source DB."""
from __future__ import annotations

import json
import resource
import statistics
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g9_structure_gate import signature


ROOT = Path(__file__).resolve().parents[1]


def quantile(values, proportion):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * proportion))]


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del inventario')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambió')
    by_db = defaultdict(dict)
    for row in json.loads(raw):
        by_db[row['db_id']].setdefault(row['query'].strip().casefold(), row['sql'])
    eligible = {db: sqls for db, sqls in by_db.items() if len(sqls) >= 20}
    support = defaultdict(set)
    structures = {}
    action_count = {}
    for db, queries in sorted(eligible.items()):
        signatures = []
        for sql in queries.values():
            sig, count = signature(sql)
            signatures.append(sig)
            support[sig].add(db)
            action_count[sig] = count
        structures[db] = signatures
    repeated = {sig for sig, dbs in support.items() if len(dbs) >= 2}
    nontrivial_three = {sig for sig, dbs in support.items()
                        if len(dbs) >= 3 and action_count[sig] >= 2}
    per_db = {}
    for db, signatures in sorted(structures.items()):
        recurring = sum(sig in repeated for sig in signatures)
        difficult = sum(sig in nontrivial_three for sig in signatures)
        per_db[db] = {'distinct_sql': len(signatures),
                      'recurrent_sql': recurring,
                      'recurrent_fraction': recurring / len(signatures),
                      'nontrivial_3db_sql': difficult}
    fractions = [item['recurrent_fraction'] for item in per_db.values()]
    eligible_count = len(eligible)
    seventy = sum(value >= 0.70 for value in fractions)
    diverse = sum(item['nontrivial_3db_sql'] >= 5 for item in per_db.values())
    gate = (eligible_count >= 50 and len(nontrivial_three) >= 30 and
            seventy >= 0.70 * eligible_count and diverse >= 20)
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    result = {'kind': 'development_all_database_structure_gate',
              'preregistration': 'prereg/G-9b-estructuras-entre-todas-las-bases.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'source_databases': len(by_db), 'eligible_databases': eligible_count,
              'distinct_sql_eligible': sum(len(x) for x in eligible.values()),
              'distinct_signatures': len(support),
              'recurrent_signatures_2db': len(repeated),
              'nontrivial_signatures_3db': len(nontrivial_three),
              'bases_with_70pct_recurrence': seventy,
              'bases_with_5_nontrivial_3db_queries': diverse,
              'recurrent_fraction_min': min(fractions),
              'recurrent_fraction_p50': statistics.median(fractions),
              'recurrent_fraction_p95': quantile(fractions, .95),
              'exceptions_below_70pct': sorted(db for db, item in per_db.items()
                                                if item['recurrent_fraction'] < .70),
              'gate_pass': gate,
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3/g9b_all_schema_gate.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k != 'exceptions_below_70pct'}, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el ensayo')


if __name__ == '__main__':
    main()

"""G-9 preregistered source gate: reusable operator structure across databases."""
from __future__ import annotations

import json
import resource
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g7_relational_graph_gate import nested_sql


ROOT = Path(__file__).resolve().parents[1]


def signature(sql):
    selected = sql['select'][1]
    aggs = tuple(item[0] for item in selected)
    actions = {
        'join': len(sql['from']['table_units']) > 1,
        'filter': bool(sql['where']),
        'aggregate': any(agg != 0 for agg in aggs),
        'group': bool(sql['groupBy']),
        'order': bool(sql['orderBy']),
        'limit': sql['limit'] is not None,
        'nested': nested_sql(sql),
        'set': any(sql[key] is not None for key in ('union', 'intersect', 'except')),
    }
    return (len(selected), aggs, bool(sql['select'][0]),
            tuple(actions[key] for key in sorted(actions))), sum(actions.values())


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del inventario')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambió')
    chosen = {item['db_id'] for item in json.loads(
        (ROOT / 'results_v3/g6_multispider_inventory.json').read_text())['sampled_databases']}
    by_db = defaultdict(dict)
    for row in json.loads(raw):
        db = row['db_id']
        if db in chosen:
            by_db[db].setdefault(row['query'].strip().casefold(), row['sql'])
    support = defaultdict(set)
    by_db_signature = {}
    action_count = {}
    for db in sorted(chosen):
        signatures = []
        for sql in by_db[db].values():
            sig, count = signature(sql)
            signatures.append(sig)
            support[sig].add(db)
            action_count[sig] = count
        by_db_signature[db] = signatures
    recurrent = {sig for sig, dbs in support.items() if len(dbs) >= 2}
    nontrivial = {sig for sig in recurrent if action_count[sig] >= 2}
    per_db = {db: {'distinct_sql': len(by_db[db]),
                   'recurrent_queries': sum(sig in recurrent for sig in by_db_signature[db]),
                   'nontrivial_recurrent_queries': sum(sig in nontrivial
                                                       for sig in by_db_signature[db])}
              for db in sorted(chosen)}
    total = sum(len(by_db[db]) for db in chosen)
    gate = (total >= 120 and len(nontrivial) >= 20 and
            all(row['recurrent_queries'] >= 15 for row in per_db.values()))
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    result = {'kind': 'development_operator_structure_gate',
              'preregistration': 'prereg/G-9-gramatica-compositiva-con-demostraciones.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'distinct_sql_total': total,
              'distinct_signatures': len(support),
              'recurrent_signatures_2db': len(recurrent),
              'nontrivial_recurrent_signatures_2db': len(nontrivial),
              'per_database': per_db, 'gate_pass': gate,
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3/g9_structure_gate.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el ensayo')


if __name__ == '__main__':
    main()

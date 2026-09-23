"""G-7 preregistered source gate: can schema relations express real joins?"""
from __future__ import annotations

import itertools
import json
import random
import resource
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_denotation_feasibility import simple_gold
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (17, 53, 97)
LIMIT = 64


def edge(a, b):
    return tuple(sorted((a, b)))


def table_of(schema, column):
    return schema['column_names_original'][column][0]


def fk_edges(schema):
    return sorted({edge(a, b) for a, b in schema['foreign_keys']
                   if table_of(schema, a) >= 0 and table_of(schema, b) >= 0
                   and table_of(schema, a) != table_of(schema, b)})


def connected_paths(schema, edges):
    """No task labels or question words: connected acyclic one/two-edge facts."""
    paths = []
    for e in edges:
        paths.append((e,))
    for e1, e2 in itertools.combinations(edges, 2):
        tables = {table_of(schema, col) for e in (e1, e2) for col in e}
        if len(tables) == 3:
            paths.append((e1, e2))
    return paths[:LIMIT]


def flat_edges(schema):
    """Ablation: same schema, no FK constraint; allow same-typed column joins."""
    columns = schema['column_names_original']
    types = schema['column_types']
    return [edge(a, b) for a in range(1, len(columns))
            for b in range(a + 1, len(columns))
            if columns[a][0] != columns[b][0] and columns[a][0] >= 0
            and columns[b][0] >= 0 and types[a] == types[b]]


def nested_sql(value, root=True):
    if isinstance(value, dict):
        if not root and 'select' in value and 'from' in value:
            return True
        return any(nested_sql(v, False) for v in value.values())
    if isinstance(value, list):
        return any(nested_sql(v, False) for v in value)
    return False


def gold_path(row, schema):
    """Evaluator only. A rejected form stays in the coverage denominator."""
    sql = row['sql']
    units = sql['from']['table_units']
    if not 2 <= len(units) <= 3 or nested_sql(sql):
        return None, 'outside_table_or_subquery'
    if any(u[0] != 'table_unit' or type(u[1]) is not int for u in units):
        return None, 'non_table_unit'
    tables = {u[1] for u in units}
    if len(tables) != len(units):
        return None, 'repeated_table'
    conds = sql['from']['conds']
    if len(conds) != 2 * (len(tables) - 1) - 1:
        return None, 'non_tree_join'
    edges = []
    for position, cond in enumerate(conds):
        if position % 2:
            if cond != 'and':
                return None, 'non_conjunctive_join'
            continue
        if not isinstance(cond, list) or len(cond) != 5:
            return None, 'join_condition_form'
        neg, op, unit, rhs, extra = cond
        if neg or op != 2 or extra is not None or not isinstance(rhs, list):
            return None, 'non_equality_join'
        if (len(unit) != 3 or unit[0] != 0 or unit[2] is not None or
            len(unit[1]) != 3 or unit[1][0] != 0 or unit[1][2] or
            len(rhs) != 3 or rhs[0] != 0 or rhs[2]):
            return None, 'join_expression'
        a, b = unit[1][1], rhs[1]
        if type(a) is not int or type(b) is not int:
            return None, 'join_column_type'
        if {table_of(schema, a), table_of(schema, b)} - tables:
            return None, 'join_outside_tables'
        edges.append(edge(a, b))
    if len({table_of(schema, col) for e in edges for col in e}) != len(tables):
        return None, 'disconnected_join'
    return tuple(sorted(edges)), 'eligible'


def rank(paths, target):
    try:
        return paths.index(target) + 1
    except ValueError:
        return None


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del ensayo')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente de preguntas cambió')
    rows = json.loads(raw)
    raw_schema = fetch(PREFIX + 'tables_es.json', 2_000_000)
    if sha256(raw_schema).hexdigest() != '4f85a31a72fe94f0d7f2f657e39d783183198fd979aa922c1367512bd5745e5c':
        raise RuntimeError('Esquemas cambiaron')
    schemas = {x['db_id']: x for x in json.loads(raw_schema)}
    inventory = json.loads((ROOT / 'results_v3/g6_multispider_inventory.json').read_text())
    selected = {x['db_id'] for x in inventory['sampled_databases']}
    by_db = defaultdict(list)
    for row in rows:
        if row['db_id'] in selected:
            by_db[row['db_id']].append(row)
    candidates = {}
    for db in sorted(selected):
        schema = schemas[db]
        candidates[db] = (connected_paths(schema, fk_edges(schema)),
                          connected_paths(schema, flat_edges(schema)))
    reports = []
    for seed in SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x6606)
        eligible, graph_hit, flat_hit = 0, 0, 0
        reasons = defaultdict(int)
        positions = []
        for db in sorted(selected):
            items = by_db[db]
            random_sample = rng.sample(items, min(5, len(items)))
            used = {id(item) for item in random_sample}
            simple = [item for item in items if id(item) not in used and
                      simple_gold(item, schemas[db]) is not None]
            rng.sample(simple, min(5, len(simple)))  # Preserve G-6 sampling order.
            graph, flat = candidates[db]
            for row in random_sample:
                target, reason = gold_path(row, schemas[db])
                reasons[reason] += 1
                if target is None:
                    continue
                eligible += 1
                gp, fp = rank(graph, target), rank(flat, target)
                graph_hit += gp is not None
                flat_hit += fp is not None
                positions.append({'db': db, 'graph': gp, 'flat': fp})
        coverage = graph_hit / eligible if eligible else 0.0
        flat_coverage = flat_hit / eligible if eligible else 0.0
        reports.append({'seed': seed, 'random_questions': 40,
                        'eligible': eligible, 'graph_hit': graph_hit,
                        'flat_hit': flat_hit, 'graph_coverage': coverage,
                        'flat_coverage': flat_coverage, 'reasons': dict(reasons),
                        'positions': positions})
    # Renaming names while retaining relation IDs must leave both searches intact.
    renamed_ok = True
    for db in sorted(selected):
        original = schemas[db]
        renamed = dict(original)
        renamed['table_names_original'] = [f't{i}' for i in range(len(original['table_names_original']))]
        renamed['column_names_original'] = [(t, f'c{i}') for i, (t, _) in
                                            enumerate(original['column_names_original'])]
        renamed_ok &= (candidates[db][0] == connected_paths(renamed, fk_edges(renamed))
                       and candidates[db][1] == connected_paths(renamed, flat_edges(renamed)))
    total_eligible = sum(x['eligible'] for x in reports)
    pass_gate = (total_eligible >= 10 and all(
        r['eligible'] and r['graph_coverage'] >= 0.70 and
        (r['graph_coverage'] - r['flat_coverage'] >= 0.20 or
         (r['graph_hit'] and r['flat_hit'] and
          sorted(p['graph'] for p in r['positions'] if p['graph'])[r['graph_hit']//2] * 2
          <= sorted(p['flat'] for p in r['positions'] if p['flat'])[r['flat_hit']//2]))
        for r in reports) and renamed_ok)
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    result = {'kind': 'development_join_graph_gate', 'preregistration':
              'prereg/G-7-grafos-relacionales.md', 'engine_tree': h0,
              'engine_unchanged': unchanged, 'renamed_same': renamed_ok,
              'gate_pass': pass_gate, 'reports': reports,
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3/g7_relational_graph_gate.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'reports'}))
    for r in reports:
        print(json.dumps({k: v for k, v in r.items() if k != 'positions'}))
    if not unchanged:
        raise RuntimeError('Motor alterado durante ensayo')


if __name__ == '__main__':
    main()

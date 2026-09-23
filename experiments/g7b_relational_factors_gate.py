"""G-7b: preregistered factored representation gate on source questions."""
from __future__ import annotations

import json
import math
import random
import re
import resource
import sqlite3
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_denotation_feasibility import (
    candidate_values, column_values, score_names, simple_gold,
)
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g7_relational_graph_gate import (
    LIMIT as JOIN_LIMIT, connected_paths, fk_edges, flat_edges, gold_path,
    nested_sql,
)


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (17, 53, 97)
CAPS = {'join': JOIN_LIMIT, 'projection': 256, 'filter': 512,
        'group': 64, 'order': 64, 'limit': 16}
MAX_FRAGMENTS = sum(CAPS.values())
OPS = (2, 3, 4, 5, 6, 7)
AGGS = (0, 1, 2, 3, 4, 5)


def normalize_value(value):
    if type(value) is str:
        return value.strip().strip("\"'").casefold()
    return value


def column_unit(item):
    if not isinstance(item, list) or len(item) != 3:
        return None
    agg, col, distinct = item
    if type(agg) is not int or type(col) is not int or type(distinct) is not bool:
        return None
    return col, agg, distinct


def value_unit(item):
    if not isinstance(item, list) or len(item) != 3 or item[0] != 0 or item[2] is not None:
        return None
    return column_unit(item[1])


def gold_factors(row, schema):
    """Evaluator only: parse a bounded subset of the published SQL AST."""
    sql = row['sql']
    if nested_sql(sql) or sql['having'] or any(sql[k] is not None for k in
                                       ('union', 'intersect', 'except')):
        return None, 'nested_having_or_set'
    units = sql['from']['table_units']
    if len(units) == 1 and units[0][0] == 'table_unit' and type(units[0][1]) is int:
        if sql['from']['conds']:
            return None, 'single_table_join_condition'
        relation = ('table', units[0][1])
    else:
        path, reason = gold_path(row, schema)
        if path is None:
            return None, reason
        relation = ('path', path)
    query_distinct, selected = sql['select']
    if type(query_distinct) is not bool or not 1 <= len(selected) <= 3:
        return None, 'projection_arity'
    projections = []
    for item in selected:
        if not isinstance(item, list) or len(item) != 2 or item[0] not in AGGS:
            return None, 'projection_form'
        inner = value_unit(item[1])
        if inner is None or inner[1] != 0:
            return None, 'projection_expression'
        projections.append((inner[0], item[0], inner[2]))
    where = sql['where']
    if len(where) not in (0, 1, 3):
        return None, 'filter_count'
    filters = []
    connector = None
    for position, cond in enumerate(where):
        if position % 2:
            if cond not in ('and', 'or'):
                return None, 'filter_connector'
            connector = cond
            continue
        if not isinstance(cond, list) or len(cond) != 5:
            return None, 'filter_form'
        neg, op, unit, scalar, extra = cond
        inner = value_unit(unit)
        if neg or op not in OPS or inner is None or inner[1:] != (0, False) or extra is not None:
            return None, 'filter_expression'
        if type(scalar) not in (str, int, float):
            return None, 'filter_non_scalar'
        filters.append((inner[0], op, normalize_value(scalar)))
    if len(sql['groupBy']) > 2:
        return None, 'group_arity'
    groups = []
    for item in sql['groupBy']:
        unit = column_unit(item)
        if unit is None or unit[1:] != (0, False):
            return None, 'group_expression'
        groups.append(unit[0])
    order = sql['orderBy']
    ordered = None
    if order:
        if (not isinstance(order, list) or len(order) != 2 or
            order[0] not in ('asc', 'desc') or len(order[1]) != 1):
            return None, 'order_arity'
        inner = value_unit(order[1][0])
        if inner is None or inner[2]:
            return None, 'order_expression'
        ordered = (inner[0], inner[1], order[0])
    limit = sql['limit']
    if limit is not None and (type(limit) is not int or limit < 1):
        return None, 'limit_form'
    return {'relation': relation, 'projections': projections,
            'filters': filters, 'connector': connector, 'groups': groups,
            'order': ordered, 'limit': limit, 'distinct': query_distinct}, 'admitted'


def proposed_factors(question, schema, observed, graph=True):
    """No SQL gold enters this generator. Search budget counts fragments."""
    columns = schema['column_names']
    originals = schema['column_names_original']
    scores = {col: score_names(question, name) if col else 0
              for col, (_, name) in enumerate(columns)}
    table_scores = {t: score_names(question, name)
                    for t, name in enumerate(schema['table_names'])}
    edges = fk_edges(schema) if graph else flat_edges(schema)
    joins = [('table', t) for t in range(len(schema['table_names']))]
    joins += [('path', path) for path in connected_paths(schema, edges)]
    joins.sort(key=lambda item: (
        -sum(table_scores[t] for t in (
            [item[1]] if item[0] == 'table' else
            {originals[c][0] for e in item[1] for c in e})),
        item[0] != 'table', repr(item)))
    joins = joins[:CAPS['join']]

    projections = []
    for col in range(len(columns)):
        for agg in AGGS:
            if col == 0 and agg != 3:
                continue
            if agg in (4, 5) and col and schema['column_types'][col] != 'number':
                continue
            for distinct in (False, True):
                projections.append((col, agg, distinct))
    projections.sort(key=lambda item: (-scores[item[0]], item[1] != 0,
                                       item[2], item))
    projections = projections[:CAPS['projection']]

    filters = []
    for col in range(1, len(columns)):
        if originals[col][0] < 0:
            continue
        values = candidate_values(question, col, observed)
        for value in values:
            for op in OPS:
                filters.append((col, op, normalize_value(value)))
    filters.sort(key=lambda item: (-scores[item[0]],
                                   item[1] != 2, item[0], item[1],
                                   repr(item[2])))
    filters = filters[:CAPS['filter']]

    groups = sorted(range(1, len(columns)), key=lambda col: (-scores[col], col))
    groups = groups[:CAPS['group']]
    orders = [(col, agg, direction)
              for col in range(1, len(columns))
              for agg in AGGS
              for direction in ('asc', 'desc')]
    orders.sort(key=lambda item: (-scores[item[0]], item[1] != 0,
                                  item[0], item[1], item[2]))
    orders = orders[:CAPS['order']]
    limits = [1]
    for raw in re.findall(r'(?<!\w)\d+(?!\w)', question):
        value = int(raw)
        if value > 0 and value not in limits:
            limits.append(value)
    return {'join': joins, 'projection': projections, 'filter': filters,
            'group': groups, 'order': orders, 'limit': limits[:CAPS['limit']]}


def coverage(gold, proposals):
    missing = []
    if gold['relation'] not in proposals['join']:
        missing.append('join')
    for name, key in (('projections', 'projection'), ('filters', 'filter'),
                      ('groups', 'group')):
        if any(part not in proposals[key] for part in gold[name]):
            missing.append(key)
    if gold['order'] is not None and gold['order'] not in proposals['order']:
        missing.append('order')
    if gold['limit'] is not None and gold['limit'] not in proposals['limit']:
        missing.append('limit')
    return not missing, sorted(set(missing))


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor cambió antes del ensayo')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Preguntas cambiaron')
    rows = json.loads(raw)
    raw_schema = fetch(PREFIX + 'tables_es.json', 2_000_000)
    if sha256(raw_schema).hexdigest() != '4f85a31a72fe94f0d7f2f657e39d783183198fd979aa922c1367512bd5745e5c':
        raise RuntimeError('Esquemas cambiaron')
    schemas = {s['db_id']: s for s in json.loads(raw_schema)}
    inventory = json.loads((ROOT / 'results_v3/g6_multispider_inventory.json').read_text())
    selected = {s['db_id']: s for s in inventory['sampled_databases']}
    by_db = defaultdict(list)
    for row in rows:
        if row['db_id'] in selected:
            by_db[row['db_id']].append(row)
    observed = {}
    renamed_structure_same = True
    for db, metadata in sorted(selected.items()):
        blob = fetch('dataset/spider/database/' + db + '/' + db + '.sqlite', 512_000)
        if sha256(blob).hexdigest() != metadata['sqlite_sha256']:
            raise RuntimeError('Datos cambiaron')
        conn = sqlite3.connect(':memory:')
        conn.deserialize(blob)
        conn.execute('PRAGMA query_only=ON')
        observed[db] = column_values(conn, schemas[db])
        conn.close()
        schema = schemas[db]
        renamed = dict(schema)
        renamed['table_names'] = [f't{i}' for i in range(len(schema['table_names']))]
        renamed['table_names_original'] = list(renamed['table_names'])
        renamed['column_names'] = [(t, f'c{i}') for i, (t, _) in
                                   enumerate(schema['column_names'])]
        renamed['column_names_original'] = list(renamed['column_names'])
        renamed_structure_same &= (
            fk_edges(schema) == fk_edges(renamed) and
            flat_edges(schema) == flat_edges(renamed) and
            proposed_factors('', schema, observed[db]) ==
            proposed_factors('', renamed, observed[db]))
    reports = []
    for seed in SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x6606)
        counts = Counter()
        missing = Counter()
        unsupported = Counter()
        candidates = 0
        composition_log10 = []
        for db in sorted(selected):
            items = by_db[db]
            random_sample = rng.sample(items, min(5, len(items)))
            used = {id(item) for item in random_sample}
            simple = [item for item in items if id(item) not in used and
                      simple_gold(item, schemas[db]) is not None]
            rng.sample(simple, min(5, len(simple)))  # Match G-6/G-7 order.
            for row in random_sample:
                counts['questions'] += 1
                gold, reason = gold_factors(row, schemas[db])
                if gold is None:
                    unsupported[reason] += 1
                    continue
                counts['shape_admitted'] += 1
                q = row['question']
                treatment = proposed_factors(q, schemas[db], observed[db])
                ablated = proposed_factors(q, schemas[db], observed[db], graph=False)
                no_text = proposed_factors('', schemas[db], observed[db])
                candidates += sum(len(values) for values in treatment.values())
                got, absent = coverage(gold, treatment)
                abl_got, _ = coverage(gold, ablated)
                textless_got, _ = coverage(gold, no_text)
                counts['covered'] += got
                counts['ablated_covered'] += abl_got
                counts['no_text_covered'] += textless_got
                multitable = gold['relation'][0] == 'path'
                counts['multi_admitted'] += multitable
                counts['multi_covered'] += got and multitable
                for part in absent:
                    missing[part] += 1
                if got:
                    # This is a warning on combining independently present
                    # fragments, not a claim that any full plan was tested.
                    factors = [len(treatment['join']),
                               len(treatment['projection']) ** len(gold['projections']),
                               max(1, len(treatment['filter'])) ** len(gold['filters']),
                               max(1, len(treatment['group'])) ** len(gold['groups']),
                               len(treatment['order']) if gold['order'] else 1,
                               len(treatment['limit']) if gold['limit'] else 1]
                    composition_log10.append(sum(math.log10(max(1, n)) for n in factors))
        counts = dict(counts)
        gate = (counts.get('covered', 0) >= 20 and
                counts.get('multi_covered', 0) >= 8 and
                counts.get('covered', 0) - counts.get('ablated_covered', 0) >= 8)
        reports.append({'seed': seed, 'counts': counts, 'unsupported': dict(unsupported),
                        'missing_fragments': dict(missing),
                        'candidate_fragments': candidates,
                        'median_log10_combinations_when_covered':
                        sorted(composition_log10)[len(composition_log10)//2]
                        if composition_log10 else None,
                        'gate_pass': gate})
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'kind': 'development_factored_representation_gate',
              'preregistration': 'prereg/G-7b-composicion-de-hechos-relacionales.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'renamed_structure_same': renamed_structure_same,
              'gate_pass': all(r['gate_pass'] for r in reports),
              'reports': reports, 'max_fragments_per_question': MAX_FRAGMENTS,
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3/g7b_relational_factors_gate.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el ensayo')


if __name__ == '__main__':
    main()

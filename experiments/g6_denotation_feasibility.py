"""G-6 preregistered source gate: can a safe relational DSL cover real questions?"""
from __future__ import annotations

import json
import random
import re
import resource
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import (
    BASE, PREFIX, TRAIN_SHA, fetch,
)
from hashlib import sha256


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (17, 53, 97)
MAX_CANDIDATES = 1000
OPS = (2, 3, 4, 5, 6, 7)
AGGS = (0, 3, 1, 2, 4, 5)


def question_tokens(text):
    return frozenset(re.findall(r'[^\W_]+', text.casefold()))


def quote_ident(name):
    return '"' + name.replace('"', '""') + '"'


def simple_gold(row, schema):
    sql = row['sql']
    units = sql['from']['table_units']
    if (len(units) != 1 or units[0][0] != 'table_unit' or
        sql['from']['conds'] or sql['groupBy'] or sql['having'] or
        sql['orderBy'] or sql['limit'] is not None or
        any(sql[key] is not None for key in ('union', 'intersect', 'except'))):
        return None
    table = units[0][1]
    if type(table) is not int or not 0 <= table < len(schema['table_names_original']):
        return None
    distinct, selected = sql['select']
    if distinct or len(selected) != 1:
        return None
    agg, val_unit = selected[0]
    if agg not in AGGS or val_unit[0] != 0 or val_unit[2] is not None:
        return None
    col_agg, sel_col, col_distinct = val_unit[1]
    if col_agg or col_distinct or type(sel_col) is not int:
        return None
    if not 0 <= sel_col < len(schema['column_names_original']):
        return None
    if schema['column_names_original'][sel_col][0] not in (-1, table):
        return None
    if sel_col == 0 and agg not in (3,):
        return None
    where = sql['where']
    if not where:
        return table, sel_col, agg, None, None, None
    if len(where) != 1 or not isinstance(where[0], list):
        return None
    negated, op, unit, value, other = where[0]
    if (negated or op not in OPS or unit[0] != 0 or unit[2] is not None or
        other is not None or type(value) not in (str, int, float)):
        return None
    inner_agg, filter_col, inner_distinct = unit[1]
    if (inner_agg or inner_distinct or type(filter_col) is not int or
        not 0 <= filter_col < len(schema['column_names_original']) or
        schema['column_names_original'][filter_col][0] != table):
        return None
    return table, sel_col, agg, filter_col, op, value


def column_values(conn, schema):
    values = defaultdict(list)
    for col_id, (table_id, col_name) in enumerate(schema['column_names_original']):
        if table_id < 0 or not col_name or col_name == '*':
            continue
        table_name = schema['table_names_original'][table_id]
        sql = (f'SELECT DISTINCT {quote_ident(col_name)} FROM '
               f'{quote_ident(table_name)} LIMIT 500')
        try:
            values[col_id] = [row[0] for row in conn.execute(sql)
                              if type(row[0]) in (str, int, float)]
        except sqlite3.Error:
            pass
    return values


def candidate_values(question, column_id, observed):
    number_values = []
    for word in re.findall(r'(?<!\w)-?\d+(?:\.\d+)?(?!\w)', question):
        value = float(word) if '.' in word else int(word)
        if value not in number_values:
            number_values.append(value)
    text_values = []
    lowered = question.casefold()
    for value in observed.get(column_id, ()):
        if type(value) is str and len(value) >= 2 and re.search(
                r'(?<!\w)' + re.escape(value.casefold()) + r'(?!\w)', lowered):
            if value not in text_values:
                text_values.append(value)
    return (number_values + text_values)[:16]


def score_names(question, name):
    a = question_tokens(question)
    b = question_tokens(name)
    return len(a & b) / max(1, len(b))


def proposals(question, schema, observed):
    """Only text, schema and observed cells enter this generator; no gold SQL."""
    choices = []
    considered = 0
    for table, (spanish, original) in enumerate(zip(schema['table_names'],
                                                    schema['table_names_original'])):
        table_cols = [i for i, (t, _) in enumerate(schema['column_names_original'])
                      if t == table]
        if not table_cols:
            continue
        table_score = score_names(question, spanish)
        for sel_col in [0, *table_cols]:
            sel_name = (schema['column_names'][sel_col][1]
                        if sel_col else '')
            sel_score = score_names(question, sel_name)
            for agg_rank, agg in enumerate(AGGS):
                if sel_col == 0 and agg != 3:
                    continue
                if (agg in (4, 5) and sel_col and
                    schema['column_types'][sel_col] != 'number'):
                    continue
                base = (table, sel_col, agg, None, None, None)
                score = 4 * table_score + 2 * sel_score - 0.05 * agg_rank
                choices.append((score, base))
                considered += 1
                for filter_col in table_cols:
                    filter_score = score_names(question,
                                               schema['column_names'][filter_col][1])
                    for value in candidate_values(question, filter_col, observed):
                        for op_rank, op in enumerate(OPS):
                            program = (table, sel_col, agg, filter_col, op, value)
                            choices.append((score + 2 * filter_score + 0.5 -
                                            0.02 * op_rank, program))
                            considered += 1
    # Sort by evidence from question/schema, then structural complexity and
    # canonical representation; answer denotations never rank programs.
    ranked = sorted(choices, key=lambda item: (-item[0],
                                                item[1][3] is not None,
                                                repr(item[1])))
    return [item[1] for item in ranked[:MAX_CANDIDATES]], considered


def equivalent(candidate, gold):
    if candidate[:5] != gold[:5]:
        return False
    a, b = candidate[5], gold[5]
    return (a == b if type(a) in (int, float) and type(b) in (int, float)
            else type(a) is type(b) and a == b)


def main():
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambiante')
    rows = json.loads(raw)
    schema_raw = fetch(PREFIX + 'tables_es.json', 2_000_000)
    schemas = {item['db_id']: item for item in json.loads(schema_raw)}
    inventory = json.loads((ROOT / 'results_v3' / 'g6_multispider_inventory.json').read_text())
    selected = {item['db_id']: item for item in inventory['sampled_databases']}
    db_rows = defaultdict(list)
    for row in rows:
        if row['db_id'] in selected:
            db_rows[row['db_id']].append(row)
    connections = {}
    observed = {}
    for db, metadata in selected.items():
        blob = fetch('dataset/spider/database/' + db + '/' + db + '.sqlite',
                     512_000)
        if sha256(blob).hexdigest() != metadata['sqlite_sha256']:
            raise RuntimeError('Base de datos cambiante')
        conn = sqlite3.connect(':memory:')
        conn.deserialize(blob)
        conn.execute('PRAGMA query_only=ON')
        connections[db] = conn
        observed[db] = column_values(conn, schemas[db])
    reports = []
    for seed in SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x6606)
        tasks = []
        for db in sorted(selected):
            items = db_rows[db]
            random_sample = rng.sample(items, min(5, len(items)))
            used = {id(item) for item in random_sample}
            simple = [item for item in items if id(item) not in used and
                      simple_gold(item, schemas[db]) is not None]
            easy_sample = rng.sample(simple, min(5, len(simple)))
            for stratum, item in ([('random', item) for item in random_sample] +
                                  [('simple', item) for item in easy_sample]):
                programs, considered = proposals(item['question'], schemas[db],
                                                 observed[db])
                gold = simple_gold(item, schemas[db])
                tasks.append({'db_id': db, 'stratum': stratum,
                              'structurally_simple': gold is not None,
                              'enumerated': len(programs),
                              'considered': considered,
                              'gold_in_candidates': bool(gold and any(
                                  equivalent(candidate, gold)
                                  for candidate in programs))})
        reports.append({'seed': seed, 'tasks': len(tasks),
                        'random_tasks': sum(t['stratum'] == 'random' for t in tasks),
                        'simple_tasks': sum(t['stratum'] == 'simple' for t in tasks),
                        'random_gold_covered': sum(t['gold_in_candidates']
                                                   for t in tasks if t['stratum'] == 'random'),
                        'simple_gold_covered': sum(t['gold_in_candidates']
                                                   for t in tasks if t['stratum'] == 'simple'),
                        'total_gold_covered': sum(t['gold_in_candidates'] for t in tasks),
                        'candidate_evaluations': sum(t['considered'] for t in tasks),
                        'gate1_pass': bool(sum(t['gold_in_candidates'] for t in tasks) >= 30 and
                                           sum(t['gold_in_candidates'] for t in tasks
                                               if t['stratum'] == 'random') >= 10),
                        'per_database': {db: {'sampled': sum(t['db_id'] == db for t in tasks),
                                              'covered': sum(t['gold_in_candidates'] for t in tasks
                                                             if t['db_id'] == db)}
                                         for db in sorted(selected)}})
    for conn in connections.values():
        conn.close()
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'preregistration': 'prereg/G-6-denotaciones-e-intervenciones-tablas.md',
              'kind': 'development_expressibility_gate_only',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'source_revision': inventory['source_revision'],
              'sampled_databases': sorted(selected), 'max_programs_per_question': MAX_CANDIDATES,
              'reports': reports, 'all_gate1_pass': bool(unchanged and all(
                  report['gate1_pass'] for report in reports)),
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3' / 'g6_denotation_feasibility.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

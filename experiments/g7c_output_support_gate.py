"""G-7c preregistered gate: prune direct projections by output support."""
from __future__ import annotations

import json
import random
import re
import resource
import sqlite3
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_denotation_feasibility import quote_ident, simple_gold
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g7b_relational_factors_gate import gold_factors


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (31, 71, 127)
PREVIOUS = (17, 53, 97)
MAX_CANDIDATES = 1000
MAX_ROWS = 100
MAX_DOMAIN_ROWS = 5000


def canon(value):
    if type(value) is str:
        return value.casefold()
    if type(value) in (int, float, bytes, type(None)):
        return value
    return repr(value)


def query_rows(conn, sql, max_rows=MAX_ROWS):
    clean = sql.strip().rstrip(';').strip()
    if not re.match(r'(?is)^(select|with)\b', clean) or ';' in clean or len(clean) > 20_000:
        return None
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    conn.set_authorizer(lambda action, a, b, database, trigger:
                        sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    ticks = [0]
    def limit_steps():
        ticks[0] += 1
        return ticks[0] >= 1000
    conn.set_progress_handler(limit_steps, 1000)
    try:
        return conn.execute(clean).fetchmany(max_rows + 1)
    except sqlite3.Error:
        return None
    finally:
        conn.set_progress_handler(None, 0)
        conn.set_authorizer(None)


def source_domains(conn, schema):
    """Unknown domains stay unpruned; no incomplete sample can reject gold."""
    domains = {}
    for col, (table, name) in enumerate(schema['column_names_original']):
        if table < 0:
            continue
        sql = ('SELECT DISTINCT ' + quote_ident(name) + ' FROM ' +
               quote_ident(schema['table_names_original'][table]))
        rows = query_rows(conn, sql, MAX_DOMAIN_ROWS)
        domains[col] = None if rows is None or len(rows) > MAX_DOMAIN_ROWS else {
            canon(row[0]) for row in rows}
    return domains


def output_support(answer, domains, schema):
    """Only answer and input-column facts enter; no task text or gold SQL."""
    arity = len(answer[0])
    cols = [i for i, (table, _) in enumerate(schema['column_names_original'])
            if table >= 0]
    if len(cols) * arity > MAX_CANDIDATES:
        return None
    output_domains = [{canon(row[position]) for row in answer}
                      for position in range(arity)]
    return [{col for col in cols
             if domains.get(col) is None or values <= domains[col]}
            for values in output_domains]


def prior_samples(by_db, schemas, h0):
    used = set()
    for seed in PREVIOUS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x6606)
        for db in sorted(by_db):
            items = by_db[db]
            selected = rng.sample(items, min(5, len(items)))
            used.update((db, row['question'], row['query']) for row in selected)
            ids = {id(row) for row in selected}
            simple = [row for row in items if id(row) not in ids and
                      simple_gold(row, schemas[db]) is not None]
            rng.sample(simple, min(5, len(simple)))
    return used


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del ensayo')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Preguntas cambiaron')
    rows = json.loads(raw)
    schema_raw = fetch(PREFIX + 'tables_es.json', 2_000_000)
    if sha256(schema_raw).hexdigest() != '4f85a31a72fe94f0d7f2f657e39d783183198fd979aa922c1367512bd5745e5c':
        raise RuntimeError('Esquemas cambiaron')
    schemas = {s['db_id']: s for s in json.loads(schema_raw)}
    inventory = json.loads((ROOT / 'results_v3/g6_multispider_inventory.json').read_text())
    selected = {s['db_id']: s for s in inventory['sampled_databases']}
    by_db = defaultdict(list)
    for row in rows:
        if row['db_id'] in selected:
            by_db[row['db_id']].append(row)
    old = prior_samples(by_db, schemas, h0)
    reading_cpu = time.process_time() - cpu0
    connections, domains = {}, {}
    domain_cpu0 = time.process_time()
    for db, metadata in sorted(selected.items()):
        blob = fetch('dataset/spider/database/' + db + '/' + db + '.sqlite', 512_000)
        if sha256(blob).hexdigest() != metadata['sqlite_sha256']:
            raise RuntimeError('Base cambiada')
        conn = sqlite3.connect(':memory:')
        conn.deserialize(blob)
        conn.execute('PRAGMA query_only=ON')
        connections[db] = conn
        domains[db] = source_domains(conn, schemas[db])
    domain_cpu = time.process_time() - domain_cpu0
    reports = []
    for seed in SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x67C)
        examples = []
        counts = Counter()
        execution_cpu = 0.0
        pruning_cpu = 0.0
        for db in sorted(selected):
            available = [row for row in by_db[db]
                         if (db, row['question'], row['query']) not in old]
            sample = rng.sample(available, min(5, len(available)))
            for row in sample:
                counts['sampled'] += 1
                gold, reason = gold_factors(row, schemas[db])
                if gold is None:
                    counts['unsupported_shape'] += 1
                    continue
                proj = gold['projections']
                if any(agg != 0 for _, agg, _ in proj) or any(col == 0 for col, _, _ in proj):
                    counts['transformed_or_star'] += 1
                    continue
                tick = time.process_time()
                result = query_rows(connections[db], row['query'])
                execution_cpu += time.process_time() - tick
                counts['environment_queries'] += 1
                if result is None:
                    counts['execution_failed'] += 1
                    continue
                if not result:
                    counts['empty_abstain'] += 1
                    continue
                if len(result[0]) != len(proj):
                    counts['arity_mismatch'] += 1
                    continue
                tick = time.process_time()
                proposed = output_support(result, domains[db], schemas[db])
                pruning_cpu += time.process_time() - tick
                if proposed is None:
                    counts['budget_exceeded'] += 1
                    continue
                gold_cols = [col for col, _, _ in proj]
                base = sum(1 for table, _ in schemas[db]['column_names_original'] if table >= 0)
                ratios = [base / max(1, len(cols)) for cols in proposed]
                survived = all(col in cols for col, cols in zip(gold_cols, proposed))
                examples.append({'db': db, 'arity': len(proj),
                                 'answer': result, 'gold_cols': gold_cols,
                                 'survived': survived,
                                 'base': base, 'after': [len(cols) for cols in proposed],
                                 'fivefold': all(r >= 5 for r in ratios),
                                 'all_counts': proposed})
        shuffled_evaluated = 0
        shuffled_survived = 0
        for item in examples:
            alternatives = [x for x in examples if x is not item and
                            x['db'] == item['db'] and x['arity'] == item['arity']]
            if not alternatives:
                continue
            other = alternatives[rng.randrange(len(alternatives))]
            tick = time.process_time()
            proposal = output_support(other['answer'], domains[item['db']],
                                      schemas[item['db']])
            pruning_cpu += time.process_time() - tick
            if proposal is None:
                continue
            shuffled_evaluated += 1
            shuffled_survived += all(c in cols for c, cols in
                                     zip(item['gold_cols'], proposal))
        counts['eligible'] = len(examples)
        counts['gold_survived'] = sum(x['survived'] for x in examples)
        counts['fivefold'] = sum(x['fivefold'] for x in examples)
        counts['shuffled_evaluated'] = shuffled_evaluated
        counts['shuffled_gold_survived'] = shuffled_survived
        after = [n for item in examples for n in item['after']]
        median_after = sorted(after)[len(after)//2] if after else None
        counts['candidate_evaluations'] = sum(item['arity'] * item['base']
                                              for item in examples)
        counts['output_rows'] = sum(len(item['answer']) for item in examples)
        gate = (len(examples) >= 10 and counts['gold_survived'] == len(examples)
                and counts['fivefold'] >= 0.75 * len(examples)
                and median_after is not None and median_after <= 5
                and shuffled_evaluated > 0
                and shuffled_survived < shuffled_evaluated)
        reports.append({'seed': seed, 'counts': dict(counts),
                        'median_candidates_after_per_position': median_after,
                        'execution_cpu_s': round(execution_cpu, 6),
                        'pruning_cpu_s': round(pruning_cpu, 6),
                        'gate_pass': gate})
    for conn in connections.values():
        conn.close()
    renamed_same = all(
        output_support([('x',)], domains[db], schemas[db]) ==
        output_support([('x',)], domains[db], {
            **schemas[db],
            'column_names_original': [(t, f'c{i}') for i, (t, _) in
                                      enumerate(schemas[db]['column_names_original'])]})
        for db in selected)
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'kind': 'development_output_support_gate',
              'preregistration': 'prereg/G-7c-soporte-de-valores-de-salida.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'renamed_same': renamed_same,
              'gate_pass': all(r['gate_pass'] for r in reports) and renamed_same,
              'reports': reports,
              'reading_cpu_s': round(reading_cpu, 6),
              'domain_cpu_s': round(domain_cpu, 6),
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3/g7c_output_support_gate.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante el ensayo')


if __name__ == '__main__':
    main()

"""G-7d: does answer-supervised column grounding transfer across schemas?"""
from __future__ import annotations

import json
import math
import random
import re
import resource
import sqlite3
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from experiments.g7c_output_support_gate import (
    SEEDS as G7C_SEEDS, canon, output_support, prior_samples, query_rows,
    source_domains,
)


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (131, 173, 211)
MAX_EXPERIENCES = 400


def words(text):
    return tuple(sorted(set(re.findall(r'[^\W_]+', text.casefold()))))


def grams(word):
    return {word[i:i + 3] for i in range(max(1, len(word) - 2))}


def sim(a, b):
    if a == b:
        return 1.0
    ag, bg = grams(a), grams(b)
    return 2 * len(ag & bg) / max(1, len(ag) + len(bg))


def lexical(question, label):
    q, c = words(question), words(label)
    if not q or not c:
        return 0.0, 0.0
    literal = sum(w in q for w in c) / len(c)
    chars = sum(max(sim(a, b) for a in q) for b in c) / len(c)
    return literal, chars


def learn(examples, schemas, shuffle=False, seed=0):
    """Question/column-word association, trained only on answer-derived labels."""
    rng = random.Random(seed)
    questions = {}
    if shuffle:
        for db in sorted(schemas):
            qs = [item['question'] for item in examples if item['db'] == db]
            rng.shuffle(qs)
            questions[db] = iter(qs)
    positive, background, frequency = Counter(), Counter(), Counter()
    for item in examples:
        db, col = item['db'], item['column']
        schema = schemas[db]
        question = next(questions[db]) if shuffle else item['question']
        qwords = words(question)
        labels = [words(name) for table, name in schema['column_names'] if table >= 0]
        target = words(schema['column_names'][col][1])
        if not target:
            continue
        frequency.update(target)
        for qword in qwords:
            for cword in target:
                positive[(qword, cword)] += 1
            for label in labels:
                for cword in label:
                    background[(qword, cword)] += 1 / max(1, len(labels))
    weights = {}
    for pair, count in positive.items():
        if count >= 2:
            weights['\t'.join(pair)] = math.log((count + 0.5) /
                                               (background[pair] + 0.5))
    return {'weights': weights, 'frequency': dict(frequency)}


def scores(question, schema, model):
    q = words(question)
    answers = {'learned': [], 'literal': [], 'chars': [], 'frequency': []}
    for col, (table, name) in enumerate(schema['column_names']):
        if table < 0:
            continue
        literal, chars = lexical(question, name)
        label = words(name)
        associations = [max((model['weights'].get(qword + '\t' + cword, 0.0)
                             for qword in q), default=0.0)
                        for cword in label]
        learned = chars + 0.5 * (sum(max(0.0, a) for a in associations) /
                                 max(1, len(associations)))
        freq = sum(model['frequency'].get(cword, 0) for cword in label)
        for kind, score in (('learned', learned), ('literal', literal),
                            ('chars', chars), ('frequency', freq)):
            answers[kind].append((score, col))
    return {kind: [col for _, col in sorted(items, key=lambda item:
                                           (-item[0], item[1]))]
            for kind, items in answers.items()}


def previous_questions(by_db, schemas, h0):
    prior = prior_samples(by_db, schemas, h0)
    used = set(prior)
    for seed in G7C_SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x67C)
        for db in sorted(by_db):
            available = [row for row in by_db[db]
                         if (db, row['question'], row['query']) not in prior]
            for row in rng.sample(available, min(5, len(available))):
                used.add((db, row['question'], row['query']))
    return used


def opaque(value):
    return sha256((type(value).__name__ + ':' + repr(value)).encode()).hexdigest()


def direct_projection_col(row):
    """Evaluator only: other SQL clauses cannot change the SELECT target."""
    selected = row['sql']['select'][1]
    if len(selected) != 1:
        return None
    agg, val = selected[0]
    if (agg != 0 or not isinstance(val, list) or len(val) != 3 or
        val[0] != 0 or val[2] is not None):
        return None
    inner = val[1]
    if (not isinstance(inner, list) or len(inner) != 3 or inner[0] != 0 or
        type(inner[1]) is not int or inner[1] == 0):
        return None
    return inner[1]


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente alterada')
    rows = json.loads(raw)
    raw_schema = fetch(PREFIX + 'tables_es.json', 2_000_000)
    if sha256(raw_schema).hexdigest() != '4f85a31a72fe94f0d7f2f657e39d783183198fd979aa922c1367512bd5745e5c':
        raise RuntimeError('Esquema alterado')
    schemas = {x['db_id']: x for x in json.loads(raw_schema)}
    inventory = json.loads((ROOT / 'results_v3/g6_multispider_inventory.json').read_text())
    selected = {x['db_id']: x for x in inventory['sampled_databases']}
    by_db = defaultdict(list)
    for row in rows:
        if row['db_id'] in selected:
            by_db[row['db_id']].append(row)
    old = previous_questions(by_db, schemas, h0)
    connections, domains, opaque_domains = {}, {}, {}
    for db, metadata in sorted(selected.items()):
        blob = fetch('dataset/spider/database/' + db + '/' + db + '.sqlite', 512_000)
        if sha256(blob).hexdigest() != metadata['sqlite_sha256']:
            raise RuntimeError('Datos cambiaron')
        conn = sqlite3.connect(':memory:')
        conn.deserialize(blob)
        conn.execute('PRAGMA query_only=ON')
        connections[db] = conn
        domains[db] = source_domains(conn, schemas[db])
        opaque_domains[db] = {
            col: None if values is None else {opaque(value) for value in values}
            for col, values in domains[db].items()}
    reports = []
    for seed in SEEDS:
        rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x67D)
        training = []
        testing = []
        weak_correct = 0
        weak_checked = 0
        counts = Counter()
        renamed_values_same = True
        for db in sorted(selected):
            available = [row for row in by_db[db]
                         if (db, row['question'], row['query']) not in old]
            chosen = rng.sample(available, min(60, len(available)))
            ntest = min(20, max(5, len(chosen) // 3))
            train_rows = chosen[ntest:ntest + 40]
            test_rows = chosen[:ntest]
            for row in train_rows:
                counts['education_offered'] += 1
                answer = query_rows(connections[db], row['query'])
                counts['education_queries'] += 1
                if not answer or len(answer[0]) != 1:
                    continue
                options = output_support(answer, domains[db], schemas[db])
                renamed_answer = [tuple(opaque(canon(value)) for value in record)
                                  for record in answer]
                renamed_values_same &= (options == output_support(
                    renamed_answer, opaque_domains[db], schemas[db]))
                if options is None or len(options[0]) != 1:
                    continue
                column = next(iter(options[0]))
                training.append({'db': db, 'question': row['question'],
                                 'column': column})
                weak_checked += 1
                weak_correct += direct_projection_col(row) == column
            testing.extend((db, row) for row in test_rows)
        if len(training) > MAX_EXPERIENCES:
            raise RuntimeError('Presupuesto de enseñanza excedido')
        train_cpu0 = time.process_time()
        fold_models = {}
        fold_shuffled = {}
        for db in sorted(selected):
            others = [item for item in training if item['db'] != db]
            fold_models[db] = learn(others, schemas)
            fold_shuffled[db] = learn(others, schemas, True, seed)
        train_cpu = time.process_time() - train_cpu0
        # Actual save/close/load path, with no executable code in the model.
        with tempfile.NamedTemporaryFile(mode='w+', encoding='utf8') as stream:
            json.dump(fold_models, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            stream.seek(0)
            restored = json.load(stream)
        restart_same = fold_models == restored
        fold_models = restored
        hits = Counter()
        evaluated = 0
        latency = []
        candidate_evaluations = 0
        rank_changed_from_chars = 0
        rank_changed_from_shuffled = 0
        per_db = {}
        for db in sorted(selected):
            per_db[db] = {'eligible': 0, 'learned_top1': 0, 'chars_top1': 0}
            memorized_questions = {item['question'] for item in training
                                   if item['db'] != db}
            for test_db, row in testing:
                if test_db != db:
                    continue
                question = row['question']
                t0 = time.perf_counter_ns()
                ranks = scores(question, schemas[db], fold_models[db])
                latency.append((time.perf_counter_ns() - t0) / 1e6)
                shuffled = scores(question, schemas[db], fold_shuffled[db])['learned']
                rank_changed_from_chars += ranks['learned'] != ranks['chars']
                rank_changed_from_shuffled += ranks['learned'] != shuffled
                candidate_evaluations += len(ranks['learned']) * 2
                # Gold and output are inspected only after all predictions.
                col = direct_projection_col(row)
                if col is None:
                    continue
                answer = query_rows(connections[db], row['query'])
                if not answer or len(answer[0]) != 1:
                    continue
                evaluated += 1
                per_db[db]['eligible'] += 1
                hits['memory_exact_question_seen'] += question in memorized_questions
                for kind, ranking in ranks.items():
                    hits[kind + '_top1'] += col == ranking[0]
                    hits[kind + '_top3'] += col in ranking[:3]
                hits['shuffled_top1'] += col == shuffled[0]
                hits['shuffled_top3'] += col in shuffled[:3]
                per_db[db]['learned_top1'] += col == ranks['learned'][0]
                per_db[db]['chars_top1'] += col == ranks['chars'][0]
        best_lexical = max(hits['literal_top1'], hits['chars_top1'])
        purity = weak_correct / weak_checked if weak_checked else 0.0
        gate = (evaluated >= 40 and purity >= 0.90 and restart_same and
                renamed_values_same and
                hits['learned_top1'] >= 0.50 * evaluated and
                hits['learned_top1'] - best_lexical >= 0.15 * evaluated and
                hits['learned_top3'] >= 0.75 * evaluated)
        reports.append({'seed': seed, 'education_offered': counts['education_offered'],
                        'weak_labels': len(training), 'weak_label_purity': purity,
                        'eligible_test': evaluated, 'hits': dict(hits),
                        'candidate_evaluations': candidate_evaluations,
                        'learned_weight_pairs_by_fold': {
                            db: len(fold_models[db]['weights']) for db in sorted(selected)},
                        'rank_changed_from_chars': rank_changed_from_chars,
                        'rank_changed_from_shuffled': rank_changed_from_shuffled,
                        'restart_same': restart_same,
                        'renamed_values_same': renamed_values_same,
                        'train_cpu_s': round(train_cpu, 6),
                        'rank_p50_ms': round(statistics.median(latency), 6) if latency else None,
                        'rank_p95_ms': round(sorted(latency)[int(.95 * (len(latency)-1))], 6)
                        if latency else None,
                        'per_database': per_db,
                        'gate_pass': gate})
    for conn in connections.values():
        conn.close()
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'kind': 'development_cross_schema_grounding',
              'preregistration': 'prereg/G-7d-transferencia-de-alineaciones-linguisticas.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'gate_pass': all(x['gate_pass'] for x in reports),
              'reports': reports, 'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3/g7d_grounding_cross_schema.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante ensayo')


if __name__ == '__main__':
    main()

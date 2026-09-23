"""Read-only inventory of Spanish human-reviewed questions with executable answers."""
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
from urllib.parse import quote
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
REVISION = '8e159f59bf5ba1f4e89977cece36402f84925405'
BASE = ('https://huggingface.co/datasets/dreamerdeo/multispider/resolve/'
        + REVISION + '/')
API = ('https://huggingface.co/api/datasets/dreamerdeo/multispider/tree/'
       + REVISION + '/dataset/spider/database/')
PREFIX = 'dataset/multispider/with_english_value/'
TRAIN_SHA = '29a8d510a5070c4598f484ea8a15222f1b17056bc9645d9d2aed894d688e4d84'


def fetch(path: str, limit: int):
    with urlopen(BASE + path, timeout=25) as response:
        return response.read(limit + 1)


def safe_read_query(blob: bytes, statement: str) -> tuple[str, int, str | None]:
    clean = statement.strip().rstrip(';').strip()
    if (not re.match(r'(?is)^(select|with)\b', clean) or
        ';' in clean or len(clean) > 20_000):
        return 'not_read_query', 0, None
    conn = sqlite3.connect(':memory:')
    try:
        conn.deserialize(blob)
        conn.execute('PRAGMA query_only=ON')
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                   sqlite3.SQLITE_FUNCTION}
        conn.set_authorizer(lambda action, a, b, database, trigger:
                            sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        ticks = [0]
        def limit_cpu():
            ticks[0] += 1
            return ticks[0] >= 100
        conn.set_progress_handler(limit_cpu, 1000)
        result = conn.execute(clean).fetchmany(51)
        return 'executed', len(result), sha256(repr(result).encode()).hexdigest()
    except sqlite3.Error as exc:
        return type(exc).__name__, 0, None
    finally:
        conn.close()


def main():
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Datos de educación cambiaron')
    rows = json.loads(raw)
    schema_raw = fetch(PREFIX + 'tables_es.json', 2_000_000)
    schemas = json.loads(schema_raw)
    by_db = defaultdict(list)
    operators = Counter()
    for row in rows:
        by_db[row['db_id']].append(row)
        sql = row['query'].casefold()
        for key, pattern in (('where', r'\bwhere\b'),
                             ('join', r'\bjoin\b'),
                             ('group_by', r'\bgroup\s+by\b'),
                             ('order_by', r'\border\s+by\b'),
                             ('having', r'\bhaving\b'),
                             ('nested_select', r'\bselect\b')):
            hits = len(re.findall(pattern, sql))
            if hits > (1 if key == 'nested_select' else 0):
                operators[key] += 1
    rng = random.Random(int(h0[:8], 16) ^ 0x6606)
    dbs = sorted(db for db, items in by_db.items() if len(items) >= 20)
    rng.shuffle(dbs)
    selected = []
    attempted = 0
    for db in dbs:
        if len(selected) >= 8 or attempted >= 20:
            break
        attempted += 1
        with urlopen(API + quote(db, safe=''), timeout=10) as response:
            listing = json.load(response)
        filename = db + '.sqlite'
        size = next((item['size'] for item in listing
                     if item['path'].endswith('/' + filename)), None)
        if size is None or size > 512_000:
            continue
        blob = fetch('dataset/spider/database/' + db + '/' + filename, 512_000)
        if len(blob) != size:
            raise RuntimeError('Base de datos incompleta')
        sample = rng.sample(by_db[db], min(3, len(by_db[db])))
        outcomes = [safe_read_query(blob, item['query']) for item in sample]
        selected.append({'db_id': db, 'sqlite_bytes': size,
                         'sqlite_sha256': sha256(blob).hexdigest(),
                         'education_questions': len(by_db[db]),
                         'query_statuses': [item[0] for item in outcomes],
                         'nonempty_outputs': sum(item[1] > 0 for item in outcomes),
                         'distinct_output_signatures': len({item[2] for item in outcomes
                                                           if item[2] is not None})})
    if git('rev-parse', 'HEAD:leobot') != h0:
        raise RuntimeError('Motor cambió')
    output = {'kind': 'source_inventory_only', 'source_revision': REVISION,
              'train_es_sha256': TRAIN_SHA,
              'tables_es_sha256': sha256(schema_raw).hexdigest(),
              'engine_tree': h0, 'training_questions': len(rows),
              'training_databases': len(by_db), 'schema_databases': len(schemas),
              'schemas_cover_training': set(by_db) <= {item['db_id'] for item in schemas},
              'sql_construct_counts': dict(operators),
              'sampled_databases': selected,
              'sampling_db_metadata_calls': attempted,
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3' / 'g6_multispider_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

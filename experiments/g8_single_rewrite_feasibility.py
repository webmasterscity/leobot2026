"""Preregistered G-8 feasibility: can one local substitution gain support?"""
from __future__ import annotations

import json
import re
import resource
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from leobot.language import normalize


ROOT = Path(__file__).resolve().parents[1]
QUOTED = re.compile(r"''[^']*''|\"[^\"]*\"|'[^']*'")
NUMBER = re.compile(r'(?<!\w)\d+(?:[.,]\d+)?(?!\w)')


def delex(text):
    norm = QUOTED.sub(' <val> ', normalize(text))
    return tuple(NUMBER.sub(' <num> ', norm).split())


def replacement(left, right):
    if left == right:
        return None
    changes = [op for op in SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes()
               if op[0] != 'equal']
    if len(changes) != 1 or changes[0][0] != 'replace':
        return None
    _, a, b, c, d = changes[0]
    first, second = left[a:b], right[c:d]
    if (not 1 <= len(first) <= 4 or not 1 <= len(second) <= 4 or
        any(tok in ('<val>', '<num>') for tok in first + second)):
        return None
    return tuple(sorted((first, second)))


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes de la prueba')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Fuente cambió')
    selected = {x['db_id'] for x in json.loads(
        (ROOT / 'results_v3/g6_multispider_inventory.json').read_text())['sampled_databases']}
    by_db = defaultdict(list)
    for row in json.loads(raw):
        if row['db_id'] in selected:
            by_db[row['db_id']].append(row)
    counts = Counter()
    per_db = {}
    support = defaultdict(set)
    for db in sorted(selected):
        local = Counter()
        rows = by_db[db]
        for i, row in enumerate(rows):
            for other in rows[i + 1:]:
                subst = replacement(delex(row['question']), delex(other['question']))
                if subst is None:
                    continue
                local['candidate_pairs'] += 1
                if row['query'].strip().casefold() == other['query'].strip().casefold():
                    local['same_sql_pairs'] += 1
                    support[subst].add((db, row['query'].strip().casefold()))
                else:
                    local['other_sql_pairs_upper_bound_negative'] += 1
        counts.update(local)
        per_db[db] = dict(local)
    promotable = sum(len(groups) >= 3 and len({db for db, _ in groups}) >= 2
                     for groups in support.values())
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    result = {'kind': 'development_single_replacement_upper_bound',
              'preregistration': 'prereg/G-8-parafrasis-por-feedback-contrastivo.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'counts': dict(counts), 'per_database': per_db,
              'unique_positive_replacements': len(support),
              'max_promotable_under_preregistered_support': promotable,
              'gate_possible': promotable > 0,
              'note': 'SQL gold used only by evaluator for an upper bound; no learner ran.',
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3/g8_single_rewrite_feasibility.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante la prueba')


if __name__ == '__main__':
    main()

"""Read-only source inventory for distinct Spanish paraphrases with shared SQL."""
from __future__ import annotations

import json
import re
import resource
import time
from collections import defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g6_multispider_inventory import PREFIX, TRAIN_SHA, fetch
from leobot.language import normalize


ROOT = Path(__file__).resolve().parents[1]


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = fetch(PREFIX + 'train_es.json', 35_000_000)
    if sha256(raw).hexdigest() != TRAIN_SHA:
        raise RuntimeError('Preguntas cambiaron')
    selected = {x['db_id'] for x in json.loads(
        (ROOT / 'results_v3/g6_multispider_inventory.json').read_text())['sampled_databases']}
    groups = defaultdict(set)
    for row in json.loads(raw):
        if row['db_id'] in selected:
            groups[(row['db_id'], row['query'].strip().casefold())].add(
                normalize(row['question']))
    supports = defaultdict(set)
    paired_groups = pairs = 0
    by_db = defaultdict(lambda: {'groups': 0, 'pairs': 0})
    for key, questions in sorted(groups.items()):
        items = sorted(questions)
        if len(items) < 2:
            continue
        paired_groups += 1
        by_db[key[0]]['groups'] += 1
        for i, left in enumerate(items):
            for right in items[i + 1:]:
                pairs += 1
                by_db[key[0]]['pairs'] += 1
                a, b = left.split(), right.split()
                for tag, x, y, u, v in SequenceMatcher(
                        a=a, b=b, autojunk=False).get_opcodes():
                    if tag != 'replace':
                        continue
                    first, second = tuple(a[x:y]), tuple(b[u:v])
                    if not (1 <= len(first) <= 4 and 1 <= len(second) <= 4):
                        continue
                    if any(re.search(r'[0-9\"\']', tok) for tok in (*first, *second)):
                        continue
                    supports[tuple(sorted((first, second)))].add(key)
    repeated = [links for links in supports.values()
                if len(links) >= 3 and len({db for db, _ in links}) >= 2]
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    result = {'kind': 'source_paraphrase_inventory_only',
              'source_sha256': TRAIN_SHA, 'engine_tree': h0,
              'engine_unchanged': unchanged,
              'paired_same_sql_groups': paired_groups,
              'distinct_question_pairs': pairs,
              'candidate_local_replacements': len(supports),
              'replacements_repeated_across_3_groups_2db': len(repeated),
              'per_database': dict(sorted(by_db.items())),
              'cpu_total_s': round(time.process_time() - cpu0, 6),
              'wall_total_s': round(time.monotonic() - wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3/g8_paraphrase_inventory.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante inventario')


if __name__ == '__main__':
    main()

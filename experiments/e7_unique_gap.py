"""E-7 external, frozen test of a single literal gap in question/document overlap."""
from __future__ import annotations

import io
import json
import random
import re
import resource
import subprocess
import time
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.agi_board import (MLQA_ARCHIVE_SHA, MLQA_MEMBER, MLQA_URL,
                                   SEED, canonical)


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-E-7'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Tag cambió')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor no congelado')


def sample(tree):
    with urllib.request.urlopen(MLQA_URL, timeout=20) as response:
        data = response.read(80 * 1024 * 1024 + 1)
    if len(data) > 80 * 1024 * 1024 or sha256(data).hexdigest() != MLQA_ARCHIVE_SHA:
        raise RuntimeError('MLQA fuera del preregistro')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document = json.loads(archive.read(MLQA_MEMBER))
    rows = sorted(({'id': qa['id'], 'article': str(article['title']),
                    'context': paragraph['context'], 'question': qa['question'],
                    'answers': [a['text'] for a in qa['answers']]}
                   for article in document['data']
                   for paragraph in article['paragraphs']
                   for qa in paragraph['qas']), key=lambda row: row['id'])
    excluded = {row['id'] for row in random.Random(SEED).sample(rows, 20)}
    for name in ('e1_reading_diagnostic.json', 'e2_evidence_pilot.json',
                 'e3_raw_curriculum.json', 'e5_clause_fragments.json',
                 'e6b_mdl_filter.json'):
        prior = json.loads((ROOT / 'results_v3' / name).read_text(encoding='utf8'))
        excluded.update(row['id'] for row in prior['rows'])
    by_article = {}
    for row in rows:
        if row['id'] not in excluded:
            by_article.setdefault(row['article'], row)
    names = sorted(by_article)
    seed = int(sha256((tree + ':E-7').encode()).hexdigest()[:8], 16)
    chosen = random.Random(seed).sample(names, 40)
    return [by_article[name] for name in chosen], len(data)


def find_gap(question, passage):
    qwords = set(canonical(question).split())
    ranked = sorted(Bot._document_sentences(passage),
                    key=lambda sentence: -len(set(canonical(sentence).split()) & qwords))[:3]
    found = []
    for sentence in ranked:
        matches = [(match, canonical(match.group()))
                   for match in re.finditer(r'[^\W_]+', sentence)]
        matches = [(match, word) for match, word in matches if word]
        if len({word for _, word in matches} & qwords) < 3:
            continue
        shared = [word in qwords for _, word in matches]
        i = 1
        while i < len(matches) - 1:
            if shared[i] or not shared[i - 1]:
                i += 1
                continue
            end = i
            while end < len(matches) and not shared[end]:
                end += 1
            if end < len(matches) and 1 <= end - i <= 6:
                found.append(sentence[matches[i][0].start():matches[end - 1][0].end()])
            i = end + 1
    return found[0] if len(found) == 1 else None


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    frozen(tree)
    wall, cpu = time.monotonic(), time.process_time()
    rows, archive_bytes = sample(tree)
    out = []
    for i, row in enumerate(rows):
        answer = find_gap(row['question'], row['context'])
        wrong = find_gap(row['question'], rows[(i + 1) % len(rows)]['context'])
        gold = {canonical(value) for value in row['answers']}
        out.append({'id': row['id'], 'attempted': answer is not None,
                    'exact': answer is not None and canonical(answer) in gold,
                    'wrong_passage_attempted': wrong is not None})
    frozen(tree)
    counts = {'attempted': sum(row['attempted'] for row in out),
              'exact': sum(row['exact'] for row in out),
              'wrong_passage_attempted': sum(row['wrong_passage_attempted'] for row in out)}
    counts['precision'] = (counts['exact'] / counts['attempted']
                           if counts['attempted'] else None)
    result = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
              'preregistration': 'prereg/E-7-hueco-textual-unico.md',
              'cases': len(out), 'archive_bytes': archive_bytes, 'counts': counts,
              'cpu_s': round(time.process_time() - cpu, 6),
              'wall_s': round(time.monotonic() - wall, 3),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'rows': out}
    path = ROOT / 'results_v3' / 'e7_unique_gap.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in result.items() if key != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    run()

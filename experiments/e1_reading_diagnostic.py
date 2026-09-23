"""Preregistered E-1 diagnosis on disjoint public MLQA development cases."""
from __future__ import annotations

import io
import json
import random
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
TAG = 'freeze-E-1'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def assert_frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('La huella del tag cambió')
    if git('diff', '--name-only', TAG, '--', 'leobot'):
        raise RuntimeError('El motor difiere del tag congelado')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Hay cambios sin commit en el motor')


def cases(tree):
    with urllib.request.urlopen(MLQA_URL, timeout=20) as response:
        archive_data = response.read(40 * 1024 * 1024 + 1)
    if len(archive_data) > 40 * 1024 * 1024:
        raise RuntimeError('Archivo supera presupuesto')
    if sha256(archive_data).hexdigest() != MLQA_ARCHIVE_SHA:
        raise RuntimeError('El archivo MLQA no coincide con el preregistro')
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        document = json.loads(archive.read(MLQA_MEMBER))
    all_cases = []
    for article in document['data']:
        for paragraph in article['paragraphs']:
            for qa in paragraph['qas']:
                all_cases.append({'id': qa['id'], 'context': paragraph['context'],
                                  'question': qa['question'],
                                  'answers': [a['text'] for a in qa['answers']]})
    ordered = sorted(all_cases, key=lambda row: row['id'])
    board_ids = {row['id'] for row in random.Random(SEED).sample(ordered, 20)}
    pool = [row for row in ordered if row['id'] not in board_ids]
    chosen = random.Random(int(tree[:8], 16)).sample(pool, 20)
    return chosen, len(ordered), len(archive_data)


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    assert_frozen(tree)
    started = time.monotonic()
    selected, source_count, archive_bytes = cases(tree)
    rows = []
    for row in selected:
        if time.monotonic() - started > 115:
            raise RuntimeError('Se agotó el presupuesto de tiempo')
        bot = Bot()
        tick = time.process_time()
        pre = bot.respond(row['question'])
        pre_cpu = time.process_time() - tick
        tick = time.process_time()
        report = bot.ingest_document_text(row['context'], source=f'e1:{row["id"]}')
        read_cpu = time.process_time() - tick
        tick = time.process_time()
        post = bot.respond(row['question'])
        answer_cpu = time.process_time() - tick
        gold = {canonical(answer) for answer in row['answers']}
        rows.append({'id': row['id'], 'pre_status': pre.get('status'),
                     'post_status': post.get('status'),
                     'pre_exact': canonical(pre.get('text', '')) in gold,
                     'post_exact': canonical(post.get('text', '')) in gold,
                     'answer_present_in_text': any(canonical(answer) in canonical(row['context'])
                                                   for answer in row['answers']),
                     'facts_added': report['facts_added'],
                     'relations_promoted': report['relations_promoted'],
                     'cpu_s': {'pre': round(pre_cpu, 6), 'reading': round(read_cpu, 6),
                               'answer': round(answer_cpu, 6)}})
    assert_frozen(tree)
    summary = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
               'preregistration': 'prereg/E-1-diagnostico-lectura-literal.md',
               'source': 'https://github.com/facebookresearch/MLQA',
               'source_cases': source_count, 'archive_bytes': archive_bytes,
               'cases': len(rows), 'pre_exact': sum(x['pre_exact'] for x in rows),
               'post_exact': sum(x['post_exact'] for x in rows),
               'text_contains_answer': sum(x['answer_present_in_text'] for x in rows),
               'cases_with_facts': sum(x['facts_added'] > 0 for x in rows),
               'total_facts': sum(x['facts_added'] for x in rows),
               'cases_with_promotions': sum(x['relations_promoted'] > 0 for x in rows),
               'status_counts': {status: sum(x['post_status'] == status for x in rows)
                                 for status in sorted({x['post_status'] for x in rows})},
               'cpu_s': {part: round(sum(x['cpu_s'][part] for x in rows), 6)
                         for part in ('pre', 'reading', 'answer')},
               'wall_s': round(time.monotonic() - started, 3),
               'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'rows': rows}
    path = ROOT / 'results_v3' / 'e1_reading_diagnostic.json'
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    run()

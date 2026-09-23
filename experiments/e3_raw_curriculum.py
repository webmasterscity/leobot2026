"""E-3: educate the frozen existing bot on unrelated, unannotated Spanish prose."""
from __future__ import annotations

import io
import json
import random
import resource
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.agi_board import (MLQA_ARCHIVE_SHA, MLQA_MEMBER, MLQA_URL,
                                   SEED, canonical)


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-E-3'
EVIDENCE_STATUSES = {'supported', 'refuted', 'bindings', 'entailed',
                     'contradicted', 'contested'}


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Tag de motor alterado')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor de trabajo alterado')


def curriculum(tree):
    with urllib.request.urlopen(MLQA_URL, timeout=20) as response:
        data = response.read(80 * 1024 * 1024 + 1)
    if len(data) > 80 * 1024 * 1024 or sha256(data).hexdigest() != MLQA_ARCHIVE_SHA:
        raise RuntimeError('Archivo fuera del preregistro')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document = json.loads(archive.read(MLQA_MEMBER))
    all_rows = sorted(({'id': qa['id'], 'article': str(article['title']),
                        'context': paragraph['context'], 'question': qa['question'],
                        'answers': [a['text'] for a in qa['answers']]}
                       for article in document['data']
                       for paragraph in article['paragraphs']
                       for qa in paragraph['qas']), key=lambda row: row['id'])
    excluded = {row['id'] for row in random.Random(SEED).sample(all_rows, 20)}
    for file in ('e1_reading_diagnostic.json', 'e2_evidence_pilot.json'):
        prior = json.loads((ROOT / 'results_v3' / file).read_text(encoding='utf8'))
        excluded.update(row['id'] for row in prior['rows'])
    by_article = {}
    for row in all_rows:
        if row['id'] not in excluded:
            by_article.setdefault(row['article'], []).append(row)
    names = sorted(by_article)
    seed = int(sha256((tree + ':E-3').encode()).hexdigest()[:8], 16)
    random.Random(seed).shuffle(names)
    if len(names) < 50:
        raise RuntimeError('No hay 50 artículos distintos')
    train = [by_article[name][0] for name in names[:30]]
    test = [by_article[name][0] for name in names[30:50]]
    return train, test, len(data)


def score(bot, row):
    tick = time.process_time()
    before = bot.respond(row['question'])
    before_cpu = time.process_time() - tick
    tick = time.process_time()
    report = bot.ingest_document_text(row['context'], source=f'e3:test:{row["id"]}')
    read_cpu = time.process_time() - tick
    tick = time.process_time()
    after = bot.respond(row['question'])
    answer_cpu = time.process_time() - tick
    gold = {canonical(answer) for answer in row['answers']}
    return {'before_status': before.get('status'), 'after_status': after.get('status'),
            'before_exact': canonical(before.get('text', '')) in gold,
            'after_exact': canonical(after.get('text', '')) in gold,
            'after_with_evidence': after.get('status') in EVIDENCE_STATUSES,
            'facts_added': report['facts_added'],
            'promoted': report['relations_promoted'],
            'cpu_s': {'before': round(before_cpu, 6), 'reading': round(read_cpu, 6),
                      'answer': round(answer_cpu, 6)}}


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    frozen(tree)
    wall_start, cpu_start = time.monotonic(), time.process_time()
    train, test, archive_bytes = curriculum(tree)
    educated = Bot()
    ablated = Bot(raw_relation_min_support=1000)
    acquisition = {}
    for label, bot in (('educated', educated), ('ablated', ablated)):
        tick = time.process_time()
        facts = promotions = 0
        for i, row in enumerate(train):
            report = bot.ingest_document_text(row['context'], source=f'e3:train:{i}')
            facts += report['facts_added']
            promotions += report['relations_promoted']
            if time.monotonic() - wall_start > 130 or time.process_time() - cpu_start > 85:
                raise RuntimeError('Presupuesto de educación agotado')
        acquisition[label] = {'facts': facts, 'promotions': promotions,
                              'cpu_s': round(time.process_time() - tick, 6)}
    with tempfile.TemporaryDirectory() as directory:
        educated_path = Path(directory) / 'educated.json'
        ablated_path = Path(directory) / 'ablated.json'
        educated.save(educated_path)
        ablated.save(ablated_path)
        loaded = Bot.load(educated_path)
        restart_stable = (loaded.kb.stats()['facts'] == educated.kb.stats()['facts']
                          and len(loaded.raw_relation_observations)
                          == len(educated.raw_relation_observations))
        results = []
        for row in test:
            fresh = score(Bot(), row)
            educated_result = score(Bot.load(educated_path), row)
            ablated_result = score(Bot.load(ablated_path), row)
            results.append({'id': row['id'], 'fresh': fresh,
                            'educated': educated_result, 'ablated': ablated_result})
            if time.monotonic() - wall_start > 145 or time.process_time() - cpu_start > 88:
                raise RuntimeError('Presupuesto de ensayo agotado')
    frozen(tree)
    counts = {condition: {metric: sum(row[condition][metric] for row in results)
                          for metric in ('before_exact', 'after_exact', 'after_with_evidence',
                                         'facts_added', 'promoted')}
              for condition in ('fresh', 'educated', 'ablated')}
    output = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
              'preregistration': 'prereg/E-3-curriculo-crudo-congelado.md',
              'archive_bytes': archive_bytes, 'train_articles': len(train),
              'test_articles': len(test), 'acquisition': acquisition,
              'counts': counts, 'restart_stable': restart_stable,
              'wall_s': round(time.monotonic() - wall_start, 3),
              'cpu_s': round(time.process_time() - cpu_start, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'rows': results}
    path = ROOT / 'results_v3' / 'e3_raw_curriculum.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in output.items() if k != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    run()

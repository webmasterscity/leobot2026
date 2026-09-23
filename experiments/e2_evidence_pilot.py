"""Frozen E-2 feasibility check for locating, not understanding, text evidence."""
from __future__ import annotations

import io
import json
import math
import random
import resource
import subprocess
import time
import urllib.request
import zipfile
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.agi_board import (MLQA_ARCHIVE_SHA, MLQA_MEMBER, MLQA_URL,
                                   SEED, canonical)


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-E-2-piloto'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Motor etiquetado cambiado')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor de trabajo no congelado')


def sample(tree):
    with urllib.request.urlopen(MLQA_URL, timeout=20) as response:
        data = response.read(80 * 1024 * 1024 + 1)
    if len(data) > 80 * 1024 * 1024 or sha256(data).hexdigest() != MLQA_ARCHIVE_SHA:
        raise RuntimeError('Archivo MLQA fuera del preregistro')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document = json.loads(archive.read(MLQA_MEMBER))
    rows = sorted(({'id': qa['id'], 'context': paragraph['context'],
                    'question': qa['question'],
                    'answers': [a['text'] for a in qa['answers']]}
                   for article in document['data']
                   for paragraph in article['paragraphs']
                   for qa in paragraph['qas']), key=lambda row: row['id'])
    excluded = {row['id'] for row in random.Random(SEED).sample(rows, 20)}
    prior = json.loads((ROOT / 'results_v3' / 'e1_reading_diagnostic.json').read_text())
    excluded.update(row['id'] for row in prior['rows'])
    seed = int(sha256((tree + ':E-2-piloto').encode()).hexdigest()[:8], 16)
    return random.Random(seed).sample([row for row in rows if row['id'] not in excluded], 40), len(data)


def rank(question, sentences, weighted):
    tokens = [set(canonical(sentence).split()) for sentence in sentences]
    query = set(canonical(question).split())
    count = Counter(word for sentence in tokens for word in sentence)
    n = len(tokens)
    return sorted(range(n), key=lambda i: (
        -sum((1 + math.log((n + 1) / (count[word] + 1))) if weighted else 1
             for word in query & tokens[i]), i))


def located(sentences, indices, answers):
    target = [canonical(answer) for answer in answers]
    return any(any(answer in canonical(sentences[i]) for answer in target) for i in indices)


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    frozen(tree)
    start = time.monotonic()
    rows, archive_bytes = sample(tree)
    results = []
    total_cpu = 0.0
    for row in rows:
        sentences = Bot._document_sentences(row['context'])
        tick = time.process_time()
        simple = rank(row['question'], sentences, False)
        weighted = rank(row['question'], sentences, True)
        total_cpu += time.process_time() - tick
        results.append({'id': row['id'], 'sentences': len(sentences),
                        'first_top1': located(sentences, [0], row['answers']),
                        'first_top3': located(sentences, range(min(3, len(sentences))), row['answers']),
                        'simple_top1': located(sentences, simple[:1], row['answers']),
                        'simple_top3': located(sentences, simple[:3], row['answers']),
                        'idf_top1': located(sentences, weighted[:1], row['answers']),
                        'idf_top3': located(sentences, weighted[:3], row['answers'])})
        if time.monotonic() - start > 115:
            raise RuntimeError('Tiempo del piloto agotado')
    frozen(tree)
    counts = {name: sum(row[name] for row in results)
              for name in ('first_top1', 'first_top3', 'simple_top1', 'simple_top3',
                           'idf_top1', 'idf_top3')}
    outcome = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
               'preregistration': 'prereg/E-2-localizacion-de-evidencia.md',
               'cases': len(results), 'archive_bytes': archive_bytes,
               'counts': counts, 'rank_cpu_s': round(total_cpu, 6),
               'wall_s': round(time.monotonic() - start, 3),
               'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'rows': results}
    path = ROOT / 'results_v3' / 'e2_evidence_pilot.json'
    path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in outcome.items() if k != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    run()

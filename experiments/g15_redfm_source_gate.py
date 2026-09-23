"""G-15: source viability for Spanish Wikipedia relations, no learner."""
from __future__ import annotations

import json
import os
import random
import resource
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
REVISION = '7fab33bee528dc1dd09d90f788afc93d35fd71b3'
URL = f'https://huggingface.co/datasets/Babelscape/REDFM/resolve/{REVISION}/data/train.es.jsonl'
CAP = 10 * 1024 * 1024
SEEDS = (911, 977, 1039)


def source():
    with urlopen(URL, timeout=20) as response:
        size = int(response.headers.get('Content-Length', '0'))
        if size > CAP:
            raise RuntimeError('Fuente supera límite preregistrado')
        raw = response.read(CAP+1)
    if not raw or len(raw) > CAP:
        raise RuntimeError('Fuente vacía o demasiado grande')
    return raw


def load(raw):
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        if row.get('lan') != 'es' or not row.get('uri'):
            raise RuntimeError('Idioma o identificador documental inesperado')
        rows.append(row)
    return rows


def aligned(text, entity):
    try:
        start, end = (int(value) for value in entity['boundaries'])
        return (0 <= start < end <= len(text) and
                text[start:end].casefold() == str(entity['surfaceform']).casefold())
    except (KeyError, TypeError, ValueError):
        return False


def relation_id(relation):
    predicate = relation.get('predicate') or {}
    return str(predicate.get('uri'))


def structural_counts(rows):
    counts = Counter()
    rivals = defaultdict(set)
    for row in rows:
        triples = row.get('relations') or []
        counts['paragraphs'] += 1
        counts['one_triple_paragraphs'] += len(triples) == 1
        counts['multi_triple_paragraphs'] += len(triples) >= 2
        for relation in triples:
            counts['triples'] += 1
            sub, obj = relation.get('subject') or {}, relation.get('object') or {}
            counts['entity_mentions'] += 2
            counts['aligned_mentions'] += aligned(row['text'], sub) + aligned(row['text'], obj)
            counts['fully_aligned_triples'] += aligned(row['text'], sub) and aligned(row['text'], obj)
            pair = (row['uri'], sub.get('uri'), obj.get('uri'))
            rivals[pair].add(relation_id(relation))
    counts['pairs_with_multiple_relations'] = sum(len(values) > 1 for values in rivals.values())
    return dict(counts)


def partition(rows, h0):
    by_article = defaultdict(list)
    for row in rows:
        by_article[row['uri']].append(row)
    all_articles = sorted(by_article)
    reports = []
    for seed in SEEDS:
        articles = list(all_articles)
        random.Random(int(h0[:8], 16) ^ seed ^ 0x69B).shuffle(articles)
        heldout = set(articles[:max(20, round(.2*len(articles)))])
        train = [row for article in all_articles if article not in heldout
                 for row in by_article[article]]
        test = [row for article in all_articles if article in heldout
                for row in by_article[article]]
        train_domains = defaultdict(set)
        test_domains = defaultdict(set)
        for row in train:
            for relation in row.get('relations') or []:
                train_domains[relation_id(relation)].add(row['uri'])
        for row in test:
            for relation in row.get('relations') or []:
                test_domains[relation_id(relation)].add(row['uri'])
        teachable = {label for label, docs in train_domains.items() if len(docs) >= 20}
        recurrent = {label for label in teachable if len(test_domains[label]) >= 10}
        train_stats = structural_counts(train)
        test_stats = structural_counts(test)
        shared = sum(relation_id(rel) in teachable
                     for row in test for rel in row.get('relations') or [])
        coverage = shared/test_stats['triples'] if test_stats['triples'] else 0
        alignment = ((train_stats['aligned_mentions']+test_stats['aligned_mentions'])/
                     (train_stats['entity_mentions']+test_stats['entity_mentions'])
                     if train_stats['entity_mentions']+test_stats['entity_mentions'] else 0)
        gate = (len(train) >= 500 and len(test) >= 100 and len(recurrent) >= 5
                and coverage >= .50 and alignment >= .95)
        reports.append({'seed': seed, 'training_articles': len(all_articles)-len(heldout),
                        'heldout_articles': len(heldout), 'training': train_stats,
                        'heldout': test_stats,
                        'teachable_relations': len(teachable),
                        'recurrent_relations': len(recurrent),
                        'heldout_shared_triples': shared,
                        'heldout_relation_coverage': coverage,
                        'mention_alignment': alignment, 'gate_partition': gate})
    return len(all_articles), reports


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes de inventario')
    raw = source()
    rows = load(raw)
    articles, reports = partition(rows, h0)
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu <= 10 and wall <= 30 and rss <= 128*1024
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'development_document_source_gate_only',
              'preregistration': 'prereg/G-15-documentos-reales-y-relaciones.md',
              'source_url': URL, 'source_bytes': len(raw),
              'source_sha256': sha256(raw).hexdigest(),
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'rows': len(rows), 'articles': articles, 'reports': reports,
              'budget_ok': budget,
              'gate_pass': budget and all(r['gate_partition'] for r in reports),
              'cpu_total_s': round(cpu, 6), 'wall_total_s': round(wall, 6),
              'max_rss_kib': rss}
    path = ROOT / f'results_v3/g15_redfm_source_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante inventario')


if __name__ == '__main__':
    main()

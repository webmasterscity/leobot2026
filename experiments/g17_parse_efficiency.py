"""G-17: frozen before/after semantic-equivalence and CPU comparison."""
from __future__ import annotations

import json
import os
import resource
import statistics
import sys
import time
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g15_redfm_source_gate import source
from experiments.g16_frozen_document_learning import (SOURCE_SHA, articles,
    paired_examples, split_articles, teach_pairs, train_facts)
from leobot import Bot


ROOT = Path(__file__).resolve().parents[1]
H0 = '1f3187f2ced4c97364503187d074815f33612326'


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), default=str).encode()
    return sha256(encoded).hexdigest()


def percentile(values, share):
    return sorted(values)[int((len(values)-1)*share)] if values else None


def main(mode):
    if mode not in ('baseline', 'candidate'):
        raise ValueError('Modo inválido')
    cpu0, wall0 = time.process_time(), time.monotonic()
    tree = git('rev-parse', 'HEAD:leobot')
    if mode == 'baseline' and tree != H0:
        raise RuntimeError('Baseline debe usar H0')
    if mode == 'candidate' and tree == H0:
        raise RuntimeError('Tratamiento aún usa H0')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor sin congelar')
    raw = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente cambió')
    rows = [json.loads(line) for line in raw.splitlines()]
    training, _, _, _ = split_articles(rows, H0, 911)
    facts = train_facts(training)
    examples, example_stats = paired_examples(training)
    bot = Bot()
    tick = time.process_time()
    bot.ingest({'facts': facts})
    fact_cpu = time.process_time()-tick
    tick = time.process_time()
    paired = teach_pairs(bot, examples)
    pair_cpu = time.process_time()-tick
    queries = [item['text'] for item in examples[:12]]
    queries += [Bot._document_sentences(row['text'])[0] for row in training
                if Bot._document_sentences(row['text'])][:12]
    if len(queries) != 24:
        raise RuntimeError('No hay 24 frases de medición')
    parse_output, parse_latency = [], []
    tick = time.process_time()
    for text in queries:
        start = time.perf_counter_ns()
        parse_output.append(bot.language.parse(text))
        parse_latency.append((time.perf_counter_ns()-start)/1e6)
    parse_cpu = time.process_time()-tick
    doc_output, doc_latency = [], []
    chosen = articles(training)[:30]
    tick = time.process_time()
    for uri, text in chosen:
        start = time.perf_counter_ns()
        doc_output.append(bot.ingest_document_text(text, source='g17_education:'+uri))
        doc_latency.append((time.perf_counter_ns()-start)/1e6)
    document_cpu = time.process_time()-tick
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    unchanged = tree == git('rev-parse', 'HEAD:leobot') and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'G17_'+mode, 'preregistration': 'prereg/G-17-normalizacion-compartida.md',
              'engine_tree': tree, 'engine_unchanged': unchanged,
              'source_sha256': SOURCE_SHA, 'training_facts': len(facts),
              'paired_candidates': example_stats, 'paired_teaching': paired,
              'parse_queries': len(queries), 'documents': len(chosen),
              'parse_output_sha256': digest(parse_output),
              'document_output_sha256': digest(doc_output),
              'fact_count_after': bot.kb.stats()['facts'],
              'language_examples_after': len(bot.language.examples),
              'fact_cpu_s': round(fact_cpu, 6), 'pair_cpu_s': round(pair_cpu, 6),
              'parse_cpu_s': round(parse_cpu, 6),
              'document_cpu_s': round(document_cpu, 6),
              'parse_p50_ms': round(statistics.median(parse_latency), 6),
              'parse_p95_ms': round(percentile(parse_latency, .95), 6),
              'parse_max_ms': round(max(parse_latency), 6),
              'document_p50_ms': round(statistics.median(doc_latency), 6),
              'document_p95_ms': round(percentile(doc_latency, .95), 6),
              'document_max_ms': round(max(doc_latency), 6),
              'cpu_total_s': round(cpu, 6), 'wall_total_s': round(wall, 6),
              'max_rss_kib': rss}
    output['budget_ok'] = cpu <= 60 and wall <= 90 and rss <= 256*1024
    if mode == 'candidate':
        baseline = json.loads((ROOT/'results_v3/g17_baseline_hashseed0.json').read_text())
        output['parse_speedup'] = baseline['parse_cpu_s']/output['parse_cpu_s']
        output['document_speedup'] = baseline['document_cpu_s']/output['document_cpu_s']
        output['equivalent'] = all(output[key] == baseline[key] for key in (
            'paired_candidates','paired_teaching','parse_output_sha256',
            'document_output_sha256','fact_count_after','language_examples_after'))
        output['gate_pass'] = (output['budget_ok'] and output['equivalent'] and
                               output['parse_speedup'] >= 5 and
                               output['document_speedup'] >= 3 and
                               output['parse_p95_ms'] <= 10 and
                               output['document_max_ms'] <= 1000 and unchanged)
    path = ROOT/f'results_v3/g17_{mode}_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante G-17')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python -m experiments.g17_parse_efficiency baseline|candidate')
    main(sys.argv[1])

"""Postgate CPU profile of G-16 education; never touches excluded articles."""
from __future__ import annotations

import cProfile
import json
import resource
import time
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g15_redfm_source_gate import source
from experiments.g16_frozen_document_learning import (SOURCE_SHA, articles,
    paired_examples, split_articles, teach_pairs, train_facts)
from leobot import Bot


ROOT = Path(__file__).resolve().parents[1]


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente cambiada')
    rows = [json.loads(line) for line in raw.splitlines()]
    train, _, _, _ = split_articles(rows, h0, 911)
    bot = Bot()
    facts = train_facts(train)
    examples, candidate_stats = paired_examples(train)
    tick = time.process_time()
    bot.ingest({'facts': facts})
    facts_cpu = time.process_time()-tick
    tick = time.process_time()
    taught = teach_pairs(bot, examples)
    teach_cpu = time.process_time()-tick
    chosen = articles(train)[:3]
    profile = cProfile.Profile()
    tick = time.process_time()
    profile.enable()
    for uri, text in chosen:
        bot.ingest_document_text(text, source='profile_education:'+uri)
    profile.disable()
    ingest_cpu = time.process_time()-tick
    ranked = sorted(profile.getstats(), key=lambda row: -row.inlinetime)
    functions = []
    for row in ranked[:30]:
        code = row.code
        if hasattr(code, 'co_filename'):
            name = f'{Path(code.co_filename).name}:{code.co_firstlineno}:{code.co_name}'
        else:
            name = str(code)
        functions.append({'function': name, 'calls': row.callcount,
                          'own_cpu_s': round(row.inlinetime, 6),
                          'cumulative_cpu_s': round(row.totaltime, 6)})
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'postgate_profile_only', 'source': 'G-16 budget interruption',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'training_facts': len(facts), 'paired_candidates': candidate_stats,
              'paired_teaching': taught, 'profiled_articles': len(chosen),
              'facts_cpu_s': round(facts_cpu, 6), 'teach_cpu_s': round(teach_cpu, 6),
              'profiled_ingest_cpu_s': round(ingest_cpu, 6),
              'top_own_cpu': functions,
              'cpu_total_s': round(time.process_time()-cpu0, 6),
              'wall_total_s': round(time.monotonic()-wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT/'results_v3/g16_education_profile.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key:output[key] for key in ('training_facts','paired_candidates',
        'paired_teaching','profiled_articles','facts_cpu_s','teach_cpu_s',
        'profiled_ingest_cpu_s','cpu_total_s','wall_total_s','max_rss_kib')},
        ensure_ascii=False))
    for row in functions[:12]:
        print(row['function'], row['own_cpu_s'], row['cumulative_cpu_s'])
    if not unchanged:
        raise RuntimeError('Motor alterado en perfilado')


if __name__ == '__main__':
    main()

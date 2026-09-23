"""E-4 frozen diagnostic: is the answer represented in induced facts?"""
from __future__ import annotations

import json
import resource
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.agi_board import canonical
from experiments.e3_raw_curriculum import curriculum


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-E-4'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Tag cambiado')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor cambiado')


def contains_token_sequence(haystack, needle):
    outer, inner = canonical(haystack).split(), canonical(needle).split()
    return bool(inner) and any(outer[i:i + len(inner)] == inner
                               for i in range(len(outer) - len(inner) + 1))


def examine(bot, row):
    source = f'e4:test:{row["id"]}'
    report = bot.ingest_document_text(row['context'], source=source)
    facts = [fact for fact in bot.kb.facts.values()
             if str(fact['source']).startswith(source + ':oración:')]
    widths = []
    for fact in facts:
        for arg in fact['atom'].args:
            if any(contains_token_sequence(arg, answer) for answer in row['answers']):
                widths.append(len(canonical(arg).split()))
    answer = bot.respond(row['question'])
    return {'facts_added': report['facts_added'], 'test_source_facts': len(facts),
            'any_arg': bool(widths), 'short_arg': any(width <= 8 for width in widths),
            'min_arg_tokens': min(widths) if widths else None,
            'status': answer.get('status')}


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    if tree != git('rev-parse', 'freeze-E-3:leobot'):
        raise RuntimeError('Motor difiere de E-3')
    frozen(tree)
    start_wall, start_cpu = time.monotonic(), time.process_time()
    train, test, archive_bytes = curriculum(tree)
    educated = Bot()
    for i, row in enumerate(train):
        educated.ingest_document_text(row['context'], source=f'e4:train:{i}')
        if time.monotonic() - start_wall > 110:
            raise RuntimeError('Presupuesto de educación agotado')
    results = []
    with tempfile.TemporaryDirectory() as directory:
        saved = Path(directory) / 'educated.json'
        educated.save(saved)
        for row in test:
            results.append({'id': row['id'], 'fresh': examine(Bot(), row),
                            'educated': examine(Bot.load(saved), row)})
            if time.monotonic() - start_wall > 125 or time.process_time() - start_cpu > 85:
                raise RuntimeError('Presupuesto agotado')
    frozen(tree)
    counts = {condition: {key: sum(row[condition][key] for row in results)
                          for key in ('any_arg', 'short_arg', 'facts_added')}
              for condition in ('fresh', 'educated')}
    widths = [row['educated']['min_arg_tokens'] for row in results
              if row['educated']['min_arg_tokens'] is not None]
    outcome = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
               'preregistration': 'prereg/E-4-cobertura-de-hechos-opacos.md',
               'train_articles': len(train), 'test_articles': len(test),
               'archive_bytes': archive_bytes, 'counts': counts,
               'median_min_matching_arg_tokens': statistics.median(widths) if widths else None,
               'cpu_s': round(time.process_time() - start_cpu, 6),
               'wall_s': round(time.monotonic() - start_wall, 3),
               'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'rows': results}
    path = ROOT / 'results_v3' / 'e4_fact_coverage.json'
    path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in outcome.items() if key != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    run()

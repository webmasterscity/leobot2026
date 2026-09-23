"""E-6b frozen comparison of long-argument compression gate and old learner."""
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
from experiments.e4_fact_coverage import contains_token_sequence
from experiments.e5_clause_fragments import scrambled


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-E-6b'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Tag cambió')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no sigue congelado')


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
                 'e3_raw_curriculum.json', 'e5_clause_fragments.json'):
        prior = json.loads((ROOT / 'results_v3' / name).read_text(encoding='utf8'))
        excluded.update(row['id'] for row in prior['rows'])
    by_article = {}
    for row in rows:
        if row['id'] not in excluded:
            by_article.setdefault(row['article'], []).append(row)
    names = sorted(by_article)
    seed = int(sha256((tree + ':E-6b').encode()).hexdigest()[:8], 16)
    random.Random(seed).shuffle(names)
    if len(names) < 50:
        raise RuntimeError('Faltan artículos')
    return ([by_article[name][0] for name in names[:30]],
            [by_article[name][0] for name in names[30:50]], len(data), seed)


def score(bot, row, context=None):
    source = f'e6b:test:{row["id"]}'
    report = bot.ingest_document_text(row['context'] if context is None else context,
                                      source=source)
    facts = [fact for fact in bot.kb.facts.values()
             if str(fact['source']).startswith(source + ':oración:')]
    widths = [len(canonical(arg).split()) for fact in facts for arg in fact['atom'].args
              if any(contains_token_sequence(arg, answer) for answer in row['answers'])]
    response = bot.respond(row['question'])
    return {'any_arg': bool(widths), 'short_arg': any(w <= 8 for w in widths),
            'facts_added': report['facts_added'],
            'promotions': report['relations_promoted'],
            'candidates_examined': report['raw_candidates_examined'],
            'exact': canonical(response.get('text', '')) in
                     {canonical(answer) for answer in row['answers']},
            'status': response.get('status')}


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    frozen(tree)
    start_wall, start_cpu = time.monotonic(), time.process_time()
    train, test, archive_bytes, seed = sample(tree)
    flags = {'treatment': True, 'ablation': False,
             'shuffled_treatment': True, 'shuffled_ablation': False}
    arms = {name: Bot(raw_relation_mdl=enabled) for name, enabled in flags.items()}
    training = {}
    for name, bot in arms.items():
        tick = time.process_time()
        facts = promotions = candidates = 0
        for i, row in enumerate(train):
            context = scrambled(row['context'], seed + i) if name.startswith('shuffled') else row['context']
            report = bot.ingest_document_text(context, source=f'e6b:train:{i}')
            facts += report['facts_added']
            promotions += report['relations_promoted']
            candidates += report['raw_candidates_examined']
            if time.monotonic() - start_wall > 160 or time.process_time() - start_cpu > 110:
                raise RuntimeError('Presupuesto de educación agotado')
        training[name] = {'facts': facts, 'promotions': promotions,
                          'candidates_examined': candidates,
                          'cpu_s': round(time.process_time() - tick, 6)}
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        paths = {}
        for name, bot in arms.items():
            path = Path(directory) / f'{name}.json'
            bot.save(path)
            paths[name] = path
        reload_ok = all(Bot.load(path).as_dict() == arms[name].as_dict()
                        for name, path in paths.items())
        for i, row in enumerate(test):
            result = {'id': row['id']}
            for name in flags:
                context = scrambled(row['context'], seed + 1000 + i) if name.startswith('shuffled') else None
                result[name] = score(Bot.load(paths[name]), row, context=context)
            result['fresh'] = score(Bot(), row)
            rows.append(result)
            if time.monotonic() - start_wall > 175 or time.process_time() - start_cpu > 118:
                raise RuntimeError('Presupuesto de ensayo agotado')
    counts = {name: {metric: sum(row[name][metric] for row in rows)
                     for metric in ('any_arg', 'short_arg', 'facts_added',
                                    'promotions', 'candidates_examined', 'exact')}
              for name in (*flags, 'fresh')}
    counterevidence = {'tested': False, 'reason': 'no_promotion'}
    promotions = list(arms['treatment'].raw_relation_promotions.values())
    if promotions:
        chosen = promotions[0]
        pred = chosen['predicate']
        before = sum(f['atom'].pred == pred for f in arms['treatment'].kb.facts.values())
        arms['treatment'].ingest_document_text('No ' + chosen['evidence'][0]['text'] + '.',
                                              source='e6b:contra')
        after = sum(f['atom'].pred == pred for f in arms['treatment'].kb.facts.values())
        counterevidence = {'tested': True, 'positive_facts_before': before,
                           'positive_facts_after': after,
                           'positive_withdrawn': after < before}
    frozen(tree)
    outcome = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
               'preregistration': 'prereg/E-6b-longitud-de-argumentos.md',
               'train_articles': len(train), 'test_articles': len(test),
               'archive_bytes': archive_bytes, 'training': training,
               'counts': counts, 'reload_ok': reload_ok,
               'counterevidence': counterevidence,
               'cpu_s': round(time.process_time() - start_cpu, 6),
               'wall_s': round(time.monotonic() - start_wall, 3),
               'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'rows': rows}
    path = ROOT / 'results_v3' / 'e6b_mdl_filter.json'
    path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in outcome.items() if key != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    run()

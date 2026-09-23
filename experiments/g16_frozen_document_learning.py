"""G-16: frozen Leobot learns from paired Wikipedia sentences and facts."""
from __future__ import annotations

import json
import os
import random
import resource
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g15_redfm_source_gate import SEEDS, relation_id, source
from leobot import Bot
from leobot.language import normalize


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '3af0fff77d7bb3d2907839e1db8e33d56b8e84ae17309f056257f240ec8127b8'


def triple(row, relation):
    return (relation_id(relation),
            normalize(relation['subject']['surfaceform']),
            normalize(relation['object']['surfaceform']))


def teachable_sentence(row, relation):
    subject = normalize(relation['subject']['surfaceform'])
    object_ = normalize(relation['object']['surfaceform'])
    sentences = [sentence for sentence in Bot._document_sentences(row['text'])
                 if subject in normalize(sentence) and object_ in normalize(sentence)]
    return sentences[0] if len(sentences) == 1 else None


def paired_examples(rows):
    chosen = []
    stats = Counter()
    for row in rows:
        relations = row.get('relations') or []
        if len(relations) != 1:
            continue
        stats['single_triple_paragraphs'] += 1
        relation = relations[0]
        sentence = teachable_sentence(row, relation)
        if sentence is None:
            stats['sentence_not_unique'] += 1
            continue
        pred, subject, object_ = triple(row, relation)
        chosen.append({'text': sentence,
                       'frame': {'act': 'assert', 'pred': pred,
                                 'args': [relation['subject']['surfaceform'],
                                          relation['object']['surfaceform']]},
                       'types': (relation['subject'].get('type'),
                                 relation['object'].get('type')),
                       'uri': row['uri']})
    stats['paired_candidates'] = len(chosen)
    return chosen, dict(stats)


def split_articles(rows, h0, seed):
    by_article = defaultdict(list)
    for row in rows:
        by_article[row['uri']].append(row)
    articles = sorted(by_article)
    random.Random(int(h0[:8], 16) ^ seed ^ 0x69B).shuffle(articles)
    heldout = set(articles[:max(20, round(.2*len(articles)))])
    training = [row for article in sorted(by_article) if article not in heldout
                for row in by_article[article]]
    test = [row for article in sorted(by_article) if article in heldout
            for row in by_article[article]]
    return training, test, len(articles)-len(heldout), len(heldout)


def train_facts(rows):
    facts = []
    for row in rows:
        for relation in row.get('relations') or []:
            pred, subject, object_ = triple(row, relation)
            facts.append({'pred': pred, 'args': [subject, object_],
                          'source': 'education:'+row['uri']})
    return facts


def shuffled_examples(examples, h0, seed):
    grouped = defaultdict(list)
    for item in examples:
        grouped[item['types']].append(item)
    rng = random.Random(int(h0[:8], 16) ^ seed ^ 0x39A)
    out = []
    for types, items in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        predicates = [item['frame']['pred'] for item in items]
        rng.shuffle(predicates)
        for item, pred in zip(items, predicates):
            out.append({**item, 'frame': {**item['frame'], 'pred': pred}})
    return out


def teach_pairs(bot, examples):
    count = Counter()
    for item in examples:
        try:
            changed = bot.language.teach(item['text'], item['frame'],
                                          'redfm_explicit_pair')
            count['accepted'] += changed
            count['duplicates'] += not changed
        except ValueError:
            count['rejected'] += 1
    return dict(count)


def articles(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['uri']].append(row['text'])
    return [(uri, '\n'.join(texts)) for uri, texts in sorted(grouped.items())]


def educate(bot, rows, facts, examples, *, pair=False):
    before = time.process_time()
    bot.ingest({'facts': facts})
    fact_cpu = time.process_time()-before
    pair_cpu = 0.0
    pairs = {}
    if pair:
        tick = time.process_time()
        pairs = teach_pairs(bot, examples)
        pair_cpu = time.process_time()-tick
    raw_cpu = 0.0
    docs = articles(rows)
    processed = 0
    tick = time.process_time()
    for uri, text in docs:
        bot.ingest_document_text(text, source='education_doc:'+uri)
        processed += 1
        if time.process_time()-tick > 95:
            raise RuntimeError(f'Presupuesto de educación documental agotado tras {processed}/{len(docs)} artículos')
    raw_cpu = time.process_time()-tick
    return {'facts': len(facts), 'pair_report': pairs,
            'articles_ingested': processed, 'fact_cpu_s': fact_cpu,
            'pair_cpu_s': pair_cpu, 'raw_cpu_s': raw_cpu}


def test_bot(bot, rows, education_triples, education_pairs, name):
    by_article = defaultdict(list)
    for row in rows:
        by_article[row['uri']].append(row)
    stats = Counter()
    latency = []
    one = Counter()
    predicates_correct = set()
    for uri, docs in sorted(by_article.items()):
        for index, row in enumerate(docs):
            source_key = f'g16_test_{name}_{uri}_{index}'
            start_fact = bot.kb.next_id
            tick = time.perf_counter()
            bot.ingest_document_text(row['text'], source=source_key)
            elapsed = time.perf_counter()-tick
            latency.append(elapsed)
            if elapsed > 1:
                stats['documents_over_1s'] += 1
            newly = [bot.kb.facts[f'f{num}'] for num in range(start_fact+1, bot.kb.next_id+1)
                     if f'f{num}' in bot.kb.facts and
                     str(bot.kb.facts[f'f{num}']['source']).startswith(source_key)]
            gold = {triple(row, relation) for relation in row.get('relations') or []}
            novel = {value for value in gold if value not in education_triples}
            new_pairs = {value for value in novel if value[1:] not in education_pairs}
            predicted = {(fact['atom'].pred, *fact['atom'].args) for fact in newly
                         if fact['atom'].pred.startswith('P')}
            correct = novel & predicted
            stats['paragraphs'] += 1
            stats['gold_triples'] += len(gold)
            stats['novel_gold_triples'] += len(novel)
            stats['novel_pair_gold_triples'] += len(new_pairs)
            stats['correct_novel'] += len(correct)
            stats['correct_new_pair'] += len(new_pairs & predicted)
            stats['new_p_facts'] += len(predicted)
            stats['p_fact_matches_gold'] += len(predicted & gold)
            predicates_correct.update(value[0] for value in correct)
            if len(gold) == 1:
                one['paragraphs'] += 1
                one['novel_gold'] += len(novel)
                one['correct_novel'] += len(correct)
            if stats['documents_over_1s'] and stats['documents_over_1s'] >= 3:
                raise RuntimeError(f'Lectura de documentos excedió 1 s ({name})')
    p95 = sorted(latency)[int((len(latency)-1)*.95)] if latency else 0
    return {'counts': dict(stats), 'single_triple': dict(one),
            'correct_predicates': len(predicates_correct),
            'document_p50_ms': statistics.median(latency)*1000 if latency else 0,
            'document_p95_ms': p95*1000}


def parse_probe(bot, rows):
    samples = [Bot._document_sentences(row['text'])[0] for row in rows
               if len(row.get('relations') or []) == 1 and Bot._document_sentences(row['text'])]
    times = []
    status = Counter()
    for sentence in samples:
        tick = time.perf_counter()
        result = bot.language.parse(sentence)
        times.append((time.perf_counter()-tick)*1000)
        status[result['status']] += 1
    return {'samples': len(samples), 'status': dict(status),
            'p50_ms': statistics.median(times) if times else None,
            'p95_ms': sorted(times)[int((len(times)-1)*.95)] if times else None,
            'max_ms': max(times) if times else None}


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del ensayo')
    raw = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente cambió')
    rows = [json.loads(line) for line in raw.splitlines()]
    train, test, train_articles, test_articles = split_articles(rows, h0, seed)
    reading_cpu = time.process_time()-cpu0
    facts = train_facts(train)
    examples, example_stats = paired_examples(train)
    shuffled = shuffled_examples(examples, h0, seed)
    training_triples = {(f['pred'], *f['args']) for f in facts}
    training_pairs = {tuple(f['args']) for f in facts}
    bots = {name: Bot() for name in ('treatment','ablation','shuffled','memory','fresh')}
    educational = {}
    for name in ('treatment','ablation','shuffled'):
        educational[name] = educate(bots[name], train, facts,
                                    examples if name == 'treatment' else shuffled,
                                    pair=name != 'ablation')
        print(f'educated {name}: {educational[name]["articles_ingested"]} articles',
              file=sys.stderr, flush=True)
        if time.process_time()-cpu0 > 110:
            raise RuntimeError('Presupuesto CPU agotado durante educación')
    bots['memory'].ingest({'facts': facts})
    before_restart = (len(bots['treatment'].language.examples),
                      len(bots['treatment'].language.constructions),
                      bots['treatment'].kb.stats()['facts'])
    with tempfile.NamedTemporaryFile(suffix='.json') as stream:
        bots['treatment'].save(stream.name)
        bots['treatment'] = Bot.load(stream.name)
    after_restart = (len(bots['treatment'].language.examples),
                     len(bots['treatment'].language.constructions),
                     bots['treatment'].kb.stats()['facts'])
    restart_same = before_restart == after_restart
    parsing = parse_probe(bots['treatment'], test)
    # Previously taught facts are deliberately excluded from credited outcomes.
    results = {}
    for name in ('treatment','ablation','shuffled','memory','fresh'):
        results[name] = test_bot(bots[name], test, training_triples, training_pairs, name)
        print(f'tested {name}: {results[name]["counts"].get("correct_novel",0)} new facts',
              file=sys.stderr, flush=True)
        if time.process_time()-cpu0 > 120:
            raise RuntimeError('Presupuesto CPU agotado durante prueba')
    t = results['treatment']
    controls = [results[name] for name in ('ablation','shuffled','memory','fresh')]
    one_gold = t['single_triple'].get('novel_gold',0)
    all_gold = t['counts'].get('novel_gold_triples',0)
    best_one = max(c['single_triple'].get('correct_novel',0) for c in controls)
    best_all = max(c['counts'].get('correct_novel',0) for c in controls)
    precision = (t['counts'].get('p_fact_matches_gold',0)/t['counts'].get('new_p_facts',1)
                 if t['counts'].get('new_p_facts') else 0)
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = (cpu <= 120 and wall <= 180 and rss <= 256*1024 and
              not t['counts'].get('documents_over_1s') and
              parsing['p95_ms'] is not None and parsing['p95_ms'] <= 10 and
              parsing['max_ms'] <= 1000)
    gate = (budget and restart_same and one_gold > 0 and all_gold > 0 and
            t['single_triple'].get('correct_novel',0)/one_gold >= .20 and
            t['counts'].get('correct_novel',0)/all_gold >= .05 and
            (t['single_triple'].get('correct_novel',0)-best_one)/one_gold >= .10 and
            (t['counts'].get('correct_novel',0)-best_all)/all_gold >= .10 and
            t['correct_predicates'] >= 5 and precision >= .80)
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'frozen_engine_document_learning',
              'preregistration': 'prereg/G-16-educacion-documental-congelada.md',
              'seed': seed, 'engine_tree': h0, 'engine_unchanged': unchanged,
              'source_sha256': SOURCE_SHA, 'training_articles': train_articles,
              'heldout_articles': test_articles, 'training_paragraphs': len(train),
              'test_paragraphs': len(test), 'education_candidates': example_stats,
              'education': educational, 'results': results,
              'restart_same': restart_same, 'parse_probe': parsing,
              'observable_precision': precision,
              'best_control_single_correct': best_one,
              'best_control_all_correct': best_all,
              'reading_cpu_s': round(reading_cpu, 6),
              'budget_ok': budget, 'gate_pass': gate,
              'cpu_total_s': round(cpu, 6), 'wall_total_s': round(wall, 6),
              'max_rss_kib': rss}
    path = ROOT / f'results_v3/g16_frozen_document_seed{seed}_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante ensayo')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python -m experiments.g16_frozen_document_learning 911|977|1039')
    try:
        main(int(sys.argv[1]))
    except RuntimeError as error:
        seed = int(sys.argv[1])
        h0 = git('rev-parse', 'estable-E-1:leobot')
        interrupted = {'kind': 'budget_or_execution_interruption',
                       'preregistration': 'prereg/G-16-educacion-documental-congelada.md',
                       'seed': seed, 'reason': str(error), 'engine_tree': h0,
                       'engine_unchanged': git('rev-parse', 'HEAD:leobot') == h0 and
                                           not git('status', '--porcelain', '--', 'leobot')}
        (ROOT/f'results_v3/g16_frozen_document_interruption_seed{seed}.json').write_text(
            json.dumps(interrupted, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(interrupted, ensure_ascii=False), file=sys.stderr)
        raise

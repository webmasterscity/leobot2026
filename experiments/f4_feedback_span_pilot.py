"""F-4 preregistered pilot: explicit contrastive counts for answer spans."""
from __future__ import annotations

import io
import json
import math
import random
import re
import resource
import statistics
import subprocess
import tempfile
import time
import urllib.request
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.agi_board import canonical


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-F-4-piloto'
SQAC_COMMIT = 'f9928e8819596a601b8887cc5f8598b15d589a82'
XQUAD_COMMIT = '7d30520c717524000f0d9d2f9c10a069acd9d285'
SOURCES = {
    'sqac_train': (
        f'https://huggingface.co/datasets/PlanTL-GOB-ES/SQAC/resolve/{SQAC_COMMIT}/train.json',
        '1d5c76176646e2ae7bdcd8b5ec6f18349102a9363aa25ad7d0e48262d7480d43'),
    'sqac_dev': (
        f'https://huggingface.co/datasets/PlanTL-GOB-ES/SQAC/resolve/{SQAC_COMMIT}/dev.json',
        'ec748f222626e5081a34193ca469bcf8112092837678a6948a2d6ae7d6629d1a'),
    'xquad': (
        f'https://raw.githubusercontent.com/google-deepmind/xquad/{XQUAD_COMMIT}/xquad.es.json',
        'dcbae93ec3a9f4b9e78fd834a171d6f96c1a875e10e15b7530b7e4ef4971e37e'),
}
EXPOSED_SAMPLE_ID = '6cf3dcd6-b5a3-4516-8f9e-c5c1c6b66628'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Motor etiquetado alterado')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor de trabajo alterado')


def download(name):
    url, expected = SOURCES[name]
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024 or sha256(data).hexdigest() != expected:
        raise RuntimeError(f'Fuente {name} fuera del preregistro')
    return json.loads(data), len(data)


def flatten(document):
    rows = []
    for article in document['data']:
        for paragraph in article['paragraphs']:
            context = paragraph['context']
            for qa in paragraph['qas']:
                answers = [answer['text'] for answer in qa.get('answers', [])
                           if isinstance(answer.get('text'), str) and answer['text']]
                if not answers or qa['id'] == EXPOSED_SAMPLE_ID:
                    continue
                rows.append({'id': str(qa['id']), 'context': context,
                             'question': qa['question'], 'answers': answers,
                             'context_key': sha256(context.encode()).hexdigest()})
    return rows


def words(text):
    return [(match, canonical(match.group())) for match in re.finditer(r'[^\W_]+', text)
            if canonical(match.group())]


def candidates(context, question):
    qwords = canonical(question).split()
    qset = set(qwords)
    ranked = []
    for index, sentence in enumerate(Bot._document_sentences(context)):
        tokens = words(sentence)
        overlap = len(qset & {word for _, word in tokens})
        ranked.append((overlap, index, sentence, tokens))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    out = []
    for overlap, index, sentence, tokens in ranked[:5]:
        for start in range(len(tokens)):
            for end in range(start + 1, min(len(tokens), start + 8) + 1):
                text = sentence[tokens[start][0].start():tokens[end - 1][0].end()]
                out.append({'text': text, 'tokens': tokens, 'start': start, 'end': end,
                            'overlap': overlap, 'sentence_index': index,
                            'sentence': sentence, 'qwords': qwords, 'qset': qset})
    return out


def features(candidate):
    tokens = candidate['tokens']; start, end = candidate['start'], candidate['end']
    qset, qwords = candidate['qset'], candidate['qwords']
    qhead = qwords[0] if qwords else '<empty>'
    text = candidate['text']
    shape = ('number' if any(char.isdigit() for char in text) else
             'capital' if text[:1].isupper() else 'lower')
    left = tokens[start - 1][1] if start else '<start>'
    right = tokens[end][1] if end < len(tokens) else '<end>'
    left_gap = next((start - i for i in range(start - 1, -1, -1)
                     if tokens[i][1] in qset), 99)
    right_gap = next((i - end + 1 for i in range(end, len(tokens))
                      if tokens[i][1] in qset), 99)
    gap_bucket = lambda value: 'none' if value == 99 else str(min(value, 4))
    length = end - start
    overlap = min(candidate['overlap'], 5)
    in_question = all(tokens[i][1] in qset for i in range(start, end))
    result = {'length:' + str(length), 'shape:' + shape,
              'overlap:' + str(overlap), 'left_gap:' + gap_bucket(left_gap),
              'right_gap:' + gap_bucket(right_gap),
              'in_question:' + str(in_question),
              'qhead_shape:' + qhead + '|' + shape,
              'qhead_length:' + qhead + '|' + str(length),
              'qhead_left_gap:' + qhead + '|' + gap_bucket(left_gap),
              'qhead_right_gap:' + qhead + '|' + gap_bucket(right_gap),
              'left_context:' + left, 'right_context:' + right,
              'qhead_left_context:' + qhead + '|' + left,
              'qhead_right_context:' + qhead + '|' + right}
    return tuple(sorted(result))


class ContrastiveSpans:
    def __init__(self):
        self.positive = Counter()
        self.negative = Counter()
        self.episodes = {}
        self.positive_total = 0
        self.negative_total = 0

    def observe(self, identifier, positive, negatives):
        if identifier in self.episodes:
            self.remove(identifier)
        pos = features(positive)
        neg = [features(row) for row in negatives]
        self.episodes[identifier] = {'positive': pos, 'negative': neg}
        self.positive.update(pos)
        for row in neg:
            self.negative.update(row)
        self.positive_total += 1
        self.negative_total += len(neg)

    def remove(self, identifier):
        episode = self.episodes.pop(identifier)
        self.positive.subtract(episode['positive'])
        for row in episode['negative']:
            self.negative.subtract(row)
        self.positive_total -= 1
        self.negative_total -= len(episode['negative'])

    def score(self, row):
        total = 0.0
        for feature in features(row):
            positive = self.positive[feature]
            negative = self.negative[feature]
            if positive + negative < 5:
                continue
            pos_rate = (positive + 1) / (self.positive_total + 2)
            neg_rate = (negative + 1) / (self.negative_total + 2)
            total += math.log(pos_rate / neg_rate)
        return total

    def predict(self, context, question):
        rows = candidates(context, question)
        by_text = {}
        for row in rows:
            if row['overlap'] < 2:
                continue
            normalized = canonical(row['text'])
            value = self.score(row)
            prior = by_text.get(normalized)
            if prior is None or value > prior[0]:
                by_text[normalized] = (value, row)
        ordered = sorted(by_text.values(), key=lambda item: (-item[0],
                                                              len(item[1]['text']),
                                                              item[1]['text']))
        if not ordered:
            return {'status': 'abstain', 'answer': None, 'candidates': len(rows),
                    'reason': 'no_shared_evidence', 'high_confidence': False}
        top, row = ordered[0]
        margin = top - ordered[1][0] if len(ordered) > 1 else top
        accepted = top > 0 and margin >= 0.25
        return {'status': 'span_candidate' if accepted else 'abstain',
                'answer': row['text'] if accepted else None,
                'source_sentence_index': row['sentence_index'] if accepted else None,
                'score': round(top, 6), 'margin': round(margin, 6),
                'high_confidence': bool(accepted and margin >= 1.5),
                'candidates': len(rows)}

    def as_dict(self):
        return {'episodes': {key: {'positive': list(value['positive']),
                                  'negative': [list(row) for row in value['negative']]}
                             for key, value in sorted(self.episodes.items())}}

    @classmethod
    def from_dict(cls, data):
        model = cls()
        for key, value in sorted(data['episodes'].items()):
            positive = tuple(value['positive'])
            negative = [tuple(row) for row in value['negative']]
            model.episodes[key] = {'positive': positive, 'negative': negative}
            model.positive.update(positive)
            for row in negative:
                model.negative.update(row)
            model.positive_total += 1
            model.negative_total += len(negative)
        return model


def train_model(rows):
    model = ContrastiveSpans()
    used = skipped = enumerated = 0
    start = time.process_time()
    for row in rows:
        options = candidates(row['context'], row['question'])
        enumerated += len(options)
        gold = {canonical(value) for value in row['answers']}
        positive = next((candidate for candidate in options
                         if canonical(candidate['text']) in gold), None)
        if positive is None:
            skipped += 1
            continue
        negatives = [candidate for candidate in options
                     if canonical(candidate['text']) not in gold]
        same = [candidate for candidate in negatives
                if candidate['sentence_index'] == positive['sentence_index']]
        rng = random.Random(int(sha256(row['id'].encode()).hexdigest()[:8], 16))
        chosen = rng.sample(same, min(4, len(same)))
        remaining = [candidate for candidate in negatives if candidate not in chosen]
        chosen += rng.sample(remaining, min(8 - len(chosen), len(remaining)))
        model.observe(row['id'], positive, chosen)
        used += 1
    return model, {'examples_used': used, 'examples_skipped': skipped,
                   'candidates_enumerated': enumerated,
                   'cpu_s': round(time.process_time() - start, 6)}


def select_distinct(rows, count, seed):
    by_context = {}
    for row in sorted(rows, key=lambda row: row['id']):
        by_context.setdefault(row['context_key'], row)
    keys = random.Random(seed).sample(sorted(by_context), count)
    return [by_context[key] for key in keys]


def evaluate(model, rows, wrong_passages=False):
    results = []; query_wall = []; cpu_start = time.process_time()
    for index, row in enumerate(rows):
        context = (rows[(index + 1) % len(rows)]['context']
                   if wrong_passages else row['context'])
        tick = time.perf_counter()
        prediction = model.predict(context, row['question'])
        query_wall.append(time.perf_counter() - tick)
        exact = prediction['answer'] is not None and canonical(prediction['answer']) in {
            canonical(value) for value in row['answers']}
        results.append({'id': row['id'], 'status': prediction['status'],
                        'exact': exact, 'high_confidence': prediction['high_confidence'],
                        'candidates': prediction['candidates']})
    milliseconds = sorted(value * 1000 for value in query_wall)
    attempts = sum(row['status'] == 'span_candidate' for row in results)
    correct = sum(row['exact'] for row in results)
    return {'total': len(rows), 'correct': correct, 'attempts': attempts,
            'precision': round(correct / attempts, 6) if attempts else None,
            'high_confidence_attempts': sum(row['high_confidence'] for row in results),
            'candidates_examined': sum(row['candidates'] for row in results),
            'cpu_s': round(time.process_time() - cpu_start, 6),
            'p50_ms': round(statistics.median(milliseconds), 5),
            'p95_ms': round(milliseconds[(95 * len(milliseconds) + 99) // 100 - 1], 5),
            'rows': results}


def sentence_retrieval(rows):
    covered = exact = 0
    for row in rows:
        qset = set(canonical(row['question']).split())
        sentences = Bot._document_sentences(row['context'])
        best = max(sentences, key=lambda sentence: len(qset & set(canonical(sentence).split())),
                   default='')
        normalized = canonical(best)
        answers = {canonical(answer) for answer in row['answers']}
        exact += normalized in answers
        covered += any(answer in normalized for answer in answers)
    return {'total': len(rows), 'exact': exact, 'answer_in_sentence': covered}


def run(dev=False):
    started_wall, started_cpu = time.monotonic(), time.process_time()
    tree = git('rev-parse', 'estable-E-1:leobot') if dev else git('rev-parse', f'{TAG}:leobot')
    if not dev:
        frozen(tree)
    train_doc, train_bytes = download('sqac_train')
    train_rows = flatten(train_doc)
    train_pool = sorted(train_rows, key=lambda row: row['id'])
    taught = random.Random(1642).sample(train_pool, 2000)
    model, learning = train_model(taught)
    if dev:
        used = {row['id'] for row in taught}
        held = select_distinct([row for row in train_rows if row['id'] not in used],
                               64, 2117)
        sources = {'sqac_train_development': held}
        source_bytes = train_bytes
    else:
        dev_doc, dev_bytes = download('sqac_dev')
        xquad_doc, xquad_bytes = download('xquad')
        sqac = select_distinct(flatten(dev_doc), 100, int(sha256(
            (tree + ':F-4:sqac_dev').encode()).hexdigest()[:8], 16))
        xquad = select_distinct(flatten(xquad_doc), 100, int(sha256(
            (tree + ':F-4:xquad').encode()).hexdigest()[:8], 16))
        sources = {'sqac_dev': sqac, 'xquad': xquad}
        source_bytes = train_bytes + dev_bytes + xquad_bytes
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'span_model.json'
        tick = time.process_time()
        path.write_text(json.dumps(model.as_dict(), ensure_ascii=False), encoding='utf8')
        loaded = ContrastiveSpans.from_dict(json.loads(path.read_text(encoding='utf8')))
        restart_cpu = time.process_time() - tick
        restart_same = loaded.as_dict() == model.as_dict()
    results = {name: evaluate(loaded, rows) for name, rows in sources.items()}
    fresh = {name: evaluate(ContrastiveSpans(), rows) for name, rows in sources.items()}
    retrieval = {name: sentence_retrieval(rows) for name, rows in sources.items()}
    incompatible = {name: evaluate(loaded, rows, wrong_passages=True) for name, rows in sources.items()}
    correction_id = next(row['id'] for row in taught if row['id'] in model.episodes)
    before = model.as_dict()
    positive_before = model.positive.copy()
    negative_before = model.negative.copy()
    model.remove(correction_id)
    removed = (correction_id not in model.episodes
               and model.positive_total == learning['examples_used'] - 1
               and model.positive != positive_before)
    removed_model = ContrastiveSpans.from_dict(model.as_dict())
    correction_reversible = (removed and removed_model.positive == model.positive
                             and removed_model.negative == model.negative
                             and ContrastiveSpans.from_dict(before).positive == positive_before
                             and ContrastiveSpans.from_dict(before).negative == negative_before)
    if not dev:
        frozen(tree)
    gate = (not dev and results['sqac_dev']['correct'] >= 15
            and results['xquad']['correct'] >= 10
            and all(results[name]['correct'] - fresh[name]['correct'] >= 5 for name in sources)
            and all(results[name]['precision'] is not None and results[name]['precision'] >= 0.5
                    for name in sources)
            and all(incompatible[name]['high_confidence_attempts'] <= 5 for name in sources)
            and restart_same and correction_reversible
            and all(results[name]['p95_ms'] <= 10 for name in sources)
            and learning['cpu_s'] <= 30)
    output = {'tag': 'development' if dev else TAG, 'engine_tree': tree,
              'engine_unchanged': not dev,
              'preregistration': 'prereg/F-4-roles-desde-feedback.md',
              'source_bytes': source_bytes, 'learning': learning,
              'results': results, 'fresh': fresh, 'retrieval': retrieval,
              'incompatible': incompatible,
              'restart_same': restart_same, 'restart_cpu_s': round(restart_cpu, 6),
              'correction_reversible': correction_reversible,
              'gate_passed': bool(gate),
              'cpu_total_s': round(time.process_time() - started_cpu, 6),
              'wall_total_s': round(time.monotonic() - started_wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3' / ('f4_span_dev.json' if dev else 'f4_span_freeze.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('results', 'fresh', 'retrieval', 'incompatible')}
                     | {name: {family: {key: value for key, value in data.items() if key != 'rows'}
                                for family, data in output[name].items()}
                        for name in ('results', 'fresh', 'retrieval', 'incompatible')}, ensure_ascii=False))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true')
    run(parser.parse_args().dev)

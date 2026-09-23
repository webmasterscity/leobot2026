"""Preregistered F-5 pilot: episode-local contrast for answer roles."""
from __future__ import annotations

import json
import random
import resource
import statistics
import tempfile
import time
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.f4_feedback_span_pilot import (
    ROOT, canonical, download, evaluate as f4_evaluate,
    flatten, git, select_distinct, sentence_retrieval, words,
)


TAG = 'freeze-F-5'


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Motor etiquetado alterado')
    if (git('diff','--name-only',TAG,'--','leobot') or
            git('status','--porcelain','--','leobot')):
        raise RuntimeError('Motor de trabajo alterado')


def candidates(context, question):
    qwords = canonical(question).split()
    qset = set(qwords)
    ranked = []
    for index, sentence in enumerate(Bot._document_sentences(context)):
        tokens = words(sentence)
        overlap = len(qset & {word for _, word in tokens})
        ranked.append((overlap, index, sentence, tokens))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    out = []
    for overlap, index, sentence, tokens in ranked[:2]:
        for start in range(len(tokens)):
            for end in range(start + 1, min(len(tokens), start + 8) + 1):
                out.append({'text': sentence[tokens[start][0].start():tokens[end-1][0].end()],
                            'tokens': tokens, 'start': start, 'end': end,
                            'overlap': overlap, 'sentence_index': index,
                            'sentence': sentence, 'qwords': qwords, 'qset': qset})
    return out


def bucket(value):
    return 'none' if value is None else str(min(value, 4))


def features(row, boundary_vocab):
    tokens = row['tokens']; start = row['start']; end = row['end']
    qwords = row['qwords']; qset = row['qset']
    qhead = qwords[0] if qwords else '<empty>'
    text = row['text']
    first = tokens[start][1]; last = tokens[end-1][1]
    before = tokens[start-1][1] if start else '<start>'
    after = tokens[end][1] if end < len(tokens) else '<end>'
    before2 = tokens[start-2][1] if start > 1 else '<start>'
    after2 = tokens[end+1][1] if end+1 < len(tokens) else '<end>'
    left_matches = [i for i in range(start) if tokens[i][1] in qset]
    right_matches = [i for i in range(end, len(tokens)) if tokens[i][1] in qset]
    left_gap = start - left_matches[-1] if left_matches else None
    right_gap = right_matches[0] - end + 1 if right_matches else None
    left_char = row['sentence'][tokens[start][0].start()-1:tokens[start][0].start()]
    right_char = row['sentence'][tokens[end-1][0].end():tokens[end-1][0].end()+1]
    shape = ('number' if any(c.isdigit() for c in text) else
             'capital' if text[:1].isupper() else 'lower')
    length = end-start
    out = {'length:' + str(length), 'shape:' + shape,
           'qhead_length:' + qhead + '|' + str(length),
           'qhead_shape:' + qhead + '|' + shape,
           'left_gap:' + bucket(left_gap), 'right_gap:' + bucket(right_gap),
           'qhead_left_gap:' + qhead + '|' + bucket(left_gap),
           'qhead_right_gap:' + qhead + '|' + bucket(right_gap),
           'left_count:' + str(min(len(left_matches), 4)),
           'right_count:' + str(min(len(right_matches), 4)),
           'qhead_left_count:' + qhead + '|' + str(min(len(left_matches), 4)),
           'qhead_right_count:' + qhead + '|' + str(min(len(right_matches), 4)),
           'overlap:' + str(min(row['overlap'], 5)),
           'before:' + before, 'after:' + after,
           'qhead_before:' + qhead + '|' + before,
           'qhead_after:' + qhead + '|' + after,
           'before2:' + before2 + '|' + before,
           'after2:' + after + '|' + after2,
           'left_punct:' + (left_char if left_char and not left_char.isspace() else 'none'),
           'right_punct:' + (right_char if right_char and not right_char.isspace() else 'none')}
    if first in boundary_vocab:
        out.add('first:' + first)
        out.add('qhead_first:' + qhead + '|' + first)
    if last in boundary_vocab:
        out.add('last:' + last)
        out.add('qhead_last:' + qhead + '|' + last)
    return tuple(sorted(out))


def gold_and_options(row):
    options = candidates(row['context'], row['question'])
    gold = {canonical(answer) for answer in row['answers']}
    positive = next((candidate for candidate in options
                     if canonical(candidate['text']) in gold), None)
    return positive, options, gold


class LocalRoleRanker:
    def __init__(self, boundary_vocab=()):
        self.boundary_vocab = set(boundary_vocab)
        self.delta = Counter()
        self.support = Counter()
        self.episodes = {}

    def observe(self, identifier, positive, negatives):
        if identifier in self.episodes:
            self.remove(identifier)
        positive_features = set(features(positive, self.boundary_vocab))
        change = Counter(); support = Counter()
        for negative in negatives:
            negative_features = set(features(negative, self.boundary_vocab))
            for feature in positive_features - negative_features:
                change[feature] += 1
                support[feature] += 1
            for feature in negative_features - positive_features:
                change[feature] -= 1
                support[feature] += 1
        self.delta.update(change)
        self.support.update(support)
        self.episodes[identifier] = {'delta': dict(change), 'support': dict(support)}

    def remove(self, identifier):
        episode = self.episodes.pop(identifier)
        for feature, value in episode['delta'].items():
            self.delta[feature] -= value
            if not self.delta[feature]:
                del self.delta[feature]
        for feature, value in episode['support'].items():
            self.support[feature] -= value
            if not self.support[feature]:
                del self.support[feature]

    def score(self, row):
        return sum(self.delta[feature] / self.support[feature]
                   for feature in features(row, self.boundary_vocab)
                   if self.support[feature] >= 5)

    def predict(self, context, question):
        options = candidates(context, question)
        best_by_text = {}
        for row in options:
            if row['overlap'] < 2:
                continue
            key = canonical(row['text'])
            score = self.score(row)
            prior = best_by_text.get(key)
            if prior is None or score > prior[0]:
                best_by_text[key] = (score, row)
        ordered = sorted(best_by_text.values(), key=lambda pair: (-pair[0],
                                                                  len(pair[1]['text']),
                                                                  pair[1]['text']))
        if not ordered:
            return {'answer': None, 'status': 'abstain', 'candidates': len(options),
                    'high_confidence': False}
        top, row = ordered[0]
        margin = top-ordered[1][0] if len(ordered)>1 else top
        accepted = top > 0 and margin >= 2
        return {'answer': row['text'] if accepted else None,
                'status': 'span_candidate' if accepted else 'abstain',
                'score': round(top, 6), 'margin': round(margin, 6),
                'high_confidence': bool(accepted and margin >= 6),
                'candidates': len(options)}

    def as_dict(self):
        return {'boundary_vocab': sorted(self.boundary_vocab),
                'episodes': {key: value for key, value in sorted(self.episodes.items())}}

    @classmethod
    def from_dict(cls, data):
        model = cls(data['boundary_vocab'])
        for key, episode in sorted(data['episodes'].items()):
            model.episodes[key] = episode
            model.delta.update(episode['delta'])
            model.support.update(episode['support'])
        return model


def negatives_for(positive, options, gold):
    other = [row for row in options if canonical(row['text']) not in gold]
    same = [row for row in other if row['sentence_index'] == positive['sentence_index']]
    start, end = positive['start'], positive['end']
    same.sort(key=lambda row: (-max(0, min(end,row['end'])-max(start,row['start'])),
                               abs((row['end']-row['start'])-(end-start)),
                               abs(row['start']-start), row['start'], row['end']))
    elsewhere = [row for row in other if row['sentence_index'] != positive['sentence_index']]
    elsewhere.sort(key=lambda row: (abs((row['end']-row['start'])-(end-start)),
                                    -row['overlap'], row['sentence_index'], row['start'], row['end']))
    return same[:8] + elsewhere[:4]


def train(rows):
    start = time.process_time(); prepared = []; boundary_counts = Counter()
    enumeration = 0
    for row in rows:
        positive, options, gold = gold_and_options(row)
        enumeration += len(options)
        if positive is None:
            continue
        prepared.append((row['id'], positive, options, gold))
        boundary_counts.update((positive['tokens'][positive['start']][1],
                                positive['tokens'][positive['end']-1][1]))
    model = LocalRoleRanker(word for word, count in boundary_counts.items() if count >= 5)
    for identifier, positive, options, gold in prepared:
        model.observe(identifier, positive, negatives_for(positive, options, gold))
    return model, {'examples_offered': len(rows), 'examples_used': len(prepared),
                   'candidates_enumerated': enumeration,
                   'episodes': len(model.episodes),
                   'boundary_vocabulary': len(model.boundary_vocab),
                   'cpu_s': round(time.process_time()-start, 6)}


def evaluate(model, rows, wrong_passages=False):
    attempts = correct = high = enumerated = 0; times = []; cpu_start = time.process_time()
    for index, row in enumerate(rows):
        context = rows[(index+1)%len(rows)]['context'] if wrong_passages else row['context']
        tick = time.perf_counter()
        prediction = model.predict(context, row['question'])
        times.append(1000*(time.perf_counter()-tick))
        attempts += prediction['answer'] is not None
        correct += prediction['answer'] is not None and canonical(prediction['answer']) in {
            canonical(answer) for answer in row['answers']}
        high += prediction['high_confidence']
        enumerated += prediction['candidates']
    times.sort()
    return {'total': len(rows), 'attempts': attempts, 'correct': correct,
            'precision': round(correct/attempts, 6) if attempts else None,
            'high_confidence_attempts': high, 'candidates_examined': enumerated,
            'cpu_s': round(time.process_time()-cpu_start, 6),
            'p50_ms': round(statistics.median(times), 5),
            'p95_ms': round(times[(95*len(times)+99)//100-1], 5)}


def run(dev=False):
    started_wall = time.monotonic(); started_cpu = time.process_time()
    tree = git('rev-parse', 'estable-E-1:leobot') if dev else git('rev-parse', f'{TAG}:leobot')
    if not dev:
        frozen(tree)
    train_doc, train_bytes = download('sqac_train')
    train_rows = flatten(train_doc)
    taught = random.Random(1642).sample(sorted(train_rows, key=lambda row: row['id']), 2000)
    used = {row['id'] for row in taught}
    if dev:
        prior = select_distinct([row for row in train_rows if row['id'] not in used],64,2117)
        excluded = {row['context_key'] for row in taught+prior}
        held = select_distinct([row for row in train_rows
                                if row['id'] not in used and row['context_key'] not in excluded],
                               64,4039)
        sources = {'sqac_train_new_development': held}
        source_bytes = train_bytes
    else:
        dev_doc, dev_bytes = download('sqac_dev')
        xquad_doc, xquad_bytes = download('xquad')
        sources = {}
        for name, rows in (('sqac_dev', flatten(dev_doc)), ('xquad', flatten(xquad_doc))):
            seed = int(sha256((tree+':F-5:'+name).encode()).hexdigest()[:8],16)
            sources[name] = select_distinct(rows,100,seed)
        source_bytes = train_bytes+dev_bytes+xquad_bytes
    model, learning = train(taught)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'model.json'; tick = time.process_time()
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        loaded = LocalRoleRanker.from_dict(json.loads(path.read_text(encoding='utf8')))
        consolidation_cpu = time.process_time()-tick
        restart_same = loaded.as_dict()==model.as_dict()
    treatment = {name:evaluate(loaded,rows) for name,rows in sources.items()}
    fresh = {name:evaluate(LocalRoleRanker(model.boundary_vocab),rows) for name,rows in sources.items()}
    wrong = {name:evaluate(loaded,rows,wrong_passages=True) for name,rows in sources.items()}
    retrieval = {name:sentence_retrieval(rows) for name,rows in sources.items()}
    baseline, baseline_learning = __import__('experiments.f4_feedback_span_pilot',fromlist=['train_model']).train_model(taught)
    old = {name:{key:value for key,value in f4_evaluate(baseline,rows).items() if key!='rows'}
           for name,rows in sources.items()}
    permuted = [{**row,'question':taught[(i+1)%len(taught)]['question']}
                for i,row in enumerate(taught)]
    shuffled_model, shuffled_learning = train(permuted)
    shuffled = {name:evaluate(shuffled_model,rows) for name,rows in sources.items()}
    correction_id = next(iter(sorted(model.episodes)))
    original_support = model.support.copy()
    model.remove(correction_id)
    removed = correction_id not in model.episodes and model.support != original_support
    corrected = LocalRoleRanker.from_dict(model.as_dict())
    correction_same = removed and corrected.support==model.support and corrected.delta==model.delta
    if not dev:
        frozen(tree)
    gate_dev = (dev and all(treatment[name]['correct']>=8
                            and treatment[name]['precision'] is not None
                            and treatment[name]['precision']>=0.5
                            and treatment[name]['correct']-old[name]['correct']>=5
                            and treatment[name]['p95_ms']<=10
                            and wrong[name]['high_confidence_attempts']<=5
                            for name in sources) and restart_same and correction_same)
    gate_external = (not dev and treatment['sqac_dev']['correct']>=15
                     and treatment['xquad']['correct']>=10
                     and all(treatment[name]['correct']-shuffled[name]['correct']>=5
                             and treatment[name]['precision'] is not None
                             and treatment[name]['precision']>=0.5
                             and treatment[name]['p95_ms']<=10
                             and wrong[name]['high_confidence_attempts']<=5
                             for name in sources) and restart_same and correction_same
                     and learning['cpu_s']<=40)
    output = {'tag':'development' if dev else TAG,'engine_tree':tree,
              'engine_unchanged':git('rev-parse','HEAD:leobot')==tree,
              'preregistration':'prereg/F-5-alineacion-relacional-local.md',
              'source_bytes':source_bytes,'learning':learning,
              'baseline_learning':baseline_learning,'shuffled_learning':shuffled_learning,
              'treatment':treatment,'fresh':fresh,'wrong_passage':wrong,
              'retrieval':retrieval,'f4_baseline':old,'shuffled_questions':shuffled,
              'restart_same':restart_same,'correction_same':correction_same,
              'consolidation_cpu_s':round(consolidation_cpu,6),
              'gate_passed':bool(gate_dev or gate_external),
              'cpu_total_s':round(time.process_time()-started_cpu,6),
              'wall_total_s':round(time.monotonic()-started_wall,6),
              'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT/'results_v3'/('f5_local_dev.json' if dev else 'f5_local_freeze.json')
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--dev',action='store_true')
    run(parser.parse_args().dev)

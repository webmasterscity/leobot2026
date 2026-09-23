"""G-3 preregistered text-to-operator source gate, with causal controls."""
from __future__ import annotations

import ast
import builtins
import json
import math
import os
import random
import re
import resource
import time
import warnings
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g3_mbpp_inventory import URL


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'ccf64ceae9c5403bf50a044cb6d505bfd2a2963ee58338ba268fd65beab92a9f'
SEEDS = (17, 53, 97)
TOP = 5
BUILTIN_NAMES = frozenset(vars(builtins))


def tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r'[^\W_]+', text.casefold()))


def operators(root: ast.Module) -> frozenset[str]:
    defs = [item for item in root.body if isinstance(item, ast.FunctionDef)]
    if len(defs) != 1:
        return frozenset()
    fn = defs[0]
    found = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and
                node.func.id in BUILTIN_NAMES and node.func.id != fn.name):
                found.add(node.func.id.casefold())
            elif isinstance(node.func, ast.Attribute):
                found.add('.' + node.func.attr.casefold())
        elif isinstance(node, ast.BinOp):
            found.add(type(node.op).__name__.casefold())
        elif isinstance(node, ast.UnaryOp):
            found.add(type(node.op).__name__.casefold())
        elif isinstance(node, ast.Compare):
            found.update(type(op).__name__.casefold() for op in node.ops)
        elif isinstance(node, (ast.Subscript, ast.ListComp, ast.GeneratorExp, ast.IfExp)):
            found.add(type(node).__name__.casefold())
    return frozenset(found)


def source() -> list[tuple[int, frozenset[str], frozenset[str]]]:
    with urlopen(URL, timeout=15) as response:
        raw = response.read(2_000_000)
    if sha256(raw).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('La fuente cambió desde el preregistro')
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        for line in raw.splitlines():
            item = json.loads(line)
            if not 601 <= item['task_id'] <= 974:
                continue
            try:
                parsed = ast.parse(item['code'], mode='exec')
            except SyntaxError:
                continue
            rows.append((item['task_id'], tokens(item['text']), operators(parsed)))
    return sorted(rows)


def frequency(train, vocab) -> Counter:
    return Counter(op for _, _, labels in train for op in labels if op in vocab)


def associations(train, vocab) -> tuple[Counter, dict[str, Counter], Counter]:
    positives = frequency(train, vocab)
    word_counts = Counter()
    joined: dict[str, Counter] = defaultdict(Counter)
    for _, words, labels in train:
        for word in words:
            word_counts[word] += 1
            for op in labels & vocab:
                joined[op][word] += 1
    return positives, joined, word_counts


def rank(words, vocab, prior, table=None) -> list[str]:
    labels = []
    total = sum(prior.values())
    for op in vocab:
        score = math.log((prior[op] + 1) / (total + len(vocab)))
        if table is not None:
            counts, word_counts, examples = table
            npos = prior[op]
            for word in words:
                seen = word_counts[word]
                if seen:
                    both = counts[op][word]
                    p_yes = (both + 1) / (npos + 2)
                    p_no = (seen - both + 1) / (examples - npos + 2)
                    score += math.log(p_yes / p_no)
        labels.append((score, op))
    labels.sort(key=lambda item: (-item[0], item[1]))
    return [op for _, op in labels]


def evaluate(dev, predictions, vocab) -> dict:
    n = len(dev)
    hits = 0
    recall = 0.0
    first_ranks = []
    coverage = 0
    for row, ordering in zip(dev, predictions):
        actual = row[2]
        coverage += bool(actual & vocab)
        offered = ordering[:TOP]
        hits += bool(actual.intersection(offered))
        recall += len(actual.intersection(offered)) / max(1, len(actual))
        first_ranks.append(next((i + 1 for i, op in enumerate(ordering)
                                 if op in actual), len(vocab) + 1))
    return {'tasks': n, 'coverage': round(coverage / n, 6),
            'hit_top5': round(hits / n, 6),
            'mean_recall_top5': round(recall / n, 6),
            'mean_first_true_rank': round(sum(first_ranks) / n, 3),
            'candidates_offered': sum(min(TOP, len(ordering)) for ordering in predictions)}


def main() -> None:
    cpu_start, wall_start = time.process_time(), time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    data = source()
    reports = []
    for seed in SEEDS:
        order = list(data)
        random.Random(int(tree[:8], 16) ^ seed).shuffle(order)
        cut = int(len(order) * 0.7)
        train, dev = order[:cut], order[cut:]
        all_frequency = frequency(train, set().union(*(row[2] for row in train)))
        vocab = frozenset(op for op, count in all_frequency.items() if count >= 5)
        prior, joined, word_counts = associations(train, vocab)
        trained = (joined, word_counts, len(train))
        shuffled_text = [row[1] for row in train]
        random.Random(int(tree[:8], 16) ^ seed ^ 0x9E3779B9).shuffle(shuffled_text)
        shuffled_rows = [(row[0], words, row[2]) for row, words in zip(train, shuffled_text)]
        _, shuffled_joined, shuffled_counts = associations(shuffled_rows, vocab)
        shuffled = (shuffled_joined, shuffled_counts, len(train))
        memorized = defaultdict(set)
        for _, words, labels in train:
            memorized[words].update(labels)
        predictions = {'treatment': [], 'frequency': [], 'lexical': [],
                       'shuffled_text': [], 'exact_memory': []}
        for _, words, _ in dev:
            base = rank(words, vocab, prior)
            predictions['frequency'].append(base)
            predictions['treatment'].append(rank(words, vocab, prior, trained))
            predictions['shuffled_text'].append(rank(words, vocab, prior, shuffled))
            predictions['lexical'].append(sorted(vocab, key=lambda op:
                                                 (op.lstrip('.') not in words,
                                                  base.index(op))))
            remembered = memorized.get(words, frozenset())
            predictions['exact_memory'].append(sorted(vocab, key=lambda op:
                                                      (op not in remembered,
                                                       base.index(op))))
        metrics = {name: evaluate(dev, ranked, vocab)
                   for name, ranked in predictions.items()}
        controls = ('frequency', 'lexical', 'shuffled_text', 'exact_memory')
        t = metrics['treatment']
        best_hit = max(metrics[key]['hit_top5'] for key in controls)
        best_recall = max(metrics[key]['mean_recall_top5'] for key in controls)
        reports.append({'seed': seed, 'train': len(train), 'dev': len(dev),
                        'vocabulary_size': len(vocab), 'metrics': metrics,
                        'gate': bool(t['coverage'] >= 0.5 and
                                     t['hit_top5'] - best_hit >= 0.1 and
                                     t['mean_recall_top5'] - best_recall >= 0.1)})
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {'preregistration': 'prereg/G-3-texto-componentes-programa.md',
              'kind': 'development_source_gate_not_behavioral',
              'source_sha256': SOURCE_SHA256, 'engine_tree': tree,
              'hashseed': os.environ.get('PYTHONHASHSEED'),
              'source_rows': len(data), 'top_k': TOP, 'min_train_support': 5,
              'reports': reports, 'all_gates_pass': all(row['gate'] for row in reports),
              'cpu_total_s': round(time.process_time() - cpu_start, 6),
              'wall_total_s': round(time.monotonic() - wall_start, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    suffix = os.environ.get('PYTHONHASHSEED', 'unknown')
    (ROOT / 'results_v3' / f'g3_text_operator_dev_hashseed{suffix}.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

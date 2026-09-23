"""G-1 pilot: can past documentation reduce the cost of tool experiments?

All method names below belong to this evaluator. Query selection sees only
anonymous handles and raw paragraphs; the environment executes the targets.
"""
from __future__ import annotations

import itertools
import json
import math
import random
import re
import resource
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g1_tool_docs_inventory import MethodParser, URL
from experiments.g1_tool_trace_inventory import observe


ROOT = Path(__file__).resolve().parents[1]
DOC_SHA = 'd0fa4f1cdcd45a9b797cd0f3c340d12f9afc9aeaedf0b634d0468fe72a94a4d8'
TRAIN_GROUPS = (('find', 'rfind'), ('partition', 'rpartition'),
                ('lstrip', 'removeprefix'))
DEVELOPMENT_GROUPS = (('startswith', 'endswith'), ('removesuffix', 'rstrip'),
                      ('split', 'rsplit'), ('index', 'rindex'))
INCOMPATIBLE = ('format', 'format_map', 'translate')
MAX_PROBE_CANDIDATES = 64
MAX_ORACLE_CALLS = 3


def source() -> dict[str, str]:
    with urlopen(URL, timeout=20) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if sha256(raw).hexdigest() != DOC_SHA:
        raise RuntimeError('Documento oficial cambió')
    parser = MethodParser()
    parser.feed(raw.decode('utf8'))
    return {name.split('.', 1)[1]: paragraph for name, paragraph
            in parser.methods.items()}


def queries(tree: str, seed: int) -> list[tuple[str, tuple]]:
    texts = [''.join(chars) for size in range(6)
             for chars in itertools.product('ab', repeat=size)]
    texts.extend(('a b a', 'a,a,a', ' a a '))
    arguments = (('a',), ('b',), ('',), ('a', 1), ('b', 1), (',', 1), ('', 1))
    result = [(text, args) for text in texts for args in arguments]
    random.Random(int(sha256((tree + ':G1:queries:' + str(seed)).encode())
                      .hexdigest()[:16], 16)).shuffle(result)
    return result


def words(paragraph: str, frequent: set[str]) -> set[str]:
    return {word for word in re.findall(r'[^\W_]+', paragraph.casefold())
            if len(word) > 2 and word not in frequent}


def frequent_words(paragraphs: dict[str, str]) -> set[str]:
    counts = Counter()
    for paragraph in paragraphs.values():
        counts.update(set(re.findall(r'[^\W_]+', paragraph.casefold())))
    return {word for word, count in counts.items() if count > 15}


def query_shape(query: tuple[str, tuple]) -> str:
    text, args = query
    if len(args) == 2:
        return 'two_arguments'
    fragment = args[0]
    if not fragment:
        return 'empty_fragment'
    if text.startswith(fragment * 2) and len(fragment) <= 2:
        return 'repeated_prefix'
    if text.endswith(fragment * 2) and len(fragment) <= 2:
        return 'repeated_suffix'
    if text.startswith(fragment) != text.endswith(fragment):
        return 'asymmetric_boundary'
    if text.count(fragment) > 1:
        return 'repeated_occurrence'
    return 'other'


def entropy_gain(outcomes: list[tuple]) -> float:
    counts = Counter(outcomes)
    total = len(outcomes)
    return math.log2(total) - sum(count / total * math.log2(count)
                                   for count in counts.values())


def select_probe(methods: tuple[str, ...], candidates: list[tuple[str, tuple]],
                 prior: dict[str, Counter] | None, text_words: set[str]) -> tuple | None:
    scored = []
    for position, query in enumerate(candidates):
        shape = query_shape(query)
        score = sum(prior.get(word, Counter())[shape] for word in text_words) if prior else 0
        scored.append((-score, position, query))
    scored.sort()
    explored = 0
    simulations = 0
    best = None
    target_gain = math.log2(len(methods))
    for _, _, query in scored[:MAX_PROBE_CANDIDATES]:
        observations = [observe(method, *query) for method in methods]
        simulations += len(methods)
        explored += 1
        gain = entropy_gain(observations)
        if best is None or gain > best[0]:
            best = (gain, query, observations)
        if gain >= target_gain - 1e-9:
            break
    if best is None or best[0] <= 0:
        return None, explored, simulations
    return best[1], explored, simulations


def train_prior(paragraphs: dict[str, str], tree: str) -> tuple[dict[str, Counter], dict]:
    common = frequent_words(paragraphs)
    prior: dict[str, Counter] = defaultdict(Counter)
    costs = {'groups': 0, 'simulations': 0, 'queries_explored': 0,
             'paired_document_tool_examples': 0,
             'learned_word_shape_pairs': 0}
    for index, group in enumerate(TRAIN_GROUPS):
        text_words = set().union(*(words(paragraphs[name], common) for name in group))
        query, explored, simulations = select_probe(group, queries(tree, index),
                                                     None, text_words)
        costs['groups'] += 1
        costs['paired_document_tool_examples'] += len(group)
        costs['simulations'] += simulations
        costs['queries_explored'] += explored
        if query is not None:
            shape = query_shape(query)
            for word in text_words:
                prior[word][shape] += 1
    costs['learned_word_shape_pairs'] = sum(len(values) for values in prior.values())
    return prior, costs


def identify(methods: tuple[str, ...], paragraphs: dict[str, str],
             pool: list[tuple[str, tuple]], prior: dict[str, Counter] | None,
             mode: str, common: set[str], seed: int) -> dict:
    # The true mapping is kept only by this evaluator. The decision loop sees
    # anonymous handles through `observe` and asks for a target observation.
    started = time.process_time()
    rng = random.Random(int(sha256((str(seed) + ':' + ':'.join(methods)).encode())
                            .hexdigest()[:16], 16))
    ordered_methods = list(methods)
    rng.shuffle(ordered_methods)
    target = rng.choice(methods)
    doc_words = set().union(*(words(paragraphs[name], common) for name in methods))
    remaining = list(ordered_methods)
    calls = simulations = explored_total = 0
    while len(remaining) > 1 and calls < MAX_ORACLE_CALLS:
        if mode == 'random':
            query = pool[calls]
            explored = 0
            search_calls = 0
        else:
            query, explored, search_calls = select_probe(
                tuple(remaining), pool, prior if mode == 'treatment' else None,
                doc_words)
            if query is None:
                break
        explored_total += explored
        simulations += search_calls
        observed = observe(target, *query)  # The environment, not the learner.
        calls += 1
        predicted = [observe(method, *query) for method in remaining]
        simulations += len(remaining)
        remaining = [method for method, value in zip(remaining, predicted)
                     if value == observed]
    return {'status': 'identified' if len(remaining) == 1 else 'ambiguous',
            'correct': remaining == [target], 'remaining': len(remaining),
            'oracle_calls': calls, 'candidate_simulations': simulations,
            'queries_explored': explored_total,
            'cpu_s': round(time.process_time() - started, 6)}


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    paragraphs = source()
    common = frequent_words(paragraphs)
    prior, education = train_prior(paragraphs, tree)
    results = {}
    for seed in (0, 17, 53):
        pool = queries(tree, seed)
        groups = {}
        for group in DEVELOPMENT_GROUPS:
            key = '/'.join(group)
            groups[key] = {mode: identify(group, paragraphs, pool, prior, mode,
                                          common, seed)
                           for mode in ('treatment', 'active_without_text', 'random')}
        results[str(seed)] = groups
    incompatible = identify(INCOMPATIBLE, paragraphs, queries(tree, 97),
                            prior, 'treatment', common, 97)
    names = tuple('/'.join(group) for group in DEVELOPMENT_GROUPS)
    all_correct = all(results[str(seed)][name]['treatment']['correct']
                      for seed in (0, 17, 53) for name in names)
    savings = []
    for seed in (0, 17, 53):
        for name in names:
            treatment = results[str(seed)][name]['treatment']
            control = results[str(seed)][name]['active_without_text']
            savings.append((seed, name,
                            treatment['oracle_calls'] < control['oracle_calls'] or
                            treatment['candidate_simulations'] <=
                            0.8 * control['candidate_simulations']))
    gate = (all_correct and all(sum(ok for s, _, ok in savings if s == seed) >= 3
                            for seed in (0, 17, 53)) and
            sum(results[str(seed)][name]['treatment']['cpu_s']
                for seed in (0, 17, 53) for name in names) <=
            sum(results[str(seed)][name]['active_without_text']['cpu_s']
                for seed in (0, 17, 53) for name in names))
    unchanged = (git('rev-parse', 'HEAD:leobot') == tree and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {
        'preregistration': 'prereg/G-1-documentos-herramientas-experimentos.md',
        'kind': 'development_only', 'engine_tree': tree,
        'engine_unchanged': unchanged, 'education': education,
        'method_groups_train': [list(group) for group in TRAIN_GROUPS],
        'method_groups_development': [list(group) for group in DEVELOPMENT_GROUPS],
        'results': results, 'incompatible': incompatible,
        'prior_words': len(prior), 'doc_savings_by_seed_group': savings,
        'preliminary_gate_passed': bool(gate and unchanged and
                                        (incompatible['status'] == 'ambiguous' or
                                         incompatible['correct'])),
        'reserved_64_queries': 'ungenerated',
        'second_family_pathlib': 'unopened',
        'counterevidence_restart': 'pending_only_if_gate_passes',
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'g1_active_tool_docs_dev.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('results', 'doc_savings_by_seed_group')}
                     | {'seed0': results['0'], 'doc_savings_count': sum(x[2] for x in savings)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

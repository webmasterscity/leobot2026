"""G-2 preregistered substrate check: shared phrase/effect evidence across types."""
from __future__ import annotations

import json
import re
import resource
import time
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g1_active_tool_docs_dev import (
    DEVELOPMENT_GROUPS, frequent_words, queries, select_probe, source,
)


ROOT = Path(__file__).resolve().parents[1]
TRAINING_PAIRS = (('find', 'rfind'), ('partition', 'rpartition'))


def positions(text: str, fragment: str) -> list[int]:
    if fragment == '':
        return list(range(len(text) + 1))
    return [i for i in range(len(text) - len(fragment) + 1)
            if text[i:i + len(fragment)] == fragment]


def effect(text: str, fragment: str, result: object) -> str | None:
    """Normalize a position chosen by integer or decomposed sequence output."""
    occurrences = positions(text, fragment)
    if len(occurrences) < 2 or occurrences[0] == occurrences[-1]:
        return None
    chosen = None
    if type(result) is int:
        chosen = result
    elif (type(result) is tuple and len(result) == 3 and
          all(type(part) is str for part in result) and
          result[1] == fragment and ''.join(result) == text):
        chosen = len(result[0])
    if chosen == occurrences[0]:
        return 'first'
    if chosen == occurrences[-1]:
        return 'last'
    return None


def contrast_parts(left: str, right: str, frequent: set[str]) -> tuple[set[str], set[str]]:
    a = re.findall(r'[^\W_]+', left.casefold())
    b = re.findall(r'[^\W_]+', right.casefold())
    first, second = set(), set()
    for kind, ai, aj, bi, bj in SequenceMatcher(None, a, b,
                                                autojunk=False).get_opcodes():
        if kind == 'equal':
            continue
        for segment, target in ((a[ai:aj], first), (b[bi:bj], second)):
            clean = [word for word in segment if word not in frequent and len(word) > 2]
            if clean:
                target.update(clean)
                target.add(' '.join(clean))
    return first, second


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    paragraphs = source()
    frequent = frequent_words(paragraphs)
    evidence: dict[tuple[str, str], set[str]] = defaultdict(set)
    reports = []
    for index, pair in enumerate(TRAINING_PAIRS):
        candidates = [(text, args) for text, args in queries(tree, index)
                      if len(args) == 1 and type(args[0]) is str]
        query, explored, simulations = select_probe(pair, candidates,
                                                     None, set())
        if query is None:
            raise RuntimeError('Par de entrenamiento sin prueba discriminante')
        text, args = query
        roles = {}
        for name in pair:
            result = getattr(text, name)(*args)
            roles[name] = effect(text, args[0], result)
        if set(roles.values()) != {'first', 'last'}:
            raise RuntimeError('La consulta no separó las semánticas de posición')
        left, right = contrast_parts(paragraphs[pair[0]], paragraphs[pair[1]], frequent)
        for name, phrases in ((pair[0], left), (pair[1], right)):
            for phrase in phrases:
                evidence[(phrase, roles[name])].add('/'.join(pair))
        reports.append({'methods': list(pair), 'query': [text, list(args)],
                        'effect_roles': roles, 'queries_explored': explored,
                        'simulations': simulations,
                        'distinctive_phrases': {pair[0]: len(left), pair[1]: len(right)}})
    reusable = sorted(phrase for (phrase, role), groups in evidence.items()
                      if len(groups) >= 2 and not evidence.get(
                          (phrase, 'last' if role == 'first' else 'first')))
    raw_evidence: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in reports:
        left, right = row['methods']
        a, b = contrast_parts(paragraphs[left], paragraphs[right], set())
        for name, phrases in ((left, a), (right, b)):
            for phrase in phrases:
                raw_evidence[(phrase, row['effect_roles'][name])].add(left + '/' + right)
    raw_reusable = sorted(phrase for (phrase, role), groups in raw_evidence.items()
                          if len(groups) >= 2 and not raw_evidence.get(
                              (phrase, 'last' if role == 'first' else 'first')))
    outgoing = json.loads((ROOT / 'results_v3' / 'g2_doc_relation_inventory.json')
                          .read_text())['outgoing_references']
    trained = {name for pair in TRAINING_PAIRS for name in pair}
    linked_development = [list(pair) for pair in DEVELOPMENT_GROUPS
                          if any(target.split('.', 1)[1] in trained
                                 for name in pair
                                 for target in outgoing.get('str.' + name, ()))]
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'preregistration': 'prereg/G-2-frases-efectos-tipados.md',
        'kind': 'source_feasibility_only', 'engine_tree': tree,
        'training_pairs': reports, 'phrase_role_hypotheses': len(evidence),
        'reusable_phrases_with_two_independent_types': reusable,
        'reusable_count': len(reusable),
        'postgate_unfiltered_reusable_phrases': raw_reusable,
        'directly_linked_development_pairs': linked_development,
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'g2_phrase_effect_feasibility.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Read-only inventory: do surface-equivalent human edits imply different labels?"""
from __future__ import annotations

import json
import resource
import time
from collections import Counter, defaultdict
from pathlib import Path

from experiments.f14_revision_baselines import groups, pairs
from experiments.f14_typed_edit_learner import _tokens
from experiments.f17_typed_sequence_pilot import edit_record, language_programs, scan
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]


def conflicted(index: dict) -> dict:
    independent = mixed = affected = affected_rows = 0
    for labels in index.values():
        sources = set().union(*labels.values())
        if len(sources) < 2:
            continue
        independent += 1
        if len([label for label, ids in labels.items() if ids]) > 1:
            mixed += 1
            affected += len(sources)
            affected_rows += sum(len(ids) for ids in labels.values())
    return {'independently_repeated_keys': independent,
            'mixed_label_keys': mixed,
            'groups_in_mixed_keys': affected,
            'group_label_support_in_mixed_keys': affected_rows}


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    train, _, _, _ = groups(tree)
    expressions = language_programs()
    relation_index = defaultdict(lambda: defaultdict(set))
    edit_index = defaultdict(lambda: defaultdict(set))
    order_only = Counter()
    directions = Counter()
    rows = 0
    for group, _, _, before, after, side in pairs(train):
        rows += 1
        old, new = before['gold_label'], after['gold_label']
        record = edit_record(before, after)
        relation = (old, side, tuple(min(2, scan(expr, record))
                                     for expr in expressions))
        exact_edit = (old, side, record['removed'], record['added'])
        relation_index[relation][new].add(group)
        edit_index[exact_edit][new].add(group)
        directions[(old, new)] += 1
        for field in ('sentence1', 'sentence2'):
            old_tokens, new_tokens = _tokens(before[field]), _tokens(after[field])
            if old_tokens != new_tokens and Counter(old_tokens) == Counter(new_tokens):
                order_only['edges'] += 1
                order_only['changed_label' if old != new else 'same_label'] += 1
                order_only['groups:' + str(group)] += 1
    order_groups = sum(key.startswith('groups:') for key in order_only)
    for key in list(order_only):
        if key.startswith('groups:'):
            del order_only[key]
    output = {
        'kind': 'source_feasibility_only', 'engine_tree': tree,
        'train_groups': len(train), 'directed_pairs': rows,
        'relation_expressions': len(expressions),
        'relation_signatures': len(relation_index),
        'relation_conflicts': conflicted(relation_index),
        'exact_edit_signatures': len(edit_index),
        'exact_edit_conflicts': conflicted(edit_index),
        'order_only': dict(order_only) | {'groups': order_groups},
        'transition_counts': {str(old) + '→' + str(new): count
                              for (old, new), count in sorted(directions.items())},
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    path = ROOT / 'results_v3' / 'f18_contrast_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

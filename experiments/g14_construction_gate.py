"""G-14 preregistered upper-bound gate for cross-domain slot anchors."""
from __future__ import annotations

import json
import os
import random
import resource
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g12_massive_source_gate import SEEDS, source
from experiments.g13_span_roles import SOURCE_SHA, load_rows


ROOT = Path(__file__).resolve().parents[1]


def keys(row, start, end):
    seq = row['tokens']
    for width in (1, 2):
        left = tuple(seq[max(0, start-width):start])
        right = tuple(seq[end:min(len(seq), end+width)])
        if start < width:
            left = ('<start>',) + left
        if len(seq)-end < width:
            right = right + ('<end>',)
        yield (width, left, right)


def inventory(rows, eligible):
    by_key = defaultdict(lambda: defaultdict(set))
    for row in rows:
        for start, end, role in row['gold']:
            if end-start > 6:
                continue
            origin = (row['scenario'], row['text'], start, end)
            for key in keys(row, start, end):
                by_key[key][role].add(origin)
    selected = {}
    impure = 0
    for key, roles in sorted(by_key.items()):
        counts = {role: len(origins) for role, origins in roles.items()}
        winner = sorted(counts, key=lambda role: (-counts[role], role))[0]
        support = counts[winner]
        total = sum(counts.values())
        databases = len({scenario for scenario, _, _, _ in roles[winner]})
        if total and support/total < .90:
            impure += 1
        if (winner in eligible and support >= 8 and databases >= 3 and
            support/total >= .90 and
            (len(counts) == 1 or support > sorted(counts.values(), reverse=True)[1])):
            selected[key] = {'role': winner, 'support': support,
                             'total': total, 'databases': databases}
    return selected, len(by_key), impure


def shuffle_labels(rows, rng):
    by_domain = defaultdict(list)
    for row in rows:
        by_domain[row['scenario']].append(row)
    shuffled = []
    for domain, group in sorted(by_domain.items()):
        labels = [role for row in group for _, _, role in row['gold']]
        rng.shuffle(labels)
        cursor = 0
        for row in group:
            n = len(row['gold'])
            shuffled.append({**row, 'gold': [(a,b,role) for (a,b,_),role
                                             in zip(row['gold'], labels[cursor:cursor+n])]})
            cursor += n
    return shuffled


def coverage(test, patterns, eligible, seen_values):
    counts = Counter()
    for row in test:
        for start, end, role in row['gold']:
            if role not in eligible:
                continue
            counts['all'] += 1
            novel = ' '.join(row['tokens'][start:end]) not in seen_values
            counts['novel'] += novel
            supported = any(patterns.get(key, {}).get('role') == role
                            for key in keys(row, start, end))
            counts['all_supported'] += supported
            counts['novel_supported'] += novel and supported
    return dict(counts)


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw, archive_bytes, _ = source()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Fuente cambió')
    rows = load_rows(raw)
    reports = []
    for seed in SEEDS:
        names = sorted({row['scenario'] for row in rows})
        random.Random(int(h0[:8], 16) ^ seed ^ 0x69B).shuffle(names)
        heldout = set(names[:max(3, round(.2*len(names)))])
        train = [row for row in rows if row['scenario'] not in heldout]
        test = [row for row in rows if row['scenario'] in heldout]
        roles = Counter(role for row in train for _, _, role in row['gold'])
        role_domains = defaultdict(set)
        for row in train:
            for _, _, role in row['gold']:
                role_domains[role].add(row['scenario'])
        eligible = {role for role, count in roles.items()
                    if count >= 20 and len(role_domains[role]) >= 3}
        seen_values = {' '.join(row['tokens'][a:b]) for row in train
                       for a,b,role in row['gold'] if role in eligible}
        treatment, observed, impure = inventory(train, eligible)
        control_rows = shuffle_labels(train, random.Random(int(h0[:8], 16) ^ seed ^ 0x39A))
        shuffled, shuffled_observed, shuffled_impure = inventory(control_rows, eligible)
        result = coverage(test, treatment, eligible, seen_values)
        control = coverage(test, shuffled, eligible, seen_values)
        all_rate = result['all_supported']/result['all'] if result['all'] else 0
        novel_rate = result['novel_supported']/result['novel'] if result['novel'] else 0
        ctrl_all = control['all_supported']/control['all'] if control['all'] else 0
        ctrl_novel = control['novel_supported']/control['novel'] if control['novel'] else 0
        gate = (len(treatment) >= 5 and all_rate >= .40 and novel_rate >= .25
                and all_rate-ctrl_all >= .20 and novel_rate-ctrl_novel >= .20)
        reports.append({'seed': seed, 'training_utterances': len(train),
                        'heldout_utterances': len(test), 'eligible_roles': len(eligible),
                        'observed_contexts': observed, 'impure_contexts': impure,
                        'promoted_contexts': len(treatment),
                        'shuffled_observed_contexts': shuffled_observed,
                        'shuffled_impure_contexts': shuffled_impure,
                        'shuffled_promoted_contexts': len(shuffled),
                        'treatment': result, 'shuffled': control,
                        'all_coverage': all_rate, 'novel_coverage': novel_rate,
                        'shuffled_all_coverage': ctrl_all,
                        'shuffled_novel_coverage': ctrl_novel,
                        'gate_partition': gate})
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu <= 15 and wall <= 60 and rss <= 256*1024
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'development_structural_source_gate_only',
              'preregistration': 'prereg/G-14-recurrencia-de-construcciones.md',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'source_sha256': SOURCE_SHA, 'archive_bytes': archive_bytes,
              'reports': reports, 'budget_ok': budget,
              'gate_pass': budget and all(r['gate_partition'] for r in reports),
              'cpu_total_s': round(cpu, 6), 'wall_total_s': round(wall, 6),
              'max_rss_kib': rss}
    path = ROOT / f'results_v3/g14_construction_gate_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante la puerta')


if __name__ == '__main__':
    main()

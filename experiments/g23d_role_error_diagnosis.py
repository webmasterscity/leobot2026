"""Postgate G-23 diagnosis on already used reserve; no new success claim."""
from __future__ import annotations

import json
import os
import random
import resource
import time
from collections import Counter
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g22_ancora_source_gate import H0, UP_URL, download, index_up
from experiments.g23_role_paths import (
    ROLES, UD_SHA, UP_SHA, compile_models, new_tables, source_stream,
    treatment_choice,
)


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-23d-diagnostico-de-rutas.md'
SEED = 1361


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g23d_role_error_diagnosis.py',
                        'experiments/g23_role_paths.py'))


def diagnose(test, tables, models):
    counts = Counter()
    by_role = {role: Counter() for role in ROLES}
    for cases in test:
        for _, keys, gold in cases:
            predicted = treatment_choice(models, keys)
            if predicted in ROLES and predicted != gold:
                counts['false_positive'] += 1
                counts['false_positive_wrong_head' if gold == 'NONE'
                       else 'false_positive_wrong_role'] += 1
            if gold not in ROLES:
                continue
            counts['gold_representable'] += 1
            row = by_role[gold]
            row['gold'] += 1
            full = tables['full'].get(keys['full'])
            path = tables['path'].get(keys['path'])
            row['full_seen'] += bool(full)
            row['path_seen'] += bool(path)
            row['full_gold_support'] += bool(full and full[gold])
            row['path_gold_support'] += bool(path and path[gold])
            if predicted == gold:
                counts['correct_gold'] += 1
                row['correct'] += 1
                continue
            counts['false_negative'] += 1
            row['missed'] += 1
            if predicted in ROLES:
                category = 'promoted_wrong_role'
            elif not full:
                category = 'full_key_unseen'
            elif not full[gold]:
                category = 'full_seen_without_gold_role_support'
            else:
                category = 'full_gold_support_without_promotion'
            counts[category] += 1
            row[category] += 1
            if full and full[gold]:
                counts['missed_full_gold_support'] += 1
            if path and path[gold]:
                counts['missed_path_gold_support'] += 1
    missed = counts['false_negative']
    decisions = {
        'score_hypothesis_priority': (counts['full_gold_support_without_promotion'] / missed >= .50
                                      if missed else False),
        'representation_hypothesis_priority': (counts['full_key_unseen'] / missed >= .50
                                               if missed else False),
        'lexical_valence_priority': (
            counts['false_positive_wrong_role'] / counts['false_positive'] >= .30
            if counts['false_positive'] else False),
    }
    return dict(counts), {role: dict(value) for role, value in by_role.items()}, decisions


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    if not frozen():
        raise RuntimeError('Motor o evaluadores no congelados')
    raw = download(UP_URL, 20*1024*1024)
    if sha256(raw).hexdigest() != UP_SHA:
        raise RuntimeError('UP cambió')
    up_bytes = len(raw)
    download_cpu = time.process_time()-cpu0
    tick = time.process_time()
    up, _ = index_up(raw)
    del raw
    up_index_cpu = time.process_time()-tick

    tables = new_tables()
    rng = random.Random(int(H0[:8], 16) ^ SEED ^ 0x23A)
    test = []
    feature_ms = []
    stats = Counter()
    seen = {name: {'docs': set(), 'lemmas': set()} for name in ('train', 'heldout')}
    tick = time.process_time()
    ud_bytes, ud_hash = source_stream(up, SEED, tables, rng, test,
                                      feature_ms, stats, seen)
    stream_cpu = time.process_time()-tick
    if ud_hash != UD_SHA:
        raise RuntimeError('UD cambió')
    tick = time.process_time()
    models = compile_models(tables)
    counts, by_role, decisions = diagnose(test, tables, models)
    diagnosis_cpu = time.process_time()-tick
    if counts['gold_representable'] != stats['representable_core_heads_heldout']:
        raise RuntimeError('No coinciden cabezas representables y diagnóstico')
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu <= 30 and wall <= 60 and rss <= 256*1024
    unchanged = frozen()
    output = {
        'kind': 'G23d_postgate_diagnosis_not_confirmation',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': {'up': UP_SHA, 'ud': ud_hash},
        'source_bytes': {'up': up_bytes, 'ud': ud_bytes},
        'seed': SEED,
        'source_counts': dict(stats),
        'rule_counts': {name: len(rules) for name, rules in models.items()},
        'counts': counts,
        'by_role': by_role,
        'decision_flags': decisions,
        'up_download_cpu_s': round(download_cpu, 6),
        'up_index_cpu_s': round(up_index_cpu, 6),
        'ud_stream_training_cpu_s': round(stream_cpu, 6),
        'diagnosis_cpu_s': round(diagnosis_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
    }
    path = ROOT / ('results_v3/g23d_role_diagnostic_hashseed'
                   + os.environ.get('PYTHONHASHSEED', 'unset') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('by_role', 'source_counts')},
                     ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluadores cambiaron durante diagnóstico')


if __name__ == '__main__':
    main()

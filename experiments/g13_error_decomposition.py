"""Postgate G-13 diagnosis: separate span boundary and role assignment errors."""
from __future__ import annotations

import json
import random
import resource
import time
from collections import Counter
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g12_massive_source_gate import SEEDS, source
from experiments.g13_span_roles import SOURCE_SHA, load_rows, train_model, predict


ROOT = Path(__file__).resolve().parents[1]


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    raw, _, _ = source()
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
        models = {'treatment': train_model(train, True),
                  'no_context': train_model(train, False)}
        detail = {}
        for name, model in models.items():
            counts = Counter()
            eligible = set(model['roles'])
            seen = {' '.join(row['tokens'][a:b]) for row in train
                    for a,b,role in row['gold'] if role in eligible}
            for row in test:
                proposed, _, _ = predict(model, row)
                gold = {(a,b,role) for a,b,role in row['gold'] if role in eligible}
                guess = {(a,b,role) for a,b,role in proposed if role in eligible}
                gold_bounds = {(a,b) for a,b,_ in gold}
                guess_bounds = {(a,b) for a,b,_ in guess}
                gold_roles = Counter(role for _,_,role in gold)
                guess_roles = Counter(role for _,_,role in guess)
                counts['gold'] += len(gold)
                counts['predicted'] += len(guess)
                counts['joint_tp'] += len(gold & guess)
                counts['boundary_tp'] += len(gold_bounds & guess_bounds)
                counts['role_multiset_tp'] += sum((gold_roles & guess_roles).values())
                novel_gold = {item for item in gold
                              if ' '.join(row['tokens'][item[0]:item[1]]) not in seen}
                novel_guess = {item for item in guess
                               if ' '.join(row['tokens'][item[0]:item[1]]) not in seen}
                counts['novel_gold'] += len(novel_gold)
                counts['novel_predicted'] += len(novel_guess)
                counts['novel_joint_tp'] += len(novel_gold & novel_guess)
                counts['novel_boundary_tp'] += len({(a,b) for a,b,_ in novel_gold}
                                                   & {(a,b) for a,b,_ in novel_guess})
            denom = counts['gold']+counts['predicted']
            novel_denom = counts['novel_gold']+counts['novel_predicted']
            detail[name] = {**dict(counts),
                            'joint_f1': 2*counts['joint_tp']/denom if denom else 0,
                            'boundary_oracle_f1': 2*counts['boundary_tp']/denom if denom else 0,
                            'role_oracle_f1': 2*counts['role_multiset_tp']/denom if denom else 0,
                            'novel_joint_f1': 2*counts['novel_joint_tp']/novel_denom
                                              if novel_denom else 0,
                            'novel_boundary_oracle_f1': 2*counts['novel_boundary_tp']/novel_denom
                                                        if novel_denom else 0}
        reports.append({'seed': seed, 'heldout_utterances': len(test), 'detail': detail})
    unchanged = git('rev-parse', 'HEAD:leobot') == h0 and not git('status', '--porcelain', '--', 'leobot')
    output = {'kind': 'postgate_diagnostic_only', 'source': 'G-13 failed gate',
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'reports': reports, 'cpu_total_s': round(time.process_time()-cpu0, 6),
              'wall_total_s': round(time.monotonic()-wall0, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT/'results_v3/g13_error_decomposition.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'reports': [{'seed': row['seed'],
        'detail': {name:{k:round(value,4) for k,value in detail.items() if k.endswith('_f1')}
                   for name,detail in row['detail'].items()}}
        for row in reports], 'cpu_total_s': output['cpu_total_s'],
        'max_rss_kib': output['max_rss_kib']}, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor alterado durante diagnóstico')


if __name__ == '__main__':
    main()

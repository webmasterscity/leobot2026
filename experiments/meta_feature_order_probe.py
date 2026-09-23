"""Optional V9 diagnostic: does meta-program discovery depend on feature order?

Run from the repository root: python3 -m experiments.meta_feature_order_probe
This is outside run_tests.sh because it measures a separate ordering property
under a fixed CPU budget. It reports a failure as data.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path

from leobot.metacontrol import MetaController


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results_v3' / 'v90_meta_feature_order_probe.json'


def code_hash():
    h = hashlib.sha256()
    for path in sorted((ROOT / 'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(b'\0')
        h.update(path.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def make_rows():
    rng = random.Random(7331)
    rows = []
    for i in range(64):
        bits = [(i >> k) & 1 for k in range(3)]
        centers = [10_000.0 + i * 17.0, 1_000_000.0 + i * 31.0,
                   100_000_000.0 + i * 43.0]
        relevant = []
        for bit, center, delta in zip(bits, centers, (3.0, 5.0, 7.0)):
            relevant.extend((center + delta, center - delta) if bit
                            else (center - delta, center + delta))
        distractors = [rng.uniform(-1e9, 1e9) for _ in range(10)]
        rows.append((relevant, distractors,
                     'A' if bits[0] ^ bits[1] ^ bits[2] else 'B'))
    return rows


def train(rows, relevant_last):
    controller = MetaController()
    family = 'feature_order_probe'
    start = time.perf_counter()
    for relevant, distractors, winner in rows:
        features = distractors + relevant if relevant_last else relevant + distractors
        for strategy in ('A', 'B'):
            controller.observe(family, features, strategy,
                               success=(strategy == winner),
                               cost=1 if strategy == winner else 9,
                               failure_budget=2)
    view = controller.invented_views.get(family)
    report = controller._invent_meta_program_from_tasks(
        family, controller._meta_tasks(family), force=True)
    return {'program_size': view.get('program_size') if view else None,
            'report_status': report.get('status'),
            'report_reason': report.get('reason'),
            'predicate_count': report.get('predicates') if isinstance(report.get('predicates'), int) else None,
            'acquisition_and_recheck_s': time.perf_counter() - start}


if __name__ == '__main__':
    before = code_hash()
    rows = make_rows()
    first = train(rows, False)
    last = train(rows, True)
    result = {'version': 'V9 optional feature-order diagnostic',
              'tasks': len(rows), 'features': 16, 'irrelevant_features': 10,
              'relevant_first': first, 'relevant_last': last,
              'order_invariant': first['program_size'] == last['program_size'],
              'code_hash_before': before, 'code_hash_after': code_hash()}
    result['code_unchanged'] = result['code_hash_before'] == result['code_hash_after']
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

"""Diagnostic baseline on a fixed sample of human tasks; no reference code runs."""
from __future__ import annotations

import ast
import json
import random
import resource
import time
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g3_mbpp_inventory import URL, test_example
from leobot.programs import LIMIT, ProgramLearner


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cpu, wall = time.process_time(), time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    with urlopen(URL, timeout=15) as response:
        raw = response.read(2_000_000)
    source_hash = sha256(raw).hexdigest()
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        if not 601 <= row['task_id'] <= 974:
            continue
        try:
            root = ast.parse(row['code'], mode='exec')
        except SyntaxError:
            continue
        defs = [node for node in root.body if isinstance(node, ast.FunctionDef)]
        if len(defs) != 1:
            continue
        tests = [test_example(text, defs[0].name) for text in row['test_list']]
        if (len(tests) != 3 or any(test is None for test in tests) or
            not all(1 <= len(args) <= 4 and
                    all(type(arg) is int and abs(arg) <= LIMIT for arg in args) and
                    type(expected) is int and abs(expected) <= LIMIT
                    for args, expected in tests) or
            len({len(args) for args, _ in tests}) != 1):
            continue
        rows.append((row['task_id'], tests))
    rng = random.Random(int(tree[:8], 16))
    sample = rng.sample(rows, min(12, len(rows)))
    reports = []
    for task_id, tests in sample:
        learner = ProgramLearner(max_size=5, max_candidates=1000,
                                 max_seconds=0.2, allow_recurrence=False,
                                 auto_abstraction=False)
        skill = 'sample'
        for args, expected in tests[:2]:
            learner.add_example(skill, args, expected)
        tick = time.process_time()
        fit = learner.fit(skill)
        guess = learner.predict(skill, tests[2][0])
        reports.append({'task_id': task_id, 'status': fit['status'],
                        'candidates': fit['candidates'],
                        'prediction_status': guess['status'],
                        'third_case_correct': guess['value'] == tests[2][1]
                        if guess['status'] == 'hypothesis' else False,
                        'third_input_seen': tests[2][0] in {args for args, _ in tests[:2]},
                        'cpu_s': round(time.process_time() - tick, 6)})
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'diagnostic_only_not_heldout', 'source_sha256': source_hash,
        'engine_tree': tree, 'seed': int(tree[:8], 16),
        'available_numeric_tasks': len(rows), 'sampled_tasks': len(sample),
        'two_examples_per_task': True, 'third_original_test_for_diagnostic': True,
        'max_size': 5, 'max_candidates_per_task': 1000,
        'max_search_seconds_per_task': 0.2,
        'supported_predictions': sum(row['prediction_status'] == 'hypothesis'
                                     for row in reports),
        'correct_predictions': sum(row['third_case_correct'] for row in reports),
        'memorized_third_inputs': sum(row['third_input_seen'] for row in reports),
        'candidates_total': sum(row['candidates'] for row in reports),
        'reports': reports,
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (ROOT / 'results_v3' / 'g3_mbpp_numeric_baseline.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

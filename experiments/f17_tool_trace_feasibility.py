"""Read-only inventory of learning from executed stdlib tool traces.

This selects no mechanism and is not a held-out promotion experiment.
"""
from __future__ import annotations

import json
import math
import operator
import random
import resource
import subprocess
import time
from pathlib import Path

from leobot.programs import ProgramLearner


ROOT = Path(__file__).resolve().parents[1]


def tree_hash() -> str:
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD:leobot'], cwd=ROOT, text=True
    ).strip()


def numeric_cases(rng: random.Random, count: int) -> list[tuple[int, int]]:
    cases = set()
    while len(cases) < count:
        cases.add((rng.randrange(-30, 31), rng.randrange(-30, 31)))
    return sorted(cases)


def string_cases(rng: random.Random, count: int) -> list[tuple[str, str]]:
    cases = set()
    while len(cases) < count:
        haystack = ''.join(rng.choices('abcdef', k=rng.randrange(3, 10)))
        needle = ''.join(rng.choices('abcdef', k=rng.randrange(1, 4)))
        cases.add((haystack, needle))
    return sorted(cases)


def main() -> None:
    start_tree = tree_hash()
    if subprocess.check_output(
        ['git', 'status', '--porcelain', '--', 'leobot'], cwd=ROOT, text=True
    ).strip():
        raise RuntimeError('Motor tiene cambios locales')
    rng = random.Random(int(start_tree[:8], 16) ^ 0xF17)
    start_cpu = time.process_time()
    start_wall = time.monotonic()
    reports = {}
    for name, blackbox in (
        ('add', operator.add), ('mul', operator.mul), ('gcd', math.gcd)
    ):
        cases = numeric_cases(rng, 72)
        train, test = cases[:24], cases[24:]
        learner = ProgramLearner(max_size=4, max_candidates=2000,
                                 max_seconds=2.0, auto_abstraction=False,
                                 allow_recurrence=False)
        before = time.process_time()
        for args in train:
            learner.add_example(name, args, blackbox(*args))
        fit = learner.fit(name)
        acquisition_cpu = time.process_time() - before
        before = time.process_time()
        predictions = [learner.predict(name, args) for args in test]
        inference_cpu = time.process_time() - before
        reports[name] = {
            'family': 'executed_integer_tool', 'train': len(train),
            'test': len(test), 'status': fit['status'],
            'candidates': fit['candidates'],
            'answered': sum(p['status'] == 'hypothesis' for p in predictions),
            'correct': sum(p['status'] == 'hypothesis' and p['value'] == blackbox(*args)
                           for p, args in zip(predictions, test)),
            'acquisition_cpu_s': round(acquisition_cpu, 6),
            'inference_cpu_s': round(inference_cpu, 6),
        }
    for name, blackbox in (
        ('find', lambda text, fragment: text.find(fragment)),
        ('count', lambda text, fragment: text.count(fragment)),
    ):
        args = string_cases(rng, 1)[0]
        learner = ProgramLearner(max_size=4, max_candidates=2000,
                                 max_seconds=2.0, auto_abstraction=False,
                                 allow_recurrence=False)
        try:
            learner.add_example(name, args, blackbox(*args))
            outcome = 'accepted'
        except ValueError as exc:
            outcome = f'rejected: {exc}'
        reports[name] = {
            'family': 'executed_string_tool', 'sample_inputs': list(args),
            'sample_output': blackbox(*args), 'input_outcome': outcome,
        }
    end_tree = tree_hash()
    if end_tree != start_tree:
        raise RuntimeError('El motor cambió durante el inventario')
    output = {
        'kind': 'architecture_feasibility_only',
        'engine_tree_before': start_tree, 'engine_tree_after': end_tree,
        'reports': reports,
        'cpu_total_s': round(time.process_time() - start_cpu, 6),
        'wall_total_s': round(time.monotonic() - start_wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'f17_tool_trace_feasibility.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

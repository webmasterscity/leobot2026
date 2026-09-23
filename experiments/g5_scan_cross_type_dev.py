"""G-5 gate 1: test an existing learned scan on a different sequence type."""
from __future__ import annotations

import json
import os
import random
import resource
import statistics
import time
from hashlib import sha256
from pathlib import Path

from experiments.f17_typed_sequence_pilot import scan, tool_programs
from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (17, 53, 97)


def cases(tree: str, seed: int, kind: str, count: int):
    digest = sha256((tree + ':' + str(seed) + ':' + kind).encode()).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    alphabet = ('a', 'b', 'c', 'd', 'e') if kind == 'text' else (0, 1, 2, 127, 255)
    result = []
    seen = set()
    while len(result) < count:
        width = rng.randrange(0, 13)
        items = [rng.choice(alphabet) for _ in range(width)]
        mode = len(result) % 5
        if mode == 0:
            pattern = []
        elif mode == 1 and items:
            start = rng.randrange(len(items))
            pattern = items[start:start + rng.randrange(1, 4)]
        elif mode == 2:
            repeated = rng.choice(alphabet)
            items = [repeated] * rng.randrange(2, 11)
            pattern = [repeated] * rng.randrange(1, 4)
        elif mode == 3:
            pattern = [rng.choice(alphabet) for _ in range(rng.randrange(1, 4))]
        else:
            pattern = [alphabet[-1], alphabet[-1]]
        source = ''.join(items) if kind == 'text' else bytes(items)
        fragment = ''.join(pattern) if kind == 'text' else bytes(pattern)
        if (source, fragment) in seen:
            continue
        seen.add((source, fragment))
        result.append((source, fragment))
    return result


def record(inputs: tuple):
    source, fragment = inputs
    if type(source) is bytes and type(fragment) is bytes:
        return {'arg0': tuple(source), 'arg1': tuple(fragment)}
    if type(source) is str and type(fragment) is str:
        return {'arg0': source, 'arg1': fragment}
    raise ValueError('Secuencias incompatibles')


def fit(rows: list[tuple], spec_list: list[dict]):
    tick = time.process_time()
    surviving = [program for program in spec_list if all(
        scan(program, record(inputs)) == observed
        for inputs, observed in rows)]
    return surviving, time.process_time() - tick


def predict(programs: list[dict], rows: list[tuple]):
    times = []
    correct = supported = false = 0
    for inputs, observed in rows:
        tick = time.perf_counter()
        values = {scan(program, record(inputs)) for program in programs}
        answer = next(iter(values)) if len(values) == 1 else None
        times.append((time.perf_counter() - tick) * 1000)
        supported += answer is not None
        correct += answer == observed if answer is not None else 0
        false += answer != observed if answer is not None else 0
    return {'cases': len(rows), 'supported': supported, 'correct': correct,
            'false': false,
            'p50_ms': round(statistics.median(times), 6),
            'p95_ms': round(sorted(times)[(95 * len(times) + 99) // 100 - 1], 6)}


def main():
    wall, cpu = time.monotonic(), time.process_time()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    programs = tool_programs()
    if len(programs) > 64:
        raise RuntimeError('Espacio de búsqueda fuera del presupuesto F-17')
    reports = []
    for seed in SEEDS:
        source_inputs = cases(h0, seed, 'text', 64)
        target_inputs = cases(h0, seed, 'bytes', 64)
        methods = []
        for operation in ('find', 'count'):
            # The evaluator knows the real method; the learner sees only rows.
            source_rows = [(item, getattr(item[0], operation)(item[1]))
                           for item in source_inputs]
            target_rows = [(item, getattr(item[0], operation)(item[1]))
                           for item in target_inputs]
            acquired, acquisition_cpu = fit(source_rows[:32], programs)
            validated, validation_cpu = fit(source_rows[32:], acquired)
            inference_tick = time.process_time()
            cross = predict(validated, target_rows)
            inference_cpu = time.process_time() - inference_tick
            fresh, target_acquisition_cpu = fit(target_rows[:32], programs)
            fresh_result = predict(fresh, target_rows[32:])
            methods.append({'evaluator_operation': operation,
                            'source_examples': 32, 'source_validation': 32,
                            'candidate_programs': len(programs),
                            'fit_survivors': len(acquired),
                            'validated_survivors': len(validated),
                            'source_fit_cpu_s': round(acquisition_cpu, 6),
                            'source_validation_cpu_s': round(validation_cpu, 6),
                            'target_oracle_calls_treatment': 0,
                            'cross_type': cross,
                            'cross_inference_cpu_s': round(inference_cpu, 6),
                            'fresh_target_examples': 32,
                            'fresh_fit_cpu_s': round(target_acquisition_cpu, 6),
                            'fresh_target_heldout': fresh_result,
                            'memory_only_cross_answers': 0,
                            'learned_descriptions': validated})
        reports.append({'seed': seed, 'methods': methods,
                        'gate1_pass': all(method['cross_type']['correct'] == 64 and
                                          method['cross_type']['false'] == 0 and
                                          method['cross_type']['p95_ms'] <= 10
                                          for method in methods)})
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'preregistration': 'prereg/G-5-composicion-de-operadores-observados.md',
              'kind': 'gate1_feasibility_only', 'engine_tree_before': h0,
              'engine_tree_after': git('rev-parse', 'HEAD:leobot'),
              'engine_unchanged': unchanged,
              'hashseed': os.environ.get('PYTHONHASHSEED'),
              'candidate_programs': len(programs),
              'reports': reports,
              'all_gate1_pass': bool(unchanged and all(report['gate1_pass']
                                                     for report in reports)),
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    suffix = os.environ.get('PYTHONHASHSEED', 'unknown')
    (ROOT / 'results_v3' / f'g5_scan_cross_type_hashseed{suffix}.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

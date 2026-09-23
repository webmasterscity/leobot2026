"""G-5b: bounded typed synthesis with balanced, goal-directed slice search."""
from __future__ import annotations

import json
import os
import random
import resource
import statistics
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f17_typed_sequence_pilot import tool_programs
from experiments.f7_typed_sequences_dev import git
from experiments.g5_composition_dev import (
    CAP, BAD, eval_program, exact, observed, signature,
    spec_key, varied_inputs,
)
from experiments.g5_scan_cross_type_dev import cases, fit


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (101, 211, 307)


def cost(expr):
    if expr[0] in ('arg', 'int', 'none', 'scan'):
        return 1
    return 1 + sum(cost(child) for child in expr[1:]
                   if isinstance(child, tuple) and child and isinstance(child[0], str))


def kind(sig):
    if sig is None:
        return None
    if all(type(value) is int for value in sig):
        return 'int'
    if all(type(value) is bool for value in sig):
        return 'bool'
    if all(type(value) in (str, bytes) for value in sig):
        return 'seq'
    return None


def eval_with_error(program, inputs):
    if program[0] == 'error':
        return ('ValueError',)
    if program[0] == 'if':
        condition = eval_program(program[1], inputs)
        if type(condition) is not bool:
            return BAD
        return eval_with_error(program[2] if condition else program[3], inputs)
    return eval_program(program, inputs)


def assess(programs, rows):
    tick_cpu = time.process_time()
    times = []
    correct = false = abstain = 0
    for inputs, actual in rows:
        tick = time.perf_counter()
        values = [eval_with_error(program, inputs) for program in programs]
        valid = [value for value in values if value is not BAD]
        unique = bool(valid and len(valid) == len(values) and all(
            type(value) is type(valid[0]) and value == valid[0] for value in valid))
        times.append((time.perf_counter() - tick) * 1000)
        if not unique:
            abstain += 1
        elif type(valid[0]) is type(actual) and valid[0] == actual:
            correct += 1
        else:
            false += 1
    return {'cases': len(rows), 'correct': correct, 'false': false,
            'abstain': abstain,
            'cpu_s': round(time.process_time() - tick_cpu, 6),
            'p50_ms': round(statistics.median(times), 6),
            'p95_ms': round(sorted(times)[(95 * len(times) + 99) // 100 - 1], 6)}


class Search:
    def __init__(self, inputs, outputs, scans):
        self.inputs = inputs
        self.outputs = outputs
        self.scans = scans
        self.tried = 0
        self.by_kind = defaultdict(list)
        self.seen = defaultdict(lambda: defaultdict(list))
        self.incompatible = 0
        self.expr_seen = set()
        self._slices = None
        self._slice_position = 0

    def add(self, expr):
        if expr in self.expr_seen:
            return True
        if self.tried >= CAP:
            return False
        self.expr_seen.add(expr)
        self.tried += 1
        sig = signature(expr, self.inputs)
        cls = kind(sig)
        if cls is None:
            self.incompatible += 1
            return True
        bucket = self.seen[cls][sig]
        if len(bucket) < 4:
            bucket.append(expr)
            self.by_kind[cls].append((expr, sig))
        return True

    def originals(self):
        a, b = ('arg', 0), ('arg', 1)
        for expr in (a, b, ('int', -1), ('int', 0), ('int', 1),
                     ('len', a), ('len', b)):
            self.add(expr)
        for spec in self.scans:
            self.add(('scan', spec_key(spec)))
        base = sorted((expr for expr, _ in self.by_kind['int']),
                      key=lambda expr: (cost(expr), str(expr)))
        arithmetic = sorted((('add', x, y) for x in base for y in base),
                            key=lambda expr: (cost(expr), str(expr)))
        # Interleave addition/subtraction by cost, not by operator or input pair.
        arithmetic = sorted([*arithmetic,
                             *(('sub', x, y) for x in base for y in base)],
                            key=lambda expr: (cost(expr), str(expr)))
        for expr in arithmetic:
            if self.tried >= 550:
                break
            self.add(expr)
        ints = sorted((expr for expr, _ in self.by_kind['int']),
                      key=lambda expr: (cost(expr), str(expr)))
        comparisons = sorted(((op, x, y) for op in ('eq', 'lt', 'ge')
                              for x in ints for y in (('int', -1), ('int', 0), ('int', 1))),
                             key=lambda expr: (cost(expr), str(expr)))
        for expr in comparisons:
            if self.tried >= 850:
                break
            self.add(expr)

    def expand_slices(self, quota):
        if self._slices is None:
            bounds = [('none',)] + sorted((expr for expr, _ in self.by_kind['int']),
                                           key=lambda expr: (cost(expr), str(expr)))
            self._slices = sorted((('slice', source, start, stop)
                                   for source in (('arg', 0), ('arg', 1))
                                   for start in bounds for stop in bounds),
                                  key=lambda expr: (cost(expr), str(expr)))
        used = 0
        while (used < quota and self.tried < CAP and
               self._slice_position < len(self._slices)):
            expr = self._slices[self._slice_position]
            self._slice_position += 1
            used += 1
            self.add(expr)

    def candidates_for_component(self, target):
        # The requested output is used only for search, never as a test answer.
        seq = list(self.by_kind['seq'])
        direct = sorted((expr for expr, values in seq if exact(values, target)),
                        key=lambda expr: (cost(expr), str(expr)))
        if direct:
            return direct[:4]
        # Search a conditional by matching each branch on the observations
        # where its predicate holds.  This is a typed factorization, not a
        # pre-written form for either target method.
        rivals = []
        for cond, bits in sorted(self.by_kind['bool'],
                                 key=lambda row: (cost(row[0]), str(row[0]))):
            if all(bits) or not any(bits):
                continue
            yes = sorted((expr for expr, values in seq if all(
                not flag or type(value) is type(want) and value == want
                for flag, value, want in zip(bits, values, target))),
                key=lambda expr: (cost(expr), str(expr)))
            no = sorted((expr for expr, values in seq if all(
                flag or type(value) is type(want) and value == want
                for flag, value, want in zip(bits, values, target))),
                key=lambda expr: (cost(expr), str(expr)))
            for a in yes[:2]:
                for b in no[:2]:
                    if self.tried >= CAP:
                        return sorted(rivals, key=lambda expr: (cost(expr), str(expr)))[:4]
                    expr = ('if', cond, a, b)
                    self.tried += 1
                    if exact(signature(expr, self.inputs) or (), target):
                        rivals.append(expr)
                        if len(rivals) >= 8:
                            return sorted(rivals, key=lambda row: (cost(row), str(row)))[:4]
        return sorted(rivals, key=lambda expr: (cost(expr), str(expr)))[:4]


def learn(inputs, outputs, scans):
    error_mask = [type(value) is tuple and value == ('ValueError',)
                  for value in outputs]
    normal_inputs = [row for row, failed in zip(inputs, error_mask) if not failed]
    normal_outputs = [row for row, failed in zip(outputs, error_mask) if not failed]
    if not normal_inputs:
        return {'programs': [], 'candidates': 0, 'part_candidates': [],
                'int_signatures': 0, 'bool_signatures': 0, 'seq_signatures': 0,
                'incompatible_candidates': 0}
    search = Search(normal_inputs, normal_outputs, scans)
    search.originals()
    error_condition = None
    if any(error_mask):
        for expr, _ in sorted(search.by_kind['int'],
                              key=lambda row: (cost(row[0]), str(row[0]))):
            for op in ('eq', 'lt', 'ge'):
                for value in (-1, 0, 1):
                    if search.tried >= CAP:
                        break
                    predicate = (op, expr, ('int', value))
                    search.tried += 1
                    bits = signature(predicate, inputs)
                    if bits is not None and list(bits) == error_mask:
                        error_condition = predicate
                        break
                if error_condition is not None:
                    break
            if error_condition is not None:
                break
    parts = (list(zip(*normal_outputs)) if normal_outputs and
             type(normal_outputs[0]) is tuple and all(
                 type(output) is tuple and len(output) == len(normal_outputs[0])
                 for output in normal_outputs) else [normal_outputs])
    learned = [[] for _ in parts]
    while search.tried < CAP and any(not choices for choices in learned):
        before = search.tried
        search.expand_slices(min(250, CAP - search.tried))
        for index, part in enumerate(parts):
            if not learned[index]:
                learned[index] = search.candidates_for_component(part)
        if search.tried == before:
            break
    if any(error_mask) and error_condition is None:
        programs = []
    elif any(not part for part in learned):
        programs = []
    elif len(parts) == 1 and not (normal_outputs and type(normal_outputs[0]) is tuple):
        programs = learned[0]
    else:
        programs = [('tuple', *(choices[0] for choices in learned))]
        for index, choices in enumerate(learned):
            for candidate in choices[1:]:
                row = list(programs[0])
                row[index + 1] = candidate
                programs.append(tuple(row))
    if error_condition is not None:
        programs = [('if', error_condition, ('error', 'ValueError'), program)
                    for program in programs]
    return {'programs': programs[:16], 'candidates': search.tried,
            'part_candidates': [len(part) for part in learned],
            'int_signatures': len(search.seen['int']),
            'bool_signatures': len(search.seen['bool']),
            'seq_signatures': len(search.seen['seq']),
            'incompatible_candidates': search.incompatible}


def train_scan(tree, seed):
    source_inputs = cases(tree, seed, 'text', 64)
    learned = []
    calls = 0
    tick = time.process_time()
    for method in ('find', 'count'):
        rows = [(item, observed(method, item)) for item in source_inputs]
        calls += len(rows)
        first, _ = fit(rows[:32], tool_programs())
        second, _ = fit(rows[32:], first)
        learned.extend(second)
    return list({spec_key(item): item for item in learned}.values()), calls, time.process_time() - tick


def evaluate_task(tree, seed, method, kind_name, scans, offset):
    inputs = varied_inputs(tree, seed + offset, kind_name, 80,
                           invalid_empty=(method in ('partition', 'rpartition')))
    empty = type(inputs[0][1])()
    inputs[0] = (inputs[0][0], empty)
    inputs[-1] = (inputs[-1][0], empty)
    rows = [(item, observed(method, item)) for item in inputs]
    education, validation = rows[:16], rows[16:]
    modes = {}
    for name, allowed in (('treatment', scans), ('flat', tool_programs())):
        tick = time.process_time()
        model = learn([item for item, _ in education],
                      [answer for _, answer in education], allowed)
        fit_cpu = time.process_time() - tick
        measured = assess(model['programs'], validation)
        modes[name] = {'model': {key: value for key, value in model.items()
                                 if key != 'programs'},
                       'fit_cpu_s': round(fit_cpu, 6),
                       'metric': measured}
    return modes


def main():
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    reports = []
    for seed in SEEDS:
        scans, tool_calls, scan_cpu = train_scan(h0, seed)
        source = evaluate_task(h0, seed, 'removeprefix', 'str', scans, 0)
        partition = evaluate_task(h0, seed, 'partition', 'bytes', scans, 1000)
        suffix = evaluate_task(h0, seed, 'removesuffix', 'str', scans, 2000)
        incompatible = evaluate_task(h0, seed, 'rpartition', 'bytes', scans, 3000)
        tasks = {'source': source, 'partition': partition, 'suffix': suffix,
                 'incompatible': incompatible}
        passed = True
        for target in ('partition', 'suffix'):
            t, f = tasks[target]['treatment'], tasks[target]['flat']
            passed &= bool(t['metric']['correct'] >= 61 and
                           t['metric']['false'] == 0 and
                           t['model']['candidates'] <= 0.7 * f['model']['candidates'] and
                           t['fit_cpu_s'] + t['metric']['cpu_s'] <=
                           f['fit_cpu_s'] + f['metric']['cpu_s'] and
                           t['metric']['p95_ms'] <= 10)
        passed &= source['treatment']['metric']['correct'] >= 61
        passed &= source['treatment']['metric']['false'] == 0
        passed &= incompatible['treatment']['metric']['false'] == 0
        reports.append({'seed': seed, 'scan_descriptions': len(scans),
                        'scan_education_calls': tool_calls,
                        'scan_education_cpu_s': round(scan_cpu, 6),
                        'tasks': tasks, 'gate_pass': bool(passed)})
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'preregistration': 'prereg/G-5b-busqueda-equilibrada-composicion.md',
              'kind': 'development_only', 'engine_tree': h0,
              'engine_unchanged': unchanged,
              'hashseed': os.environ.get('PYTHONHASHSEED'),
              'reports': reports, 'all_gates_pass': bool(unchanged and all(
                  report['gate_pass'] for report in reports)),
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    suffix = os.environ.get('PYTHONHASHSEED', 'unknown')
    (ROOT / 'results_v3' / f'g5b_cost_order_dev_hashseed{suffix}.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

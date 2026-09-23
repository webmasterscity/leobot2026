"""G-5 gate 2: bounded synthesis of typed compositions using acquired scans."""
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

from experiments.f17_typed_sequence_pilot import scan, tool_programs
from experiments.f7_typed_sequences_dev import git
from experiments.g5_scan_cross_type_dev import cases, fit, record


ROOT = Path(__file__).resolve().parents[1]
SEEDS = (17, 53, 97)
CAP = 2000
BAD = object()


def spec_key(spec):
    return (spec['source'], spec['pattern'], spec['match'],
            spec['overlap'], spec['reduce'])


def contains(program, subprogram):
    return program == subprogram or any(
        contains(child, subprogram) for child in program[1:]
        if isinstance(child, tuple) and child and isinstance(child[0], str))


def eval_program(expr, inputs, fuel=None):
    if fuel is None:
        fuel = [100]
    fuel[0] -= 1
    if fuel[0] < 0:
        return BAD
    op = expr[0]
    if op == 'arg':
        return inputs[expr[1]]
    if op == 'int':
        return expr[1]
    if op == 'none':
        return None
    if op == 'scan':
        fields = expr[1]
        return scan(dict(zip(('source', 'pattern', 'match', 'overlap', 'reduce'), fields)),
                    record(inputs))
    values = [eval_program(child, inputs, fuel) for child in expr[1:]]
    if any(value is BAD for value in values):
        return BAD
    try:
        if op == 'len' and type(values[0]) in (str, bytes, tuple, list):
            result = len(values[0])
        elif op in ('add', 'sub') and all(type(value) is int for value in values):
            result = values[0] + values[1] if op == 'add' else values[0] - values[1]
        elif op == 'eq':
            result = type(values[0]) is type(values[1]) and values[0] == values[1]
        elif op in ('lt', 'ge') and type(values[0]) is type(values[1]) is int:
            result = values[0] < values[1] if op == 'lt' else values[0] >= values[1]
        elif op == 'slice' and type(values[0]) in (str, bytes, tuple, list) and all(
                value is None or type(value) is int for value in values[1:]):
            result = values[0][slice(values[1], values[2])]
        elif op == 'if' and type(values[0]) is bool:
            result = values[1] if values[0] else values[2]
        elif op == 'tuple':
            result = tuple(values)
        else:
            return BAD
    except (TypeError, ValueError, IndexError, OverflowError):
        return BAD
    if type(result) is int and abs(result) > 10**6:
        return BAD
    if type(result) in (str, bytes, tuple, list) and len(result) > 256:
        return BAD
    return result


def signature(expr, inputs):
    values = tuple(eval_program(expr, row) for row in inputs)
    return None if any(value is BAD for value in values) else values


class Pools:
    def __init__(self, inputs, scans):
        self.inputs = inputs
        self.scans = scans
        self.attempts = 0
        self.by_type = {'int': [], 'bool': [], 'seq': []}
        self.signatures = {'int': defaultdict(list), 'bool': defaultdict(list),
                           'seq': defaultdict(list)}

    def add(self, expr, kind):
        if self.attempts >= CAP:
            return False
        self.attempts += 1
        sig = signature(expr, self.inputs)
        if sig is None:
            return True
        if kind == 'int' and not all(type(item) is int for item in sig):
            return True
        if kind == 'bool' and not all(type(item) is bool for item in sig):
            return True
        if kind == 'seq' and not all(type(item) in (str, bytes) for item in sig):
            return True
        keep = self.signatures[kind][sig]
        if len(keep) < 2:
            keep.append(expr)
            self.by_type[kind].append((expr, sig))
        return True


def build_pools(inputs, scans, source_macro=None):
    pool = Pools(inputs, scans)
    a, b = ('arg', 0), ('arg', 1)
    for expr in (a, b):
        pool.add(expr, 'seq')
    for value in (-1, 0, 1):
        pool.add(('int', value), 'int')
    for expr in (a, b):
        pool.add(('len', expr), 'int')
    for spec in scans:
        pool.add(('scan', spec_key(spec)), 'int')
    basics = [expr for expr, _ in pool.by_type['int']]
    # Generic one-step arithmetic.  Equivalent signatures are kept as rivals.
    for op in ('add', 'sub'):
        for left in basics:
            for right in basics:
                if pool.attempts >= 700:
                    break
                pool.add((op, left, right), 'int')
    ints = [expr for expr, _ in pool.by_type['int']]
    for op in ('eq', 'lt', 'ge'):
        for left in ints:
            for right in (('int', -1), ('int', 0), ('int', 1)):
                if pool.attempts >= 1000:
                    break
                pool.add((op, left, right), 'bool')
    ints = [expr for expr, _ in pool.by_type['int']]
    bounds = [('none',), *ints]
    for seq in (a, b):
        for start in bounds:
            for stop in bounds:
                if pool.attempts >= 1700:
                    break
                pool.add(('slice', seq, start, stop), 'seq')
    if source_macro is not None and pool.attempts < CAP:
        pool.add(source_macro, 'seq')
    return pool


def exact(values, expected):
    return len(values) == len(expected) and all(type(a) is type(b) and a == b
                                                 for a, b in zip(values, expected))


def component(pool, target):
    choices = [expr for expr, values in pool.by_type['seq'] if exact(values, target)]
    if choices:
        return choices[:8]
    seq = pool.by_type['seq']
    for cond, bits in pool.by_type['bool']:
        if all(bits) or not any(bits):
            continue
        yes = [expr for expr, values in seq if all(
            not flag or type(value) is type(want) and value == want
            for flag, value, want in zip(bits, values, target))]
        no = [expr for expr, values in seq if all(
            flag or type(value) is type(want) and value == want
            for flag, value, want in zip(bits, values, target))]
        for left in yes[:4]:
            for right in no[:4]:
                if pool.attempts >= CAP:
                    return choices[:8]
                expr = ('if', cond, left, right)
                pool.attempts += 1
                if exact(signature(expr, pool.inputs) or (), target):
                    choices.append(expr)
                    if len(choices) >= 8:
                        return choices
    return choices


def learn(inputs, outputs, scans, source_macro=None):
    pool = build_pools(inputs, scans, source_macro)
    if outputs and type(outputs[0]) is tuple and all(
            type(output) is tuple and len(output) == len(outputs[0])
            for output in outputs):
        alternatives = []
        for index in range(len(outputs[0])):
            candidate = component(pool, [row[index] for row in outputs])
            if not candidate:
                return {'status': 'no_program', 'candidates': pool.attempts,
                        'programs': [], 'component': index}
            alternatives.append(candidate)
        # Multiple components remain independent hypotheses; never choose by
        # looking at target validation outputs.
        programs = [('tuple', *(part[0] for part in alternatives))]
        for i, part in enumerate(alternatives):
            for rival in part[1:]:
                variant = list(programs[0])
                variant[i + 1] = rival
                programs.append(tuple(variant))
    else:
        programs = component(pool, outputs)
    return {'status': 'learned_hypotheses' if programs else 'no_program',
            'candidates': pool.attempts, 'programs': programs[:16],
            'int_signatures': len(pool.signatures['int']),
            'bool_signatures': len(pool.signatures['bool']),
            'sequence_signatures': len(pool.signatures['seq'])}


def assess(programs, rows):
    cpu = time.process_time()
    times = []
    correct = false = abstain = 0
    for inputs, actual in rows:
        tick = time.perf_counter()
        predictions = [eval_program(program, inputs) for program in programs]
        valid = [value for value in predictions if value is not BAD]
        unique = bool(valid and len(valid) == len(predictions) and all(
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
            'cpu_s': round(time.process_time() - cpu, 6),
            'p50_ms': round(statistics.median(times), 6),
            'p95_ms': round(sorted(times)[(95 * len(times) + 99) // 100 - 1], 6)}


def varied_inputs(tree, seed, kind, count, invalid_empty=False):
    digest = sha256((tree + ':G5:composition:' + str(seed) + ':' + kind).encode()).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    alphabet = ('a', 'b', 'c', 'd') if kind == 'str' else (0, 1, 2, 255)
    rows = []
    seen = set()
    while len(rows) < count:
        length = rng.randrange(0, 13)
        values = [rng.choice(alphabet) for _ in range(length)]
        mode = len(rows) % 4
        if mode == 0 and values:
            piece = values[:rng.randrange(1, min(4, len(values)) + 1)]
        elif mode == 1 and values:
            index = rng.randrange(len(values))
            piece = values[index:index + rng.randrange(1, 4)]
        elif mode == 2:
            piece = [rng.choice(alphabet) for _ in range(rng.randrange(1, 4))]
        else:
            piece = [alphabet[-1], alphabet[-1]]
        if invalid_empty and len(rows) == count - 1:
            piece = []
        source = ''.join(values) if kind == 'str' else bytes(values)
        pattern = ''.join(piece) if kind == 'str' else bytes(piece)
        if (source, pattern) in seen:
            continue
        seen.add((source, pattern))
        rows.append((source, pattern))
    return rows


def observed(method, inputs):
    try:
        return getattr(inputs[0], method)(inputs[1])
    except ValueError:
        return ('ValueError',)


def main():
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    reports = []
    for seed in SEEDS:
        source_rows = cases(h0, seed, 'text', 64)
        learned = []
        for method in ('find', 'count'):
            observed_rows = [(item, observed(method, item)) for item in source_rows]
            first, _ = fit(observed_rows[:32], tool_programs())
            second, _ = fit(observed_rows[32:], first)
            learned.extend(second)
        learned = list({spec_key(item): item for item in learned}.values())
        source_inputs = varied_inputs(h0, seed, 'str', 80)
        target_inputs = varied_inputs(h0, seed, 'bytes', 80, invalid_empty=True)
        source_education = [(item, observed('removeprefix', item))
                            for item in source_inputs[:16]]
        source_validation = [(item, observed('removeprefix', item))
                             for item in source_inputs[16:]]
        target_education = [(item, observed('partition', item))
                            for item in target_inputs[:16]]
        target_validation = [(item, observed('partition', item))
                             for item in target_inputs[16:]]
        tick = time.process_time()
        source_model = learn([item for item, _ in source_education],
                             [value for _, value in source_education], learned)
        source_fit_cpu = time.process_time() - tick
        source_assessment = assess(source_model['programs'], source_validation)
        macro = source_model['programs'][0] if source_model['programs'] else None
        modes = {}
        for name, scans, use_macro in (
                ('treatment', learned, macro),
                ('flat', tool_programs(), None),
                ('scan_alone', learned, None)):
            tick = time.process_time()
            model = learn([item for item, _ in target_education],
                          [value for _, value in target_education], scans, use_macro)
            fit_cpu = time.process_time() - tick
            metric = assess(model['programs'], target_validation)
            modes[name] = {'status': model['status'],
                           'candidates': model['candidates'],
                           'fit_cpu_s': round(fit_cpu, 6),
                           'metric': metric,
                           'uses_source_macro': bool(use_macro and any(
                               contains(program, use_macro)
                               for program in model['programs'])),
                           'uses_acquired_scan': any(
                               contains(program, ('scan', spec_key(spec)))
                               for program in model['programs'] for spec in learned)}
        t, f = modes['treatment'], modes['flat']
        gate = bool(source_assessment['correct'] >= 61 and
                    source_assessment['false'] == 0 and
                    t['metric']['correct'] >= 61 and t['metric']['false'] == 0 and
                    (t['candidates'] <= 0.7 * f['candidates']) and
                    t['fit_cpu_s'] + t['metric']['cpu_s'] <=
                    f['fit_cpu_s'] + f['metric']['cpu_s'] and
                    t['uses_acquired_scan'] and
                    t['metric']['p95_ms'] <= 10)
        reports.append({'seed': seed, 'scan_descriptions': len(learned),
                        'source_examples': len(source_education),
                        'source_programs': len(source_model['programs']),
                        'source_candidates': source_model['candidates'],
                        'source_fit_cpu_s': round(source_fit_cpu, 6),
                        'source_validation': source_assessment,
                        'target_examples': len(target_education),
                        'target_validation_cases': len(target_validation),
                        'modes': modes, 'gate2_pass': gate})
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'preregistration': 'prereg/G-5-composicion-de-operadores-observados.md',
              'kind': 'gate2_development_only', 'engine_tree': h0,
              'engine_unchanged': unchanged, 'hashseed': os.environ.get('PYTHONHASHSEED'),
              'reports': reports, 'all_gate2_pass': bool(unchanged and all(
                  report['gate2_pass'] for report in reports)),
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    suffix = os.environ.get('PYTHONHASHSEED', 'unknown')
    (ROOT / 'results_v3' / f'g5_composition_dev_hashseed{suffix}.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

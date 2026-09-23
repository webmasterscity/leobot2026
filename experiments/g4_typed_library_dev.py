"""G-4 pilot: typed, bounded AST fragments as data; never run source code."""
from __future__ import annotations

import ast
import json
import random
import resource
import time
import warnings
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import permutations
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g3_mbpp_inventory import URL, test_example


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'ccf64ceae9c5403bf50a044cb6d505bfd2a2963ee58338ba268fd65beab92a9f'
SEEDS = (17, 53, 97)
LIMIT = 2000
BAD = object()
BINOPS = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul',
          ast.FloorDiv: 'floordiv', ast.Mod: 'mod'}
CMPOPS = {ast.Eq: 'eq', ast.NotEq: 'ne', ast.Lt: 'lt', ast.LtE: 'le',
          ast.Gt: 'gt', ast.GtE: 'ge'}
UNARY = {'len', 'sum', 'min', 'max'}
MAX_VALUE_SIZE = 64
MAX_MAGNITUDE = 1_000_000


def compile_fragment(node: ast.AST, names: dict[str, int], depth: int = 0):
    if depth > 8:
        return None
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if node.id not in names:
            names[node.id] = len(names)
        return ('var', names[node.id]) if len(names) <= 4 else None
    if isinstance(node, ast.Constant):
        value = node.value
        if type(value) is int and -1 <= value <= 1:
            return ('const', value)
        if type(value) is bool:
            return ('const', value)
        if type(value) is str and len(value) <= 2:
            return ('const', value)
        return None
    if isinstance(node, ast.UnaryOp):
        op = 'neg' if isinstance(node.op, ast.USub) else (
            'not' if isinstance(node.op, ast.Not) else None)
        child = compile_fragment(node.operand, names, depth + 1)
        return (op, child) if op and child else None
    if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
        a = compile_fragment(node.left, names, depth + 1)
        b = compile_fragment(node.right, names, depth + 1)
        return (BINOPS[type(node.op)], a, b) if a and b else None
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMPOPS:
        a = compile_fragment(node.left, names, depth + 1)
        b = compile_fragment(node.comparators[0], names, depth + 1)
        return (CMPOPS[type(node.ops[0])], a, b) if a and b else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        op = node.func.id
        if op not in UNARY or len(node.args) != 1 or node.keywords:
            return None
        child = compile_fragment(node.args[0], names, depth + 1)
        return (op, child) if child else None
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
        sequence = compile_fragment(node.value, names, depth + 1)
        if isinstance(node.slice, ast.Slice):
            if node.slice.step is not None:
                return None
            bounds = []
            for bound in (node.slice.lower, node.slice.upper):
                bounds.append(('none',) if bound is None else
                              compile_fragment(bound, names, depth + 1))
            return ('slice', sequence, *bounds) if sequence and all(bounds) else None
        index = compile_fragment(node.slice, names, depth + 1)
        return ('index', sequence, index) if sequence and index else None
    if isinstance(node, (ast.List, ast.Tuple)) and isinstance(node.ctx, ast.Load):
        if len(node.elts) > 4:
            return None
        children = [compile_fragment(item, names, depth + 1) for item in node.elts]
        return ('list' if isinstance(node, ast.List) else 'tuple', *children) if all(children) else None
    return None


def count_nodes(program: tuple) -> int:
    return 1 + sum(count_nodes(item) for item in program[1:] if isinstance(item, tuple))


def vars_used(program: tuple) -> set[int]:
    if program[0] == 'var':
        return {program[1]}
    result = set()
    for child in program[1:]:
        if isinstance(child, tuple):
            result.update(vars_used(child))
    return result


def substitute(program: tuple, mapped: tuple[tuple, ...]) -> tuple:
    if program[0] == 'var':
        return mapped[program[1]]
    return (program[0], *(substitute(item, mapped) if isinstance(item, tuple) else item
                          for item in program[1:]))


def acceptable(value) -> bool:
    if type(value) is int:
        return abs(value) <= MAX_MAGNITUDE
    if type(value) is bool or value is None:
        return True
    if type(value) is str:
        return len(value) <= MAX_VALUE_SIZE
    if type(value) in (tuple, list):
        return len(value) <= MAX_VALUE_SIZE and all(acceptable(item) for item in value)
    return False


def evaluate(program: tuple, args: tuple, fuel: list[int]):
    fuel[0] -= 1
    if fuel[0] < 0:
        return BAD
    op = program[0]
    if op == 'var':
        return args[program[1]] if program[1] < len(args) else BAD
    if op == 'const':
        return program[1]
    if op == 'none':
        return None
    values = [evaluate(child, args, fuel) for child in program[1:]]
    if BAD in values or any(not acceptable(value) for value in values):
        return BAD
    try:
        if op == 'neg' and type(values[0]) is int:
            result = -values[0]
        elif op == 'not':
            result = not values[0]
        elif op in BINOPS.values() and len(values) == 2:
            a, b = values
            if op == 'add' and type(a) is type(b) and type(a) in (int, str, list, tuple):
                result = a + b
            elif op == 'sub' and type(a) is type(b) is int:
                result = a - b
            elif op == 'mul' and type(a) is type(b) is int:
                result = a * b
            elif op in ('mod', 'floordiv') and type(a) is type(b) is int and b:
                result = a % b if op == 'mod' else a // b
            else:
                return BAD
        elif op in CMPOPS.values() and len(values) == 2:
            a, b = values
            if type(a) is not type(b):
                return BAD
            result = {'eq': lambda: a == b, 'ne': lambda: a != b,
                      'lt': lambda: a < b, 'le': lambda: a <= b,
                      'gt': lambda: a > b, 'ge': lambda: a >= b}[op]()
        elif op == 'len' and type(values[0]) in (str, list, tuple):
            result = len(values[0])
        elif op == 'sum' and type(values[0]) in (list, tuple) and all(
                type(item) is int for item in values[0]):
            result = sum(values[0])
        elif op in ('min', 'max') and type(values[0]) in (list, tuple) and values[0] and all(
                type(item) is type(values[0][0]) for item in values[0]):
            result = min(values[0]) if op == 'min' else max(values[0])
        elif op == 'index' and type(values[0]) in (str, list, tuple) and type(values[1]) is int:
            result = values[0][values[1]]
        elif op == 'slice' and type(values[0]) in (str, list, tuple) and all(
                bound is None or type(bound) is int for bound in values[1:]):
            result = values[0][slice(values[1], values[2])]
        elif op == 'list':
            result = values
        elif op == 'tuple':
            result = tuple(values)
        else:
            return BAD
    except (ValueError, TypeError, IndexError, ZeroDivisionError, OverflowError):
        return BAD
    return result if acceptable(result) else BAD


def typed_equal(a, b) -> bool:
    return type(a) is type(b) and a == b


def load_rows():
    with urlopen(URL, timeout=15) as response:
        raw = response.read(2_000_000)
    if sha256(raw).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('Fuente cambiante')
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        for line in raw.splitlines():
            item = json.loads(line)
            if not 601 <= item['task_id'] <= 974:
                continue
            try:
                root = ast.parse(item['code'])
            except SyntaxError:
                root = ast.Module(body=[], type_ignores=[])
            defs = [node for node in root.body if isinstance(node, ast.FunctionDef)]
            tests = ([test_example(text, defs[0].name) for text in item['test_list']]
                     if len(defs) == 1 else [])
            rows.append((item['task_id'], root, tests, item['text']))
    return sorted(rows)


def library(source_rows):
    evidence = defaultdict(set)
    extracted = 0
    for task_id, root, _, _ in source_rows:
        for fn in (node for node in root.body if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(fn):
                if not isinstance(node, (ast.BinOp, ast.Compare, ast.Call,
                                         ast.Subscript, ast.List, ast.Tuple, ast.UnaryOp)):
                    continue
                names = {}
                program = compile_fragment(node, names)
                if (program is None or not names or len(names) > 4 or
                    count_nodes(program) > 8):
                    continue
                evidence[program].add(task_id)
                extracted += 1
    reusable = {program: ids for program, ids in evidence.items() if len(ids) >= 2}
    ranked = sorted(reusable, key=lambda p: (-len(reusable[p]), count_nodes(p), str(p)))
    return ranked, reusable, {'extracted_fragments': extracted,
                               'distinct_fragments': len(evidence),
                               'reusable_fragments': len(reusable),
                               'supported_task_links': sum(map(len, reusable.values()))}


def instantiations(program: tuple, arity: int):
    used = vars_used(program)
    if not used or max(used) >= arity:
        if not used:
            yield program
        return
    for mapping in permutations(range(arity), max(used) + 1):
        yield substitute(program, tuple(('var', i) for i in mapping))


def flat(arity: int):
    leaves = [('var', i) for i in range(arity)] + [('const', v) for v in (-1, 0, 1)]
    for item in leaves:
        yield item
    for op in ('len', 'sum', 'min', 'max'):
        for leaf in leaves:
            yield (op, leaf)
    for op in ('add', 'sub', 'mul', 'mod', 'floordiv',
               'eq', 'ne', 'lt', 'le', 'gt', 'ge', 'index'):
        for a in leaves:
            for b in leaves:
                yield (op, a, b)
    for op in ('len', 'sum', 'min', 'max'):
        for a in leaves:
            for b in leaves:
                yield (op, ('index', a, b))
                yield (op, ('add', a, b))


def compositions(ranked: list[tuple], support: dict):
    unary = [p for p in ranked if vars_used(p) == {0}][:32]
    pairs = sorted(((a, b) for a in unary for b in unary if a != b and
                    count_nodes(a) + count_nodes(b) <= 8),
                   key=lambda pair: (-(len(support[pair[0]]) + len(support[pair[1]])),
                                     count_nodes(pair[0]) + count_nodes(pair[1]),
                                     str(pair)))
    for a, b in pairs:
        yield substitute(a, (b,))


def proposals(arity: int, ranked: list[tuple], support: dict, treatment: bool):
    seen = set()
    streams = []
    if treatment:
        streams.append((program for item in ranked for program in instantiations(item, arity)))
        streams.append((program for item in compositions(ranked, support)
                        for program in instantiations(item, arity)))
    streams.append(flat(arity))
    for stream in streams:
        for program in stream:
            if program in seen:
                continue
            seen.add(program)
            yield program
            if len(seen) >= LIMIT:
                return


def eligible(tests):
    return bool(len(tests) == 3 and all(test is not None for test in tests) and
                len({len(args) for args, _ in tests}) == 1 and
                1 <= len(tests[0][0]) <= 4 and
                all(acceptable(value) for args, expected in tests
                    for value in (*args, expected)))


def solve(tests, candidates):
    args1, expected1 = tests[0]
    args2, expected2 = tests[1]
    args3, expected3 = tests[2]
    consistent = []
    seen = 0
    for program in candidates:
        seen += 1
        a = evaluate(program, args1, [100])
        if a is BAD or not typed_equal(a, expected1):
            continue
        b = evaluate(program, args2, [100])
        if b is BAD or not typed_equal(b, expected2):
            continue
        consistent.append(program)
    predictions = [(program, evaluate(program, args3, [100])) for program in consistent]
    valid = [value for _, value in predictions if value is not BAD]
    unique = bool(valid and len(valid) == len(predictions) and
                  all(typed_equal(value, valid[0]) for value in valid))
    return {'candidates': seen, 'consistent': len(consistent),
            'unique': unique, 'correct': bool(unique and typed_equal(valid[0], expected3)),
            'false': bool(unique and not typed_equal(valid[0], expected3)),
            'any_correct': any(value is not BAD and typed_equal(value, expected3)
                               for _, value in predictions),
            'composite_consistent': sum(count_nodes(p) >= 4 for p in consistent)}


def main():
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    reading_start = time.process_time()
    data = load_rows()
    reading_cpu = time.process_time() - reading_start
    reports = []
    for seed in SEEDS:
        order = list(data)
        random.Random(int(h0[:8], 16) ^ seed).shuffle(order)
        cut = int(len(order) * 0.7)
        train, dev = order[:cut], order[cut:]
        acquisition_start = time.process_time()
        ranked, support, source_stats = library(train)
        acquisition_cpu = time.process_time() - acquisition_start
        outcomes = []
        for task_id, _, tests, _ in dev:
            if not eligible(tests):
                outcomes.append({'id': task_id, 'eligible': False})
                continue
            arity = len(tests[0][0])
            task = {'id': task_id, 'eligible': True}
            for treatment in (True, False):
                tick = time.process_time()
                result = solve(tests, proposals(arity, ranked, support, treatment))
                result['cpu_s'] = round(time.process_time() - tick, 6)
                task['library' if treatment else 'flat'] = result
            outcomes.append(task)
        totals = {}
        for key in ('library', 'flat'):
            chosen = [item[key] for item in outcomes if item['eligible']]
            totals[key] = {'unique_correct': sum(item['correct'] for item in chosen),
                           'unique_false': sum(item['false'] for item in chosen),
                           'any_correct': sum(item['any_correct'] for item in chosen),
                           'ambiguous_or_unknown': len(chosen) - sum(item['unique'] for item in chosen),
                           'candidates': sum(item['candidates'] for item in chosen),
                           'cpu_s': round(sum(item['cpu_s'] for item in chosen), 6)}
        reports.append({'seed': seed, 'train': len(train), 'dev': len(dev),
                        'eligible_dev': sum(item['eligible'] for item in outcomes),
                        'source': source_stats,
                        'acquisition_cpu_s': round(acquisition_cpu, 6),
                        'totals': totals, 'tasks': outcomes,
                        'gate': bool(totals['library']['unique_false'] == 0 and
                                     totals['library']['unique_correct'] >= 0.2 * len(dev) and
                                     totals['library']['unique_correct'] -
                                     totals['flat']['unique_correct'] >= 0.1 * len(dev) and
                                     totals['library']['cpu_s'] <= 2 * totals['flat']['cpu_s'])})
    if git('rev-parse', 'HEAD:leobot') != h0:
        raise RuntimeError('Motor cambió')
    output = {'preregistration': 'prereg/G-4-biblioteca-tipificada-de-subprogramas.md',
              'kind': 'development_pilot', 'engine_tree': h0,
              'source_sha256': SOURCE_SHA256, 'source_rows': len(data),
              'reading_cpu_s': round(reading_cpu, 6),
              'reports': reports, 'all_gates_pass': all(r['gate'] for r in reports),
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3' / 'g4_typed_library_dev.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in output.items() if k != 'reports'}, ensure_ascii=False))
    for report in reports:
        print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

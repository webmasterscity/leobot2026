"""Inventory executable evidence in the official MBPP training split; parse only."""
from __future__ import annotations

import ast
import json
import resource
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
URL = 'https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl'


def literal(node: ast.AST):
    """Reject dynamic test expressions; ast.literal_eval never invokes target code."""
    value = ast.literal_eval(node)
    if type(value) not in (str, int, float, bool, type(None), tuple, list, dict, set):
        raise ValueError('Tipo de prueba no admitido')
    if len(repr(value)) > 512:
        raise ValueError('Prueba demasiado grande')
    return value


def test_example(text: str, function: str) -> tuple | None:
    try:
        root = ast.parse(text, mode='exec')
        if len(root.body) != 1 or not isinstance(root.body[0], ast.Assert):
            return None
        compare = root.body[0].test
        if (not isinstance(compare, ast.Compare) or len(compare.ops) != 1 or
            not isinstance(compare.ops[0], ast.Eq) or
            len(compare.comparators) != 1 or
            not isinstance(compare.left, ast.Call) or
            not isinstance(compare.left.func, ast.Name) or
            compare.left.func.id != function or compare.left.keywords):
            return None
        args = tuple(literal(arg) for arg in compare.left.args)
        expected = literal(compare.comparators[0])
        return (args, expected)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return None


def shape(node: ast.AST) -> tuple:
    if isinstance(node, ast.Name):
        return ('name',)
    if isinstance(node, ast.Constant):
        return ('literal', type(node.value).__name__)
    return (type(node).__name__, tuple(shape(child) for child in ast.iter_child_nodes(node)))


def semantic_shape(node: ast.AST) -> tuple:
    """Retain operation names, erase task identifiers and literal answers."""
    if isinstance(node, ast.Call):
        func = node.func
        operator = (func.id if isinstance(func, ast.Name) else
                    '.' + func.attr if isinstance(func, ast.Attribute) else '?')
        operands = ([func.value] if isinstance(func, ast.Attribute) else []) + node.args
        return ('Call', operator, tuple(semantic_shape(arg) for arg in operands))
    if isinstance(node, ast.Name):
        return ('name',)
    if isinstance(node, ast.Constant):
        return ('literal', type(node.value).__name__)
    return (type(node).__name__, tuple(semantic_shape(child)
                                     for child in ast.iter_child_nodes(node)))


def main() -> None:
    cpu, wall = time.process_time(), time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    with urlopen(URL, timeout=15) as response:
        raw = response.read(2_000_000)
    rows = [json.loads(line) for line in raw.splitlines()]
    if len(rows) != 974:
        raise RuntimeError('Tamaño inesperado de la fuente')
    stats = Counter()
    shapes = defaultdict(set)
    components = defaultdict(set)
    one_expr_ops = Counter()
    for row in rows:
        task_id = row['task_id']
        if not 601 <= task_id <= 974:
            continue
        stats['training_rows'] += 1
        try:
            root = ast.parse(row['code'], mode='exec')
        except SyntaxError:
            stats['solution_parse_error'] += 1
            continue
        defs = [node for node in root.body if isinstance(node, ast.FunctionDef)]
        if len(defs) != 1:
            stats['not_one_function'] += 1
            continue
        fn = defs[0]
        if fn.decorator_list or fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs:
            stats['special_signature'] += 1
            continue
        tests = [test_example(test, fn.name) for test in row['test_list']]
        if all(test is not None for test in tests) and len(tests) >= 3:
            for item in ast.walk(fn):
                if not isinstance(item, (ast.Call, ast.BinOp, ast.Compare,
                                         ast.Subscript, ast.IfExp, ast.ListComp,
                                         ast.GeneratorExp)):
                    continue
                size = sum(1 for _ in ast.walk(item))
                if 4 <= size <= 15:
                    components[semantic_shape(item)].add(task_id)
        if all(test is not None for test in tests) and len(tests) >= 3:
            stats['three_literal_io_tests'] += 1
            if (all(1 <= len(args) <= 4 and all(type(arg) is int for arg in args)
                    and type(expected) is int for args, expected in tests) and
                len({len(args) for args, _ in tests}) == 1):
                stats['numeric_io_program_learner_compatible'] += 1
            if (all(1 <= len(args) <= 4 and all(type(arg) is str for arg in args)
                    and type(expected) is str for args, expected in tests) and
                len({len(args) for args, _ in tests}) == 1):
                stats['text_io'] += 1
            if (all(1 <= len(args) <= 4 and all(type(arg) in (str, int) for arg in args)
                    and type(expected) in (str, int, bool, list, tuple)
                    for args, expected in tests) and
                len({len(args) for args, _ in tests}) == 1):
                stats['bounded_scalar_or_sequence_io'] += 1
        if len(root.body) != 1 or len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return):
            stats['not_single_return'] += 1
            continue
        stats['single_return'] += 1
        expr = fn.body[0].value
        nodes = list(ast.walk(expr))
        if len(nodes) > 50 or len(fn.args.args) > 4:
            stats['return_over_budget'] += 1
            continue
        if all(test is not None for test in tests) and len(tests) >= 3:
            stats['single_return_three_literal_io_tests'] += 1
            shapes[shape(expr)].add(task_id)
            for node in nodes:
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        one_expr_ops[node.func.id] += 1
                    elif isinstance(node.func, ast.Attribute):
                        one_expr_ops['.' + node.func.attr] += 1
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    repeated = {item: ids for item, ids in shapes.items() if len(ids) >= 2}
    repeated_components = {item: ids for item, ids in components.items() if len(ids) >= 2}
    output = {
        'kind': 'source_feasibility_only', 'source_url': URL,
        'source_sha256': sha256(raw).hexdigest(), 'engine_tree': tree,
        'train_task_ids': '601-974', 'rows_downloaded': len(rows),
        'counts': dict(stats), 'distinct_single_return_shapes': len(shapes),
        'repeated_single_return_shapes': len(repeated),
        'rows_in_repeated_shapes': sum(len(ids) for ids in repeated.values()),
        'distinct_nontrivial_components': len(components),
        'components_repeated_across_tasks': len(repeated_components),
        'task_component_links_repeated': sum(len(ids) for ids in repeated_components.values()),
        'top_calls_single_return': one_expr_ops.most_common(15),
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (ROOT / 'results_v3' / 'g3_mbpp_inventory.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

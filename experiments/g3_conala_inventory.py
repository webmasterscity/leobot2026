"""Read-only inventory of human intent/program pairs; never execute snippets."""
from __future__ import annotations

import ast
import json
import resource
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
DATASET = 'neulab/conala'
REVISION = 'fbc749f1c537e5c3834e93b15784302e331debe2'
SAFE_STRUCTURE = {
    ast.Module, ast.Expr, ast.Expression, ast.Call, ast.Name, ast.Load,
    ast.Attribute, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Subscript, ast.Slice,
    ast.keyword, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Pow, ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.BitOr, ast.BitAnd, ast.BitXor, ast.LShift, ast.RShift,
}


def fetch() -> list[dict]:
    result = []
    total = None
    while total is None or len(result) < total:
        query = urlencode({'dataset': DATASET, 'config': 'curated',
                           'split': 'train', 'revision': REVISION,
                           'offset': len(result), 'length': 100})
        with urlopen('https://datasets-server.huggingface.co/rows?' + query,
                     timeout=15) as response:
            page = json.load(response)
        if total is None:
            total = page['num_rows_total']
        if total != page['num_rows_total'] or not page['rows']:
            raise RuntimeError('Fuente incompleta o cambiante')
        result.extend(item['row'] for item in page['rows'])
    if len(result) != total:
        raise RuntimeError('Filas inconsistentes')
    return result


def skeleton(node: ast.AST) -> tuple:
    """Discard literal answers and names to count reusable program shapes."""
    if isinstance(node, ast.Name):
        return ('Name',)
    if isinstance(node, ast.Constant):
        return ('Constant', type(node.value).__name__)
    if isinstance(node, ast.Attribute):
        return ('Attribute', skeleton(node.value))
    fields = []
    for _, value in ast.iter_fields(node):
        if isinstance(value, ast.AST):
            fields.append(skeleton(value))
        elif isinstance(value, list):
            fields.append(tuple(skeleton(item) for item in value
                                if isinstance(item, ast.AST)))
    return (type(node).__name__, *fields)


def depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    return 1 + max((depth(child) for child in children), default=0)


def main() -> None:
    cpu = time.process_time()
    wall = time.monotonic()
    tree = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != tree or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado')
    data = fetch()
    digest = sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()).hexdigest()
    stats = Counter()
    shape_sources = defaultdict(set)
    nodes = []
    names = Counter()
    for row in data:
        if not {'question_id', 'intent', 'rewritten_intent', 'snippet'} <= set(row):
            raise RuntimeError('Fuente con esquema inesperado')
        snippet = row['snippet']
        if not isinstance(snippet, str):
            stats['not_text'] += 1
            continue
        try:
            parsed = ast.parse(snippet, mode='exec')
        except SyntaxError:
            stats['syntax_error'] += 1
            continue
        stats['parsed'] += 1
        if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.Expr):
            stats['not_single_expression'] += 1
            continue
        stats['single_expression'] += 1
        body = parsed.body[0].value
        count = sum(1 for _ in ast.walk(body))
        nodes.append(count)
        free = {item.id for item in ast.walk(body)
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)}
        for item in ast.walk(body):
            if isinstance(item, ast.Call):
                if isinstance(item.func, ast.Name):
                    names[item.func.id] += 1
                elif isinstance(item.func, ast.Attribute):
                    names['.' + item.func.attr] += 1
        structural = all(type(item) in SAFE_STRUCTURE for item in ast.walk(body))
        bounded = structural and count <= 50 and depth(body) <= 8 and len(free) <= 4
        if bounded:
            stats['bounded_expression_structure'] += 1
            shape_sources[skeleton(body)].add(str(row['question_id']))
        else:
            stats['outside_bounded_structure'] += 1
    repeated = {shape: sources for shape, sources in shape_sources.items()
                if len(sources) >= 2}
    if git('rev-parse', 'HEAD:leobot') != tree:
        raise RuntimeError('Motor cambió')
    output = {
        'kind': 'source_feasibility_only', 'source': DATASET,
        'revision': REVISION, 'split': 'curated/train',
        'source_url': 'https://conala-corpus.github.io/',
        'engine_tree': tree, 'rows': len(data), 'canonical_sha256': digest,
        'counts': dict(stats), 'bounded_distinct_shapes': len(shape_sources),
        'bounded_shapes_repeated_across_questions': len(repeated),
        'bounded_rows_in_repeated_shapes': sum(len(sources) for sources in repeated.values()),
        'top_called_operations': names.most_common(15),
        'max_ast_nodes_single_expression': max(nodes, default=0),
        'cpu_total_s': round(time.process_time() - cpu, 6),
        'wall_total_s': round(time.monotonic() - wall, 6),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    path = ROOT / 'results_v3' / 'g3_conala_inventory.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

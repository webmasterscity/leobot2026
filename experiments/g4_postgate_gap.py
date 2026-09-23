"""Post-failure diagnosis of which target structures G-4 cannot express."""
from __future__ import annotations

import ast
import json
import resource
import time
from collections import Counter
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g4_typed_library_dev import compile_fragment, load_rows


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cpu, wall = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0:
        raise RuntimeError('Motor cambiante')
    result = json.loads((ROOT / 'results_v3' / 'g4_typed_library_dev_hashseed0.json').read_text())
    failed = {task['id'] for group in result['reports'] for task in group['tasks']
              if task['eligible'] and not task['library']['correct']}
    rows = {task_id: root for task_id, root, _, _ in load_rows()}
    counts = Counter()
    for task_id in sorted(failed):
        defs = [node for node in rows[task_id].body if isinstance(node, ast.FunctionDef)]
        if len(defs) != 1:
            continue
        fn = defs[0]
        nodes = list(ast.walk(fn))
        counts['failed_unique'] += 1
        counts['has_for_or_while'] += any(isinstance(node, (ast.For, ast.While)) for node in nodes)
        counts['has_if'] += any(isinstance(node, (ast.If, ast.IfExp)) for node in nodes)
        counts['has_comprehension'] += any(isinstance(node, (ast.ListComp, ast.DictComp,
                                                            ast.SetComp, ast.GeneratorExp))
                                           for node in nodes)
        counts['has_recursive_call'] += any(isinstance(node, ast.Call) and
                                            isinstance(node.func, ast.Name) and
                                            node.func.id == fn.name for node in nodes)
        counts['has_unsupported_call'] += any(isinstance(node, ast.Call) and
                                              (not isinstance(node.func, ast.Name) or
                                               node.func.id not in {'len', 'sum', 'min', 'max'})
                                              for node in nodes)
        if len(fn.body) == 1 and isinstance(fn.body[0], ast.Return):
            counts['single_return'] += 1
            counts['single_return_compilable'] += compile_fragment(fn.body[0].value, {}) is not None
    if git('rev-parse', 'HEAD:leobot') != h0:
        raise RuntimeError('Motor cambió')
    output = {'kind': 'postgate_diagnostic_only', 'engine_tree': h0,
              'source_result': 'results_v3/g4_typed_library_dev_hashseed0.json',
              'counts': dict(counts),
              'cpu_total_s': round(time.process_time() - cpu, 6),
              'wall_total_s': round(time.monotonic() - wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    (ROOT / 'results_v3' / 'g4_postgate_gap.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()

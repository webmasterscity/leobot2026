"""Development prototype (outside the engine): ARC grids as integer programs.

Question: how many ARC-AGI-1 *training* tasks (visible, development only) does
bottom-up synthesis with observational equivalence solve when each output
cell is an integer expression over (row, col, height, width) plus one generic
substrate operation: index access into the example's input grid?  Output size
is a second expression over the input (height, width).

Substrate: add, sub, mul, floordiv, mod, min, max (the engine's DSL), plus
at(i, j) (input cell, -1 outside), eq (1/0) and if(c, a, b).  No ARC-specific
primitive (no rotation, flip, object, symmetry, tiling).
python3 -m experiments.g39_grid_prototype ARC_ZIP OUT.json [SPLIT] [SECONDS]
"""
from __future__ import annotations

import json
import sys
import time
import zipfile
from pathlib import Path

BIN = ('add', 'sub', 'mul', 'floordiv', 'mod', 'min', 'max', 'eq')
COMM = {'add', 'mul', 'min', 'max', 'eq'}


def op2(op, a, b):
    if op == 'add': return a + b
    if op == 'sub': return a - b
    if op == 'mul': return a * b
    if op == 'floordiv': return a // b if b else None
    if op == 'mod': return a % b if b else None
    if op == 'min': return a if a < b else b
    if op == 'max': return a if a > b else b
    return 1 if a == b else 0


class Search:
    """Bottom-up enumeration by size; one program kept per behaviour."""

    def __init__(self, points, target, grids=None, leaves=(), consts=(), deadline=0.0, max_size=9):
        self.points, self.target, self.grids = points, tuple(target), grids
        self.deadline, self.max_size = deadline, max_size
        self.levels, self.seen, self.solution = {}, set(), None
        for name, k in leaves:
            self.add(name, tuple(p[k] for p in points), 1)
        for c in consts:
            self.add(str(c), tuple(c for _ in points), 1)

    def add(self, expr, sig, size):
        if None in sig or sig in self.seen:
            return
        self.seen.add(sig); self.levels.setdefault(size, []).append((expr, sig))
        if sig == self.target and self.solution is None:
            self.solution = expr

    def at(self, si, sj):
        out = []
        for p, i, j in zip(self.points, si, sj):
            g = self.grids[p[-1]]
            out.append(g[i][j] if 0 <= i < len(g) and 0 <= j < len(g[0]) else -1)
        return tuple(out)

    def run(self):
        for size in range(2, self.max_size + 1):
            if self.solution is not None or time.perf_counter() > self.deadline:
                break
            for ls in range(1, size - 1):
                rs = size - 1 - ls
                for le, lv in self.levels.get(ls, []):
                    if time.perf_counter() > self.deadline:
                        return self.solution
                    for re_, rv in self.levels.get(rs, []):
                        for op in BIN:
                            if op in COMM and ls > rs:
                                continue
                            self.add(f'{op}({le},{re_})', tuple(op2(op, a, b) for a, b in zip(lv, rv)), size)
                        if self.grids is not None:
                            self.add(f'at({le},{re_})', self.at(lv, rv), size)
                        if self.solution is not None:
                            return self.solution
            for cs in range(1, size - 2):
                for ts in range(1, size - 1 - cs):
                    es = size - 1 - cs - ts
                    for ce, cv in self.levels.get(cs, []):
                        if not all(v in (0, 1) for v in cv) or len(set(cv)) < 2:
                            continue
                        if time.perf_counter() > self.deadline:
                            return self.solution
                        for te, tv in self.levels.get(ts, []):
                            for ee, ev in self.levels.get(es, []):
                                self.add(f'if({ce},{te},{ee})', tuple(t if c else e for c, t, e in zip(cv, tv, ev)), size)
                        if self.solution is not None:
                            return self.solution
        return self.solution


def evaluate(expr, env, grid):
    """Evaluate a printed expression (prototype only) on one point."""
    def at(i, j):
        return grid[i][j] if 0 <= i < len(grid) and 0 <= j < len(grid[0]) else -1
    names = {'r': env[0], 'c': env[1], 'h': env[2], 'w': env[3], 'at': at,
             'add': lambda a, b: a + b, 'sub': lambda a, b: a - b, 'mul': lambda a, b: a * b,
             'floordiv': lambda a, b: a // b if b else None, 'mod': lambda a, b: a % b if b else None,
             'min': min, 'max': max, 'eq': lambda a, b: int(a == b), 'if': lambda c, a, b: a if c else b}
    return eval(expr, {'__builtins__': {}}, names)  # prototype-only reader of its own output


def solve(task, seconds):
    pairs = task['train']
    start = time.perf_counter()
    # Output size as integer programs of the input size.
    sizes = [(len(p['input']), len(p['input'][0])) for p in pairs]
    shape = []
    for k in (0, 1):
        target = [len(p['output']) if k == 0 else len(p['output'][0]) for p in pairs]
        s = Search([(h, w) for h, w in sizes], target, leaves=(('h', 0), ('w', 1)), consts=(1, 2, 3),
                   deadline=start + seconds * 0.1, max_size=7)
        expr = s.run()
        if expr is None:
            return None, 'size'
        shape.append(expr)
    points, target, grids = [], [], []
    for n, p in enumerate(pairs):
        grids.append(p['input'])
        h, w = len(p['input']), len(p['input'][0])
        for r, row in enumerate(p['output']):
            for c, v in enumerate(row):
                points.append((r, c, h, w, n)); target.append(v)
    s = Search(points, target, grids=grids, leaves=(('r', 0), ('c', 1), ('h', 2), ('w', 3)),
               consts=tuple(range(10)), deadline=start + seconds, max_size=9)
    cell = s.run()
    if cell is None:
        return None, 'cell'
    preds = []
    for t in task['test']:
        g = t['input']; h, w = len(g), len(g[0])
        ho = evaluate(shape[0], (0, 0, h, w), g)
        wo = evaluate(shape[1], (0, 0, h, w), g)
        if not ho or not wo or ho < 1 or wo < 1 or ho > 30 or wo > 30:
            return None, 'size_test'
        preds.append([[evaluate(cell, (r, c, h, w), g) for c in range(wo)] for r in range(ho)])
    return {'shape': shape, 'cell': cell, 'pred': preds}, 'ok'


def main():
    z = zipfile.ZipFile(sys.argv[1]); out = Path(sys.argv[2])
    split = sys.argv[3] if len(sys.argv) > 3 else 'training'
    seconds = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0
    names = sorted(n for n in z.namelist() if n.endswith('.json') and f'/data/{split}/' in n)
    rows, solved = [], 0
    for name in names:
        task = json.loads(z.read(name))
        t0 = time.process_time()
        res, why = solve(task, seconds)
        ok = bool(res) and all(p == t['output'] for p, t in zip(res['pred'], task['test']))
        solved += ok
        rows.append({'task': Path(name).stem, 'solved': ok, 'stage': why,
                     'program': res and {'shape': res['shape'], 'cell': res['cell']},
                     'cpu_s': round(time.process_time() - t0, 2)})
        if ok:
            print(Path(name).stem, res['cell'], flush=True)
    report = {'split': split, 'tasks': len(names), 'solved': solved, 'seconds_per_task': seconds, 'rows': rows}
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

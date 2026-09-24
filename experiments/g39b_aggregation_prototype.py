"""Development prototype (outside the engine), G-39b exploration: ARC grids with aggregation.

Same search as g39_grid_prototype plus generic aggregation/iteration substrate:
per-grid leaves (most frequent colour, most/least frequent non-zero colour,
number of colours, bounding box of non-zero cells) and per-cell binary ops
nb(i,j) (non-zero 8-neighbours) and comp(i,j) (size of the 4-connected
same-colour component).  Derived from g39_grid_prototype.py.

With --goal, each size first tries at(i, j) as the root by inverting it
(the engine's goal-directed join, extended to index access): a row
expression survives only if every target colour occurs in that input row,
and only column expressions landing on such cells are then checked.

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

GOAL = '--goal' in sys.argv
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

    def cellop(self, fn, si, sj):
        return tuple(fn(self.grids[p[-1]], i, j) for p, i, j in zip(self.points, si, sj))

    def at(self, si, sj):
        out = []
        for p, i, j in zip(self.points, si, sj):
            g = self.grids[p[-1]]
            out.append(g[i][j] if 0 <= i < len(g) and 0 <= j < len(g[0]) else -1)
        return tuple(out)

    def goal_at(self, size):
        """Root at(i, j) by inversion: prune row expressions alone first."""
        if not hasattr(self, 'rowmaps'):
            self.rowmaps = []
            for p, y in zip(self.points, self.target):
                g = self.grids[p[-1]]
                self.rowmaps.append({i: frozenset(j for j, v in enumerate(row) if v == y)
                                     for i, row in enumerate(g) if y in row})
        for ls in range(1, size - 1):
            rs = size - 1 - ls
            rights = self.levels.get(rs, [])
            if not rights:
                continue
            by_first = {}
            for re_, rv in rights:
                by_first.setdefault(rv[0], []).append((re_, rv))
            for le, lv in self.levels.get(ls, []):
                if time.perf_counter() > self.deadline:
                    return
                allowed = []
                for rm, i in zip(self.rowmaps, lv):
                    cols = rm.get(i)
                    if not cols:
                        break
                    allowed.append(cols)
                else:
                    for j0 in allowed[0]:
                        for re_, rv in by_first.get(j0, ()):
                            if all(j in a for j, a in zip(rv, allowed)):
                                self.add(f'at({le},{re_})', self.at(lv, rv), size)
                                return

    def run(self):
        for size in range(2, self.max_size + 1):
            if self.solution is not None or time.perf_counter() > self.deadline:
                break
            if GOAL and self.grids is not None:
                self.goal_at(size)
                if self.solution is not None:
                    return self.solution
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
                            self.add(f'nb({le},{re_})', self.cellop(nb, lv, rv), size)
                            self.add(f'comp({le},{re_})', self.cellop(comp, lv, rv), size)
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
                                self.add(f'ite({ce},{te},{ee})', tuple(t if c else e for c, t, e in zip(cv, tv, ev)), size)
                        if self.solution is not None:
                            return self.solution
        return self.solution


from collections import Counter
from functools import lru_cache


def feats(g):
    cnt = Counter(v for row in g for v in row); nz = {k: n for k, n in cnt.items() if k}
    rows = [r for r, row in enumerate(g) if any(row)]; cols = [c for c in range(len(g[0])) if any(row[c] for row in g)]
    return {'mode': cnt.most_common(1)[0][0],
            'nzmax': max(sorted(nz), key=lambda k: nz[k]) if nz else 0,
            'nzmin': min(sorted(nz), key=lambda k: nz[k]) if nz else 0,
            'ncol': len(nz), 'top': rows[0] if rows else 0, 'left': cols[0] if cols else 0,
            'bh': rows[-1] - rows[0] + 1 if rows else 0, 'bw': cols[-1] - cols[0] + 1 if cols else 0}


FEATS = ('mode', 'nzmax', 'nzmin', 'ncol', 'top', 'left', 'bh', 'bw')


def nb(g, i, j):
    if not (0 <= i < len(g) and 0 <= j < len(g[0])):
        return -1
    return sum(1 for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di or dj)
               and 0 <= i + di < len(g) and 0 <= j + dj < len(g[0]) and g[i + di][j + dj])


_COMP = {}


def comp(g, i, j):
    if not (0 <= i < len(g) and 0 <= j < len(g[0])):
        return -1
    key = id(g)
    if key not in _COMP:
        lab = [[-1] * len(g[0]) for _ in g]; sizes = []
        for a in range(len(g)):
            for b in range(len(g[0])):
                if lab[a][b] < 0:
                    stack, n = [(a, b)], 0; lab[a][b] = len(sizes)
                    while stack:
                        x, y = stack.pop(); n += 1
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            u, v = x + dx, y + dy
                            if 0 <= u < len(g) and 0 <= v < len(g[0]) and lab[u][v] < 0 and g[u][v] == g[x][y]:
                                lab[u][v] = len(sizes); stack.append((u, v))
                    sizes.append(n)
        _COMP[key] = (g, lab, sizes)
    _, lab, sizes = _COMP[key]
    return sizes[lab[i][j]]


def evaluate(expr, env, grid):
    """Evaluate a printed expression (prototype only) on one point."""
    def at(i, j):
        return grid[i][j] if 0 <= i < len(grid) and 0 <= j < len(grid[0]) else -1
    names = {'r': env[0], 'c': env[1], 'h': env[2], 'w': env[3], 'at': at, **feats(grid),
             'nb': lambda i, j: nb(grid, i, j), 'comp': lambda i, j: comp(grid, i, j),
             'add': lambda a, b: a + b, 'sub': lambda a, b: a - b, 'mul': lambda a, b: a * b,
             'floordiv': lambda a, b: a // b if b else None, 'mod': lambda a, b: a % b if b else None,
             'min': min, 'max': max, 'eq': lambda a, b: int(a == b), 'ite': lambda c, a, b: a if c else b}
    return eval(expr, {'__builtins__': {}}, names)  # prototype-only reader of its own output


def solve(task, seconds):
    _COMP.clear()
    pairs = task['train']
    start = time.perf_counter()
    # Output size as integer programs of the input size.
    sizes = [(len(p['input']), len(p['input'][0]), *[feats(p['input'])[f] for f in FEATS]) for p in pairs]
    shape = []
    for k in (0, 1):
        target = [len(p['output']) if k == 0 else len(p['output'][0]) for p in pairs]
        s = Search(sizes, target, leaves=(('h', 0), ('w', 1), *[(f, 2 + n) for n, f in enumerate(FEATS)]), consts=(1, 2, 3),
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
                points.append((r, c, h, w, *[feats(p['input'])[f] for f in FEATS], n)); target.append(v)
    s = Search(points, target, grids=grids, leaves=(('r', 0), ('c', 1), ('h', 2), ('w', 3), *[(f, 4 + n) for n, f in enumerate(FEATS)]),
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
    args = [a for a in sys.argv if a != '--goal']
    split = args[3] if len(args) > 3 else 'training'
    seconds = float(args[4]) if len(args) > 4 else 6.0
    names = sorted(n for n in z.namelist() if n.endswith('.json') and f'/data/{split}/' in n)
    rows, solved = [], 0
    for name in names:
        task = json.loads(z.read(name))
        t0 = time.process_time()
        try:
            res, why = solve(task, seconds)
        except Exception as exc:  # a malformed prediction counts as a failure of that task
            res, why = None, f'error: {type(exc).__name__}'
        ok = bool(res) and all(p == t['output'] for p, t in zip(res['pred'], task['test']))
        solved += ok
        rows.append({'task': Path(name).stem, 'solved': ok, 'stage': why,
                     'program': res and {'shape': res['shape'], 'cell': res['cell']},
                     'cpu_s': round(time.process_time() - t0, 2)})
        if ok:
            print(Path(name).stem, res['cell'], flush=True)
    report = {'goal_at': GOAL, 'split': split, 'tasks': len(names), 'solved': solved, 'seconds_per_task': seconds, 'rows': rows}
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

"""Development prototype (outside the engine), G-40 exploration: objects as views.

An object is a connected set of non-background cells: either of one colour or
of any colours (two generic notions), 8-connected.  A *view* turns the input
grid into another grid: identity, the bounding box of everything drawn, or the
bounding box of the object selected by one generic property (largest,
smallest, topmost, leftmost, the only one with its colours).  Each view is composed with the engine's typed
grid learner (G-39c/G-39d, unchanged): the learner sees view(input) as its
context.  Views that fit the demonstrations but predict differently on the
test mean ambiguity, so the prototype abstains.
python3 -m experiments.g40_objects_prototype ARC_ZIP OUT.json [SECONDS_PER_VIEW]
"""
from __future__ import annotations

import json
import sys
import time
import zipfile
from pathlib import Path

from leobot.programs import ProgramLearner


def objects(grid, same_colour):
    h, w = len(grid), len(grid[0])
    seen, out = set(), []
    for r in range(h):
        for c in range(w):
            if grid[r][c] == 0 or (r, c) in seen:
                continue
            stack, cells = [(r, c)], []
            seen.add((r, c))
            while stack:
                x, y = stack.pop(); cells.append((x, y))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        u, v = x + dx, y + dy
                        if (0 <= u < h and 0 <= v < w and (u, v) not in seen and grid[u][v] != 0
                                and (not same_colour or grid[u][v] == grid[x][y])):
                            seen.add((u, v)); stack.append((u, v))
            out.append(cells)
    return out


def crop(grid, cells):
    rows = [r for r, _ in cells]; cols = [c for _, c in cells]
    return [row[min(cols):max(cols) + 1] for row in grid[min(rows):max(rows) + 1]]


def select(objs, how, grid=None):
    """One object by a generic property; None when the choice is not unique."""
    if not objs:
        return None
    if how == 'unico':
        # The only object whose colour set appears in no other object.
        sets = [frozenset(grid[r][c] for r, c in o) for o in objs]
        alone = [o for o, s in zip(objs, sets) if sets.count(s) == 1]
        return alone[0] if len(alone) == 1 else None
    key = {'mayor': lambda o: -len(o), 'menor': lambda o: len(o),
           'arriba': lambda o: min(r for r, _ in o), 'izquierda': lambda o: min(c for _, c in o)}[how]
    ranked = sorted(objs, key=key)
    if len(ranked) > 1 and key(ranked[0]) == key(ranked[1]):
        return None
    return ranked[0]


def view(grid, name):
    if name == 'identidad':
        return grid
    cells = [(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v]
    if name == 'dibujo':
        return crop(grid, cells) if cells else None
    notion, how = name.split(':')
    obj = select(objects(grid, notion == 'color'), how, grid)
    return crop(grid, obj) if obj else None


VIEWS = ['identidad', 'dibujo'] + [f'{n}:{h}' for n in ('color', 'mixto')
                                   for h in ('mayor', 'menor', 'arriba', 'izquierda', 'unico')]


def solve(task, seconds):
    answers, fitted = {}, []
    for name in VIEWS:
        pairs = [(view(p['input'], name), p['output']) for p in task['train']]
        tests = [view(t['input'], name) for t in task['test']]
        if any(a is None for a, _ in pairs) or any(g is None for g in tests):
            continue
        pl = ProgramLearner(max_seconds=seconds)
        for a, b in pairs:
            pl.add_grid_example('v', a, b)
        if pl.fit_grid('v', tests).get('status') != 'learned_hypothesis':
            continue
        preds = [pl.predict_grid('v', g) for g in tests]
        fitted.append(name)
        if all(p['status'] == 'hypothesis' for p in preds):
            answers[name] = [p['grid'] for p in preds]
    distinct = {json.dumps(a) for a in answers.values()}
    if len(distinct) == 1:
        return next(iter(answers.values())), sorted(answers), fitted
    return None, sorted(answers), fitted


def main():
    z = zipfile.ZipFile(sys.argv[1]); out = Path(sys.argv[2])
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    names = sorted(n for n in z.namelist() if n.endswith('.json') and '/data/training/' in n)
    rows = []
    for name in names:
        task = json.loads(z.read(name)); t0 = time.process_time()
        pred, views, fitted = solve(task, seconds)
        ok = pred is not None and all(p == t['output'] for p, t in zip(pred, task['test']))
        rows.append({'task': Path(name).stem, 'answered': pred is not None, 'correct': ok,
                     'views_answering': views, 'views_fitted': fitted, 'cpu_s': round(time.process_time() - t0, 2)})
        if ok:
            print(Path(name).stem, views, flush=True)
    report = {'split': 'training', 'tasks': len(rows), 'seconds_per_view': seconds,
              'correct': sum(r['correct'] for r in rows), 'answered': sum(r['answered'] for r in rows),
              'wrong': sum(r['answered'] and not r['correct'] for r in rows), 'rows': rows}
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

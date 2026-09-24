"""G-40-0: ARC compute curve on 100 training tasks (diagnostic, frozen engine).

See prereg/G-40-0-curva-de-computo-arc.md.
python3 -m experiments.g40_0_compute_curve ARC1_ZIP OUT.json
"""
from __future__ import annotations

import json
import os
import random
import resource
import sys
import time
from pathlib import Path

from experiments.g39_arc_grids import git, load

BUDGETS = {'x1': dict(max_seconds=6.0, max_candidates=120_000, max_signature_cells=10_000_000),
           'x5': dict(max_seconds=30.0, max_candidates=600_000, max_signature_cells=50_000_000)}


def run(task, budget):
    from leobot.programs import ProgramLearner
    pl = ProgramLearner(**budget)
    for p in task['train']:
        pl.add_grid_example('tarea', p['input'], p['output'])
    t0 = time.process_time()
    rep = pl.fit_grid('tarea', [t['input'] for t in task['test']])
    preds = [pl.predict_grid('tarea', t['input']) for t in task['test']]
    answered = all(p['status'] == 'hypothesis' for p in preds)
    return {'answered': answered, 'correct': answered and all(p['grid'] == t['output'] for p, t in zip(preds, task['test'])),
            'stage': rep.get('stage'), 'status': rep.get('status'), 'cpu_s': round(time.process_time() - t0, 2),
            'reason': rep.get('celda', {}).get('reason')}


def main():
    tasks = load(sys.argv[1], 'training')
    names = sorted(random.Random(4040).sample(sorted(tasks), 100))
    rows = []
    for name in names:
        rows.append({'task': name, **{k: run(tasks[name], b) for k, b in BUDGETS.items()}})
    summary = {k: {'correct': sum(r[k]['correct'] for r in rows), 'answered': sum(r[k]['answered'] for r in rows),
                   'cpu_s_total': round(sum(r[k]['cpu_s'] for r in rows), 1)} for k in BUDGETS}
    report = {'engine_tree': git('rev-parse', 'HEAD:leobot'), 'hashseed': os.environ.get('PYTHONHASHSEED'),
              'budgets': BUDGETS, 'summary': summary,
              'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1), 'rows': rows}
    Path(sys.argv[2]).write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

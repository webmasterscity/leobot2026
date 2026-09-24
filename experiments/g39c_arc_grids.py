"""G-39c: ARC-AGI-1 grids with colours as symbols (typed DSL).

See prereg/G-39c-colores-como-simbolos.md.
python3 -m experiments.g39c_arc_grids ARC1_ZIP OUT.json dev|reserve [WORKERS] [--treatment-only]

Reuses the G-39 evaluator (same data, tasks and controls) and adds two
ablations with the same budget: flat search (no inversion) and inversion
without the aggregation substrate.
"""
from __future__ import annotations

import json
import os
import random
import resource
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from experiments.g39_arc_grids import COMMIT, SECONDS, attempt, git, load, recolor

TREATMENT_ONLY = '--treatment-only' in sys.argv


def run_task(item):
    name, task, shuffled_task = item
    from leobot.programs import ProgramLearner
    out = {'task': name}
    pl, out['treatment'] = attempt(task)
    if not TREATMENT_ONLY:
        again = ProgramLearner.from_dict(json.loads(json.dumps(pl.as_dict())))
        out['restart_identical'] = all(again.predict_grid('tarea', t['input']) == pl.predict_grid('tarea', t['input'])
                                       for t in task['test'])
        out['fresh_answers'] = ProgramLearner().predict_grid('tarea', task['test'][0]['input'])['status'] == 'hypothesis'
        out['ablation_no_at'] = attempt(task, use_context=False)[1]
        out['no_test_probes'] = attempt(task, use_test_probes=False)[1]
        out['no_goal'] = attempt(task, use_goal=False)[1]
        out['no_aggregation'] = attempt(task, use_aggregation=False)[1]
        out['no_types'] = attempt(task, use_types=False)[1]
        out['shuffled_pairs'] = attempt(shuffled_task)[1]
        perm = [0] + random.Random(name).sample(range(1, 10), 9)
        renamed = {'train': [{'input': recolor(p['input'], perm), 'output': recolor(p['output'], perm)} for p in task['train']],
                   'test': [{'input': recolor(t['input'], perm), 'output': recolor(t['output'], perm)} for t in task['test']]}
        out['renamed_colors'] = attempt(renamed)[1]
    out['rss_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return out


def main():
    args = [a for a in sys.argv if a != '--treatment-only']
    zip_path, out_path, mode = args[1], Path(args[2]), args[3]
    workers = int(args[4]) if len(args) > 4 else 2
    tree = git('rev-parse', 'HEAD:leobot')
    if mode == 'dev':
        tasks = load(zip_path, 'training'); seed = None
    else:
        frozen = git('rev-parse', 'freeze-G-39c:leobot')
        if frozen != tree or git('status', '--porcelain', '--', 'leobot'):
            raise RuntimeError('El motor no es el congelado.')
        seed = int(frozen[:8], 16)
        pool = load(zip_path, 'evaluation')
        tasks = {k: pool[k] for k in sorted(random.Random(seed).sample(sorted(pool), 200))}
    names = sorted(tasks)
    items = []
    for i, n in enumerate(names):
        other = tasks[names[(i + 1) % len(names)]]
        shuffled = {'train': [{'input': p['input'], 'output': q['output']}
                              for p, q in zip(tasks[n]['train'], other['train'])], 'test': tasks[n]['test']}
        items.append((n, tasks[n], shuffled))
    started = time.time()
    with Pool(workers) as pool:
        rows = pool.map(run_task, items, chunksize=1)

    def tally(key):
        rs = [r[key] for r in rows]
        return {'correct': sum(r['correct'] for r in rs), 'answered': sum(r['answered'] for r in rs),
                'wrong': sum(r['answered'] and not r['correct'] for r in rs)}
    treat = tally('treatment')
    report = {'mode': mode, 'engine_tree': tree, 'seed': seed, 'tasks': len(rows), 'arc_commit': COMMIT,
              'hashseed': os.environ.get('PYTHONHASHSEED'), 'seconds_per_fit': SECONDS, 'workers': workers,
              'treatment_only': TREATMENT_ONLY, 'treatment': treat,
              'precision': round(treat['correct'] / treat['answered'], 3) if treat['answered'] else None,
              'learn_cpu_s_max': max(r['treatment']['learn_cpu_s'] for r in rows),
              'predict_ms_p95': sorted(r['treatment']['predict_ms'] for r in rows)[int(0.95 * len(rows))],
              'rss_mib_max': max(r['rss_mib'] for r in rows), 'wall_s': round(time.time() - started, 1)}
    if not TREATMENT_ONLY:
        report.update({k: tally(k) for k in ('ablation_no_at', 'no_test_probes', 'no_goal', 'no_aggregation', 'no_types',
                                              'shuffled_pairs', 'renamed_colors')})
        report.update(restart_identical=all(r['restart_identical'] for r in rows),
                      fresh_answers=sum(r['fresh_answers'] for r in rows))
    report['rows'] = rows
    out_path.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

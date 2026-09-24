"""G-39: ARC-AGI-1 grids learned with the engine's program synthesis.

See prereg/G-39-cuadriculas-como-programas-con-acceso-por-indice.md.
python3 -m experiments.g39_arc_grids ARC1_ZIP OUT.json dev|reserve [WORKERS]

dev: the 400 visible ``training`` tasks.  reserve: 200 ``evaluation`` tasks
drawn with the seed from the first 8 hex digits of freeze-G-39:leobot.
Each task gets fresh learners; workers only parallelize independent tasks.
"""
from __future__ import annotations

import json
import os
import random
import resource
import subprocess
import sys
import time
import zipfile
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '399030444e0ab0cc8b4e199870fb20b863846f34'
SECONDS = 6.0


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def load(zip_path, split):
    z = zipfile.ZipFile(zip_path)
    names = sorted(n for n in z.namelist() if n.endswith('.json') and f'-{COMMIT}/data/{split}/' in n)
    return {Path(n).stem: json.loads(z.read(n)) for n in names}


def recolor(grid, perm):
    return [[perm[v] for v in row] for row in grid]


def attempt(task, **switches):
    from leobot.programs import ProgramLearner
    pl = ProgramLearner(max_seconds=SECONDS)
    for p in task['train']:
        pl.add_grid_example('tarea', p['input'], p['output'])
    tests = [t['input'] for t in task['test']]
    t0 = time.process_time()
    rep = pl.fit_grid('tarea', tests, **switches)
    learn_cpu = time.process_time() - t0
    preds, lat = [], []
    for g in tests:
        t1 = time.perf_counter(); preds.append(pl.predict_grid('tarea', g)); lat.append((time.perf_counter() - t1) * 1000)
    answered = all(p['status'] == 'hypothesis' for p in preds)
    correct = answered and all(p['grid'] == t['output'] for p, t in zip(preds, task['test']))
    cell = rep.get('celda', {})
    return pl, {'answered': answered, 'correct': correct, 'status': rep.get('status'), 'stage': rep.get('stage'),
                'predict_status': [p['status'] for p in preds], 'programs': cell.get('programs', [])[:3],
                'candidates': cell.get('candidates'), 'learn_cpu_s': round(learn_cpu, 3),
                'predict_ms': round(max(lat), 3)}


def run_task(item):
    name, task, shuffled_task = item
    from leobot.programs import ProgramLearner
    out = {'task': name}
    pl, out['treatment'] = attempt(task)
    again = ProgramLearner.from_dict(json.loads(json.dumps(pl.as_dict())))
    out['restart_identical'] = all(again.predict_grid('tarea', t['input']) == pl.predict_grid('tarea', t['input'])
                                   for t in task['test'])
    out['fresh_answers'] = ProgramLearner().predict_grid('tarea', task['test'][0]['input'])['status'] == 'hypothesis'
    out['ablation_no_at'] = attempt(task, use_context=False)[1]
    out['no_test_probes'] = attempt(task, use_test_probes=False)[1]
    out['shuffled_pairs'] = attempt(shuffled_task)[1]
    perm = [0] + random.Random(name).sample(range(1, 10), 9)
    renamed = {'train': [{'input': recolor(p['input'], perm), 'output': recolor(p['output'], perm)} for p in task['train']],
               'test': [{'input': recolor(t['input'], perm), 'output': recolor(t['output'], perm)} for t in task['test']]}
    out['renamed_colors'] = attempt(renamed)[1]
    out['rss_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return out


def main():
    zip_path, out_path, mode = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    tree = git('rev-parse', 'HEAD:leobot')
    if mode == 'dev':
        tasks = load(zip_path, 'training'); seed = None
    else:
        frozen = git('rev-parse', 'freeze-G-39:leobot')
        if frozen != tree or git('status', '--porcelain', '--', 'leobot'):
            raise RuntimeError('El motor no es el congelado.')
        seed = int(frozen[:8], 16)
        pool = load(zip_path, 'evaluation')
        tasks = {k: pool[k] for k in sorted(random.Random(seed).sample(sorted(pool), 200))}
    names = sorted(tasks)
    # Shuffled pairs: each task's demonstration outputs come from the next task.
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
              'treatment': treat,
              'precision': round(treat['correct'] / treat['answered'], 3) if treat['answered'] else None,
              'ablation_no_at': tally('ablation_no_at'), 'no_test_probes': tally('no_test_probes'),
              'shuffled_pairs': tally('shuffled_pairs'), 'renamed_colors': tally('renamed_colors'),
              'restart_identical': all(r['restart_identical'] for r in rows),
              'fresh_answers': sum(r['fresh_answers'] for r in rows),
              'learn_cpu_s_max': max(r['treatment']['learn_cpu_s'] for r in rows),
              'predict_ms_p95': sorted(r['treatment']['predict_ms'] for r in rows)[int(0.95 * len(rows))],
              'rss_mib_max': max(r['rss_mib'] for r in rows), 'wall_s': round(time.time() - started, 1),
              'rows': rows}
    out_path.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

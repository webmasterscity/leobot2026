"""G-40: objects as views, on never-used ARC tasks.

See prereg/G-40-objetos-como-vistas.md.
python3 -m experiments.g40_arc_views ARC1_ZIP ARC2_ZIP OUT.json dev|reserve

dev: ARC-AGI-1 `training` (visible), treatment only.  reserve: 150 tasks drawn
with the freeze-G-40 seed from the 395 never-used tasks (48 free ARC-AGI-1
evaluation, 114 ARC-AGI-2 evaluation and 233 ARC-AGI-2 training tasks that are
not in ARC-AGI-1), with the controls.  One process, as agreed with the user.
"""
from __future__ import annotations

import json
import random
import resource
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARC1 = '399030444e0ab0cc8b4e199870fb20b863846f34'
ARC2 = 'f3283f727488ad98fe575ea6a5ac981e4a188e49'
SECONDS_PER_VIEW = 2.0


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def load(path, commit, split):
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if n.endswith('.json') and f'-{commit}/data/{split}/' in n]
    return {Path(n).stem: json.loads(z.read(n)) for n in names}


def recolor(grid, perm):
    return [[perm[v] for v in row] for row in grid]


def attempt(task, views=None):
    from leobot.programs import GRID_VIEWS, ProgramLearner
    pl = ProgramLearner()
    for p in task['train']:
        pl.add_grid_example('tarea', p['input'], p['output'])
    tests = [t['input'] for t in task['test']]
    t0 = time.process_time()
    rep = pl.fit_grid_views('tarea', tests, views=views or GRID_VIEWS, seconds_per_view=SECONDS_PER_VIEW)
    cpu = time.process_time() - t0
    preds, lat = [], []
    for g in tests:
        t1 = time.perf_counter(); preds.append(pl.predict_grid_views('tarea', g)); lat.append((time.perf_counter() - t1) * 1000)
    answered = all(p['status'] == 'hypothesis' for p in preds)
    correct = answered and all(p['grid'] == t['output'] for p, t in zip(preds, task['test']))
    return pl, {'answered': answered, 'correct': correct, 'views': rep.get('views', []),
                'status': [p['status'] for p in preds], 'learn_cpu_s': round(cpu, 2), 'predict_ms': round(max(lat), 3)}


def main():
    arc1, arc2, out, mode = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
    tree = git('rev-parse', 'HEAD:leobot')
    if mode == 'dev':
        tasks = {f'arc1-training/{k}': v for k, v in load(arc1, ARC1, 'training').items()}; seed = None
    else:
        frozen = git('rev-parse', 'freeze-G-40:leobot')
        if frozen != tree or git('status', '--porcelain', '--', 'leobot'):
            raise RuntimeError('El motor no es el congelado.')
        a1t, a1e = load(arc1, ARC1, 'training'), load(arc1, ARC1, 'evaluation')
        a2t, a2e = load(arc2, ARC2, 'training'), load(arc2, ARC2, 'evaluation')
        used = set(json.loads((ROOT / 'results_v3/arc1_evaluation_used_tasks.json').read_text()))
        seen1 = set(a1t) | set(a1e)
        pool = {**{f'arc1-evaluation/{k}': v for k, v in a1e.items() if k not in used},
                **{f'arc2-evaluation/{k}': v for k, v in a2e.items() if k not in seen1},
                **{f'arc2-training/{k}': v for k, v in a2t.items() if k not in seen1}}
        seed = int(frozen[:8], 16)
        tasks = {k: pool[k] for k in sorted(random.Random(seed).sample(sorted(pool), 150))}
    names = sorted(tasks)
    rows, started = [], time.time()
    from leobot.programs import ProgramLearner
    for i, name in enumerate(names):
        task = tasks[name]
        row = {'task': name}
        pl, row['treatment'] = attempt(task)
        if mode != 'dev':
            again = ProgramLearner.from_dict(json.loads(json.dumps(pl.as_dict())))
            row['restart_identical'] = all(again.predict_grid_views('tarea', t['input']) == pl.predict_grid_views('tarea', t['input'])
                                           for t in task['test'])
            row['fresh_answers'] = ProgramLearner().predict_grid_views('tarea', task['test'][0]['input'])['status'] == 'hypothesis'
            row['identity_only'] = attempt(task, views=('identidad',))[1]
            other = tasks[names[(i + 1) % len(names)]]
            row['shuffled_pairs'] = attempt({'train': [{'input': p['input'], 'output': q['output']}
                                                       for p, q in zip(task['train'], other['train'])],
                                             'test': task['test']})[1]
            perm = [0] + random.Random(name).sample(range(1, 10), 9)
            row['renamed_colors'] = attempt({'train': [{'input': recolor(p['input'], perm), 'output': recolor(p['output'], perm)}
                                                       for p in task['train']],
                                             'test': [{'input': recolor(t['input'], perm), 'output': recolor(t['output'], perm)}
                                                      for t in task['test']]})[1]
        rows.append(row)

    def tally(key, subset=None):
        rs = [r[key] for r in rows if subset is None or r['task'].startswith(subset)]
        return {'correct': sum(r['correct'] for r in rs), 'answered': sum(r['answered'] for r in rs),
                'wrong': sum(r['answered'] and not r['correct'] for r in rs), 'tasks': len(rs)}
    report = {'mode': mode, 'engine_tree': tree, 'seed': seed, 'tasks': len(rows), 'arc1': ARC1, 'arc2': ARC2,
              'seconds_per_view': SECONDS_PER_VIEW, 'treatment': tally('treatment'),
              'by_origin': {o: tally('treatment', o) for o in sorted({r['task'].split('/')[0] for r in rows})},
              'learn_cpu_s_max': max(r['treatment']['learn_cpu_s'] for r in rows),
              'predict_ms_p95': sorted(r['treatment']['predict_ms'] for r in rows)[int(0.95 * len(rows))],
              'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
              'wall_s': round(time.time() - started, 1)}
    t = report['treatment']
    report['precision'] = round(t['correct'] / t['answered'], 3) if t['answered'] else None
    if mode != 'dev':
        report.update({k: tally(k) for k in ('identity_only', 'shuffled_pairs', 'renamed_colors')})
        report.update(restart_identical=all(r['restart_identical'] for r in rows),
                      fresh_answers=sum(r['fresh_answers'] for r in rows))
    report['rows'] = rows
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()

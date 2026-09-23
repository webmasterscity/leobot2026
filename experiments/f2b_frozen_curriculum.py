"""F-2b: nested 256/512-example curricula with an unchanged engine tree."""
from __future__ import annotations

import json
import random
import resource
import subprocess
import tempfile
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.f2_sequence_composition import (
    ROOT, download, curriculum, teach, evaluate, rename, counterevidence)


TAG = 'freeze-F-2b'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if tree != git('rev-parse', 'freeze-F-2:leobot'):
        raise RuntimeError('El motor F-2b difiere de F-2')
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('El tag F-2b cambió')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor de trabajo cambió')


def expanded(rows, base):
    groups = defaultdict(list)
    for source in rows:
        groups[len(source.split())].append(source)
    base_set = set(base)
    rng = random.Random(1642)
    for length in range(4, 10):
        rng.sample(sorted(groups[length]), 32 if length < 6 else 31)
    extra = []
    for length in range(4, 10):
        pool = sorted(set(groups[length]) - base_set)
        extra.extend(rng.sample(pool, 42 if length < 6 else 43))
    out = sorted(base_set | set(extra), key=lambda source: (len(source.split()), source))
    if len(out) != 512 or not base_set <= set(out):
        raise RuntimeError('Currículo ampliado inválido')
    return out


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    frozen(tree)
    cpu_start, wall_start = time.process_time(), time.monotonic()
    train, train_bytes = download('train')
    test, test_bytes = download('test')
    base = curriculum(train)
    broad = expanded(train, base)
    prior_f1 = json.loads((ROOT / 'results_v3' / 'f1_external_freeze_gate.json').read_text())
    prior_f2 = json.loads((ROOT / 'results_v3' / 'f2_sequence_freeze.json').read_text())
    used = {row['id'] for row in prior_f1['family_results']['scan']['rows']}
    used.update(row['id'] for row in prior_f2['treatment']['rows'])
    available = [source for source in sorted(test)
                 if sha256(source.encode()).hexdigest()[:12] not in used]
    seed = int(sha256((tree + ':F-2b').encode()).hexdigest()[:8], 16)
    held = random.Random(seed).sample(available, 32)
    rows = {**train, **test}
    arms = {}
    for name, selected, composition in (('base', base, True),
                                         ('expanded', broad, True),
                                         ('memory_only', broad, False)):
        bot, report, observe_cpu, consolidate_cpu = teach(rows, selected,
                                                          composition=composition)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f'{name}.json'
            tick = time.process_time()
            bot.save(path)
            reloaded = Bot.load(path)
            restart_cpu = time.process_time() - tick
            scores = evaluate(reloaded, rows, held)
            stable = [(x['status'], x['correct']) for x in scores['rows']] == [
                (x['status'], x['correct']) for x in evaluate(bot, rows, held)['rows']]
        arms[name] = {'report': report, 'scores': scores,
                      'observe_cpu_s': round(observe_cpu, 6),
                      'consolidate_cpu_s': round(consolidate_cpu, 6),
                      'restart_cpu_s': round(restart_cpu, 6),
                      'restart_same': stable, 'examples': len(selected)}
        if time.process_time() - cpu_start > 85 or time.monotonic() - wall_start > 110:
            raise RuntimeError('Presupuesto F-2b agotado')
        if name == 'expanded':
            expanded_bot = bot
    fresh = evaluate(Bot(), rows, held)
    renamed_rows, renamed_taught, renamed_held = rename(rows, broad, held, tree)
    renamed_bot, renamed_report, rename_observe, rename_consolidate = teach(
        renamed_rows, renamed_taught)
    renamed = evaluate(renamed_bot, renamed_rows, renamed_held)
    correction = counterevidence(expanded_bot, rows, held, arms['expanded']['scores'])
    frozen(tree)
    a = arms['base']; b = arms['expanded']
    a_cost = (a['observe_cpu_s'] + a['consolidate_cpu_s'] + a['restart_cpu_s']
              + a['scores']['load_cpu_s'] + a['scores']['cpu_s'])
    b_cost = (b['observe_cpu_s'] + b['consolidate_cpu_s'] + b['restart_cpu_s']
              + b['scores']['load_cpu_s'] + b['scores']['cpu_s'])
    signal = (b['scores']['correct'] >= 12 and
              b['scores']['correct'] - a['scores']['correct'] >= 4)
    promoted = (signal and b['scores']['correct'] >= 15 and
                b_cost / b['scores']['correct'] <= a_cost / max(1, a['scores']['correct']) and
                b['scores']['correct'] > max(arms['memory_only']['scores']['correct'],
                                            fresh['correct']) and
                renamed['correct'] == b['scores']['correct'] and
                b['restart_same'] and correction.get('applied') and
                correction.get('previous_prediction_withdrawn') and
                b['scores']['latency']['p95_ms'] <= 10)
    output = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
              'preregistration': 'prereg/F-2b-curva-educacion-congelada.md',
              'source_bytes': train_bytes + test_bytes,
              'test_examples': len(held), 'arms': arms,
              'fresh': {key: value for key, value in fresh.items() if key != 'rows'},
              'renamed': {key: value for key, value in renamed.items() if key != 'rows'},
              'renamed_report': renamed_report,
              'rename_observe_cpu_s': round(rename_observe, 6),
              'rename_consolidate_cpu_s': round(rename_consolidate, 6),
              'counterevidence': correction,
              'cpu_per_correct_s': {'base': round(a_cost / max(1, a['scores']['correct']), 6),
                                    'expanded': round(b_cost / max(1, b['scores']['correct']), 6)},
              'more_education_signal': signal, 'promotion_gate': bool(promoted),
              'cpu_total_s': round(time.process_time() - cpu_start, 6),
              'wall_total_s': round(time.monotonic() - wall_start, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3' / 'f2b_frozen_curriculum.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    summary = {key: value for key, value in output.items() if key != 'arms'}
    summary['arms'] = {name: {'examples': row['examples'], 'report': row['report'],
                               'correct': row['scores']['correct'],
                               'latency': row['scores']['latency'],
                               'restart_same': row['restart_same'],
                               'observe_cpu_s': row['observe_cpu_s'],
                               'consolidate_cpu_s': row['consolidate_cpu_s']}
                       for name, row in arms.items()}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    run()

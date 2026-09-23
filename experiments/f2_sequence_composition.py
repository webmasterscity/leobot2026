"""F-2: frozen pair teaching and structural sequence generalization on SCAN."""
from __future__ import annotations

import argparse
import json
import random
import resource
import statistics
import subprocess
import tempfile
import time
import urllib.request
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.f1_external_freeze_gate import SCAN_COMMIT, SCAN_SHAS, ROOT


TAG = 'freeze-F-2'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('Tag de motor cambiado')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor de trabajo modificado')


def download(split):
    url = (f'https://raw.githubusercontent.com/brendenlake/SCAN/{SCAN_COMMIT}'
           f'/add_prim_split/tasks_{split}_addprim_jump.txt')
    with urllib.request.urlopen(url, timeout=20) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024 or sha256(data).hexdigest() != SCAN_SHAS[split]:
        raise RuntimeError('Fuente SCAN alterada')
    rows = {}
    for line in data.decode('utf8').splitlines():
        if not line.startswith('IN: ') or ' OUT: ' not in line:
            raise RuntimeError('Formato SCAN alterado')
        source, target = line[4:].split(' OUT: ', 1)
        rows[source] = target
    return rows, len(data)


def curriculum(rows):
    groups = defaultdict(list)
    for source in rows:
        groups[len(source.split())].append(source)
    selected = [source for source in rows if len(source.split()) <= 3]
    if len(selected) != 68:
        raise RuntimeError('La partición corta cambió')
    rng = random.Random(1642)
    for length in range(4, 10):
        selected.extend(rng.sample(sorted(groups[length]), 32 if length < 6 else 31))
    return sorted(selected, key=lambda text: (len(text.split()), text))


def teach(rows, selected, *, composition=True):
    bot = Bot()
    bot.sequence_learner.enable_composition = composition
    started = time.process_time()
    for source in selected:
        bot.observe_sequence_example(source, rows[source])
    observe_cpu = time.process_time() - started
    started = time.process_time()
    report = bot.consolidate_sequence_learning()
    consolidate_cpu = time.process_time() - started
    return bot, report, observe_cpu, consolidate_cpu


def p50_p95(values):
    ms = sorted(value * 1000 for value in values)
    return {'p50_ms': round(statistics.median(ms), 5),
            'p95_ms': round(ms[(95 * len(ms) + 99) // 100 - 1], 5),
            'max_ms': round(ms[-1], 5)}


def evaluate(bot, rows, selected):
    outcomes = []; wall = []; total_cpu = load_cpu = 0.0
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'snapshot.json'
        bot.save(path)
        for source in selected:
            loaded_at = time.process_time()
            isolated = Bot.load(path)
            load_cpu += time.process_time() - loaded_at
            cpu_start, wall_start = time.process_time(), time.perf_counter()
            answer = isolated.respond(source)
            total_cpu += time.process_time() - cpu_start
            wall.append(time.perf_counter() - wall_start)
            outcomes.append({'id': sha256(source.encode()).hexdigest()[:12],
                             'correct': answer.get('text', '') == rows[source],
                             'status': answer.get('status'),
                             'dependencies': answer.get('dependencies', []),
                             'rules_used': answer.get('rules_used', []),
                             'states': answer.get('states')})
    return {'correct': sum(row['correct'] for row in outcomes),
            'statuses': {name: sum(row['status'] == name for row in outcomes)
                         for name in sorted({row['status'] for row in outcomes})},
            'cpu_s': round(total_cpu, 6), 'load_cpu_s': round(load_cpu, 6),
            'latency': p50_p95(wall),
            'rows': outcomes}


def rename(rows, taught, held, tree):
    symbols = sorted({symbol for source in taught for symbol in source.split()}
                     | {symbol for source in taught for symbol in rows[source].split()})
    rng = random.Random(int(sha256((tree + ':F-2:rename').encode()).hexdigest()[:8], 16))
    opaque = [f'z{index:04d}' for index in range(len(symbols))]
    rng.shuffle(opaque)
    mapping = dict(zip(symbols, opaque))
    if any(symbol not in mapping for source in held for symbol in source.split()):
        raise RuntimeError('Un símbolo de prueba no apareció en enseñanza')
    renamed = {' '.join(mapping[word] for word in source.split()):
               ' '.join(mapping[word] for word in rows[source].split())
               for source in [*taught, *held]}
    return renamed, [' '.join(mapping[word] for word in source.split()) for source in taught], [
        ' '.join(mapping[word] for word in source.split()) for source in held]


def counterevidence(bot, rows, held, original):
    before_rules = len(bot.sequence_learner.rules)
    supported = [row for row in original['rows'] if row['status'] == 'sequence_program']
    for rule in bot.sequence_learner.rules:
        if rule['kind'] != 'binary':
            continue
        relevant = [row for row in supported if rule['id'] in row['rules_used']]
        if not relevant:
            continue
        for source in sorted(set(relevant[0]['dependencies']) & set(rule['dependencies'])):
            output = rows[source].split()
            if len(output) < 2 or output == list(reversed(output)):
                continue
            bot.observe_sequence_example(source, list(reversed(output)))
            report = bot.consolidate_sequence_learning()
            after = evaluate(bot, rows, held)
            affected = [i for i, row in enumerate(original['rows'])
                        if rule['id'] in row['rules_used']]
            return {'applied': True, 'source_hash': sha256(source.encode()).hexdigest()[:12],
                    'rules_before': before_rules, 'rules_after': report['rules'],
                    'correct_before': original['correct'], 'correct_after': after['correct'],
                    'affected_heldout': len(affected),
                    'previous_prediction_withdrawn': bool(affected) and all(
                        rule['id'] not in after['rows'][i]['rules_used'] for i in affected),
                    'conflict_status': bot.predict_sequence(source)['status']}
    return {'applied': False, 'reason': 'no_binary_rule_with_nonpalindromic_evidence'}


def run(dev=False):
    wall_start, cpu_start = time.monotonic(), time.process_time()
    tree = git('rev-parse', 'estable-E-1:leobot') if dev else git('rev-parse', f'{TAG}:leobot')
    if not dev:
        frozen(tree)
    train, train_bytes = download('train')
    taught = curriculum(train)
    if dev:
        pool = sorted(set(train) - set(taught))
        held = random.Random(2117).sample(pool, 32)
        rows = train
        test_bytes = 0
    else:
        test, test_bytes = download('test')
        prior = json.loads((ROOT / 'results_v3' / 'f1_external_freeze_gate.json').read_text())
        used = {row['id'] for row in prior['family_results']['scan']['rows']}
        available = [source for source in sorted(test)
                     if sha256(source.encode()).hexdigest()[:12] not in used]
        rng = random.Random(int(sha256((tree + ':F-2').encode()).hexdigest()[:8], 16))
        held = rng.sample(available, 32)
        rows = {**train, **test}
    treatment, consolidation, observe_cpu, consolidate_cpu = teach(rows, taught)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'sequence.json'
        save_start = time.process_time()
        treatment.save(path)
        loaded = Bot.load(path)
        restart_cpu = time.process_time() - save_start
        result = evaluate(loaded, rows, held)
        repeat = evaluate(treatment, rows, held)
        restart_same = [(row['correct'], row['status']) for row in result['rows']] == [
            (row['correct'], row['status']) for row in repeat['rows']]
    ablated, _, ablation_observe_cpu, ablation_consolidate_cpu = teach(rows, taught,
                                                                      composition=False)
    ablation = evaluate(ablated, rows, held)
    fresh = evaluate(Bot(), rows, held)
    renamed_rows, renamed_taught, renamed_held = rename(rows, taught, held, tree)
    renamed_bot, renamed_report, renamed_observe_cpu, renamed_consolidate_cpu = teach(
        renamed_rows, renamed_taught)
    renamed = evaluate(renamed_bot, renamed_rows, renamed_held)
    correction = counterevidence(treatment, rows, held, repeat)
    if not dev:
        frozen(tree)
    out = {'tag': 'development' if dev else TAG, 'engine_tree': tree,
           'engine_unchanged': not dev,
           'preregistration': 'prereg/F-2-secuencias-composicionales.md',
           'train_examples': len(taught), 'test_examples': len(held),
           'source_bytes': train_bytes + test_bytes,
           'consolidation': consolidation, 'treatment': result,
           'ablation': {key: value for key, value in ablation.items() if key != 'rows'},
           'fresh': {key: value for key, value in fresh.items() if key != 'rows'},
           'renamed': {key: value for key, value in renamed.items() if key != 'rows'},
           'renamed_consolidation': renamed_report,
           'counterevidence': correction, 'restart_same': restart_same,
           'cpu_breakdown_s': {'observe': round(observe_cpu, 6),
                               'consolidate': round(consolidate_cpu, 6),
                               'restart': round(restart_cpu, 6),
                               'ablation_observe': round(ablation_observe_cpu, 6),
                               'ablation_consolidate': round(ablation_consolidate_cpu, 6),
                               'rename_observe': round(renamed_observe_cpu, 6),
                               'rename_consolidate': round(renamed_consolidate_cpu, 6)},
           'cpu_total_s': round(time.process_time() - cpu_start, 6),
           'wall_total_s': round(time.monotonic() - wall_start, 6),
           'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    passed = (result['correct'] >= 8 and result['correct'] - max(ablation['correct'], fresh['correct']) >= 8
              and renamed['correct'] == result['correct'] and restart_same
              and correction.get('applied') and correction.get('previous_prediction_withdrawn')
              and result['latency']['p95_ms'] <= 10)
    out['gate_passed'] = bool(passed)
    path = ROOT / 'results_v3' / ('f2_sequence_dev.json' if dev else 'f2_sequence_freeze.json')
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in out.items() if key != 'treatment'} |
                     {'treatment': {key: value for key, value in result.items() if key != 'rows'}},
                     ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true')
    run(parser.parse_args().dev)

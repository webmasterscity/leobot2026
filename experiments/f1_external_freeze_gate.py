"""F-1: three external families on one frozen Leobot motor, with no semantic adapter."""
from __future__ import annotations

import io
import json
import random
import re
import resource
import statistics
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.agi_board import canonical


ROOT = Path(__file__).resolve().parents[1]
TAG = 'freeze-F-1'
BELEBELE_URL = 'https://dl.fbaipublicfiles.com/belebele/Belebele.zip'
BELEBELE_SHA = 'c645e750e111404806751509b5aa3f808a01e6029cd225d37e966dc694aca9e4'
SCAN_COMMIT = 'c4b756cbc010d75c912f16c42c8f15dc6b7e6c8f'
SCAN_SHAS = {
    'train': 'e3c78485692e028eed4205e1b8b3fd0e785ef2c12d45b5b89204dadf5b239e23',
    'test': '8147ae2651422c701162e174d9d66158daa57858a26b30317ac61797118ac7a5',
}
ARC_COMMIT = 'f3283f727488ad98fe575ea6a5ac981e4a188e49'
ARC_SHA = 'c3f9f6975d8432133419fd0e1677c42289666517af4e6f83d8a291690e14d49f'


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def frozen(tree):
    if git('rev-parse', f'{TAG}:leobot') != tree:
        raise RuntimeError('El tag del motor cambió')
    if git('diff', '--name-only', TAG, '--', 'leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no está congelado')


def seed(tree, family):
    return int(sha256((tree + ':F-1:' + family).encode()).hexdigest()[:8], 16)


def download(url, expected, limit=40 * 1024 * 1024):
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(limit + 1)
    actual = sha256(data).hexdigest()
    if len(data) > limit or actual != expected:
        raise RuntimeError(f'Fuente alterada o excedida: {url}; bytes={len(data)} sha={actual}')
    return data


def timed(action):
    cpu, wall = time.process_time(), time.perf_counter()
    result = action()
    return result, {'cpu_s': time.process_time() - cpu,
                    'wall_s': time.perf_counter() - wall}


def latency(samples):
    ms = sorted(sample * 1000 for sample in samples)
    if not ms:
        return {'p50_ms': None, 'p95_ms': None, 'max_ms': None}
    return {'p50_ms': round(statistics.median(ms), 4),
            'p95_ms': round(ms[max(0, (95 * len(ms) + 99) // 100 - 1)], 4),
            'max_ms': round(ms[-1], 4)}


def assemble_options(row):
    return row['question'] + '\n' + '\n'.join(
        f'{letter}: {row[f"mc_answer{i}"]}' for i, letter in enumerate('ABCD', 1))


def option_chosen(answer, row):
    text = str(answer.get('text', '')).strip()
    if answer.get('status') in ('unrecognized', 'document_processed', 'ambiguous'):
        return None
    letter = canonical(text).upper()
    if letter in 'ABCD' and len(letter) == 1:
        return 'ABCD'.index(letter) + 1
    for i in range(1, 5):
        if canonical(text) == canonical(row[f'mc_answer{i}']):
            return i
    return None


def belebele(tree):
    archive = download(BELEBELE_URL, BELEBELE_SHA)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        lines = zipped.read('Belebele/spa_Latn.jsonl').decode('utf8').splitlines()
    pool = [json.loads(line) for line in lines[1:]]  # first row was exposed during format inspection
    by_passage = {}
    for row in pool:
        passage_key = (row['link'], sha256(row['flores_passage'].encode()).hexdigest())
        by_passage.setdefault(passage_key, row)
    keys = random.Random(seed(tree, 'belebele')).sample(sorted(by_passage), 20)
    rows = [by_passage[key] for key in keys]
    outcomes = []; acquisition_cpu = answer_cpu = 0.0; answer_wall = []
    for index, row in enumerate(rows):
        prompt = assemble_options(row)
        fresh, fresh_t = timed(lambda: Bot().respond(prompt))
        bot = Bot()
        report, ingested = timed(lambda: bot.ingest_document_text(
            row['flores_passage'], source=f'f1:belebele:{index}'))
        answer, answered = timed(lambda: bot.respond(prompt))
        other = Bot()
        other.ingest_document_text(rows[(index + 1) % len(rows)]['flores_passage'],
                                   source='f1:wrong_passage')
        mismatched = other.respond(prompt)
        choice = option_chosen(answer, row)
        outcomes.append({'id': f'{row["link"]}#{row["question_number"]}',
                         'correct': choice == int(row['correct_answer_num']),
                         'choice': choice, 'fresh_choice': option_chosen(fresh, row),
                         'wrong_passage_choice': option_chosen(mismatched, row),
                         'status': answer.get('status'),
                         'facts_added': report['facts_added'],
                         'promotions': report['relations_promoted'],
                         'sentences_too_long': report['sentences_too_long'],
                         'fresh_cpu_s': round(fresh_t['cpu_s'], 6)})
        acquisition_cpu += ingested['cpu_s']; answer_cpu += answered['cpu_s']
        answer_wall.append(answered['wall_s'])
    return {'source_bytes': len(archive), 'cases': len(rows),
            'correct': sum(row['correct'] for row in outcomes),
            'attempted': sum(row['choice'] is not None for row in outcomes),
            'fresh_attempted': sum(row['fresh_choice'] is not None for row in outcomes),
            'wrong_passage_attempted': sum(row['wrong_passage_choice'] is not None for row in outcomes),
            'facts_added': sum(row['facts_added'] for row in outcomes),
            'promotions': sum(row['promotions'] for row in outcomes),
            'sentences_too_long': sum(row['sentences_too_long'] for row in outcomes),
            'acquisition_cpu_s': round(acquisition_cpu, 6),
            'inference_cpu_s': round(answer_cpu, 6),
            'inference_wall': latency(answer_wall), 'rows': outcomes}


def scan_rows(data):
    rows = {}
    for line in data.decode('utf8').splitlines():
        match = re.fullmatch(r'IN: (.*?) OUT: (.*)', line)
        if match is None:
            raise RuntimeError('Formato SCAN inesperado')
        rows[match.group(1)] = match.group(2)
    return rows


def scan(tree):
    texts = {}
    for split, expected in SCAN_SHAS.items():
        url = (f'https://raw.githubusercontent.com/brendenlake/SCAN/{SCAN_COMMIT}'
               f'/add_prim_split/tasks_{split}_addprim_jump.txt')
        texts[split] = download(url, expected)
    train = scan_rows(texts['train']); test = scan_rows(texts['test'])
    rng = random.Random(seed(tree, 'scan'))
    taught = rng.sample(sorted(train), 64); held = rng.sample(sorted(test), 16)
    bot = Bot()
    document = '\n'.join(f'IN: {command} OUT: {train[command]}' for command in taught)
    report, ingested = timed(lambda: bot.ingest_document_text(document, source='f1:scan:curriculum'))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'scan.json'
        bot.save(path)
        restart_ok = Bot.load(path).as_dict() == bot.as_dict()
        outcomes = []; answer_cpu = 0.0; answer_wall = []
        for command in held:
            prompt = 'IN: ' + command
            answer, elapsed = timed(lambda: Bot.load(path).respond(prompt))
            fresh = Bot().respond(prompt)
            exact = canonical(answer.get('text', '')) == canonical(test[command])
            outcomes.append({'id': sha256(command.encode()).hexdigest()[:12],
                             'exact': exact, 'status': answer.get('status'),
                             'fresh_exact': canonical(fresh.get('text', '')) == canonical(test[command]),
                             'memory_exact': command in train and command in taught})
            answer_cpu += elapsed['cpu_s']; answer_wall.append(elapsed['wall_s'])
    return {'train_examples': len(taught), 'test_examples': len(held),
            'source_bytes': sum(map(len, texts.values())),
            'correct': sum(row['exact'] for row in outcomes),
            'fresh_correct': sum(row['fresh_exact'] for row in outcomes),
            'memory_correct': sum(row['memory_exact'] for row in outcomes),
            'facts_added': report['facts_added'], 'promotions': report['relations_promoted'],
            'sentences_too_long': report['sentences_too_long'],
            'restart_ok': restart_ok, 'acquisition_cpu_s': round(ingested['cpu_s'], 6),
            'inference_cpu_s': round(answer_cpu, 6),
            'inference_wall': latency(answer_wall), 'rows': outcomes}


def arc(tree):
    url = f'https://codeload.github.com/arcprize/ARC-AGI-2/zip/{ARC_COMMIT}'
    data = download(url, ARC_SHA)
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        names = sorted(name for name in zipped.namelist()
                       if '/data/training/' in name and name.endswith('.json'))
        selected = random.Random(seed(tree, 'arc')).sample(names, 10)
        tasks = [(Path(name).stem, json.loads(zipped.read(name))) for name in selected]
    outcomes = []; acquisition_cpu = answer_cpu = 0.0; answer_wall = []
    for index, (task_id, task) in enumerate(tasks):
        bot = Bot()
        demonstrations = '\n'.join(json.dumps(pair, separators=(',', ':')) for pair in task['train'])
        report, ingested = timed(lambda: bot.ingest_document_text(
            demonstrations, source=f'f1:arc:{task_id}'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'arc.json'
            bot.save(path)
            restart_ok = Bot.load(path).as_dict() == bot.as_dict()
            pairs = []
            for pair in task['test']:
                query = json.dumps(pair['input'], separators=(',', ':'))
                answer, elapsed = timed(lambda: Bot.load(path).respond(query))
                fresh = Bot().respond(query)
                try:
                    predicted = json.loads(answer.get('text', ''))
                except (ValueError, TypeError):
                    predicted = None
                try:
                    fresh_predicted = json.loads(fresh.get('text', ''))
                except (ValueError, TypeError):
                    fresh_predicted = None
                pairs.append({'exact': predicted == pair['output'],
                              'fresh_exact': fresh_predicted == pair['output'],
                              'fresh_status': fresh.get('status'),
                              'status': answer.get('status'),
                              'memory_exact': any(example['input'] == pair['input']
                                                  and example['output'] == pair['output']
                                                  for example in task['train'])})
                answer_cpu += elapsed['cpu_s']; answer_wall.append(elapsed['wall_s'])
        outcomes.append({'task_id': task_id, 'test_pairs': len(pairs),
                         'solved': all(pair['exact'] for pair in pairs),
                         'fresh_solved': all(pair['fresh_exact'] for pair in pairs),
                         'memory_solved': all(pair['memory_exact'] for pair in pairs),
                         'facts_added': report['facts_added'],
                         'promotions': report['relations_promoted'],
                         'sentences_too_long': report['sentences_too_long'],
                         'restart_ok': restart_ok,
                         'statuses': [pair['status'] for pair in pairs]})
        acquisition_cpu += ingested['cpu_s']
    return {'source_bytes': len(data), 'tasks': len(outcomes),
            'correct': sum(row['solved'] for row in outcomes),
            'fresh_correct': sum(row['fresh_solved'] for row in outcomes),
            'memory_correct': sum(row['memory_solved'] for row in outcomes),
            'facts_added': sum(row['facts_added'] for row in outcomes),
            'promotions': sum(row['promotions'] for row in outcomes),
            'sentences_too_long': sum(row['sentences_too_long'] for row in outcomes),
            'restart_ok': all(row['restart_ok'] for row in outcomes),
            'acquisition_cpu_s': round(acquisition_cpu, 6),
            'inference_cpu_s': round(answer_cpu, 6),
            'inference_wall': latency(answer_wall), 'rows': outcomes}


def run():
    tree = git('rev-parse', f'{TAG}:leobot')
    frozen(tree)
    start_cpu, start_wall = time.process_time(), time.monotonic()
    families = {}
    for name, evaluator in (('belebele', belebele), ('scan', scan), ('arc', arc)):
        families[name] = evaluator(tree)
        frozen(tree)
        if time.process_time() - start_cpu > 85 or time.monotonic() - start_wall > 170:
            raise RuntimeError('Presupuesto F-1 agotado')
    gate = (all(families[name]['correct'] >= 1 for name in families)
            and (families['scan']['correct'] > max(families['scan']['fresh_correct'],
                                                  families['scan']['memory_correct'])
                 or families['arc']['correct'] > max(families['arc']['fresh_correct'],
                                                    families['arc']['memory_correct'])))
    result = {'tag': TAG, 'engine_tree': tree, 'engine_unchanged': True,
              'preregistration': 'prereg/F-1-puerta-externa-congelada.md',
              'gate_passed': gate, 'family_results': families,
              'cpu_s': round(time.process_time() - start_cpu, 6),
              'wall_s': round(time.monotonic() - start_wall, 3),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3' / 'f1_external_freeze_gate.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({**{key: value for key, value in result.items() if key != 'family_results'},
                      'families': {name: {key: value for key, value in family.items() if key != 'rows'}
                                   for name, family in families.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    run()

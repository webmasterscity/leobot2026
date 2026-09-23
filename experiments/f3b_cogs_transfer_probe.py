"""Development-only cross-domain probe for the candidate sequence learner."""
from __future__ import annotations

import json
import random
import resource
import time
import urllib.request
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leobot import Bot


ROOT = Path(__file__).resolve().parents[1]
COMMIT = '165a7b669eade971fa47bf568a2e51925360fed8'
SHAS = {'train.tsv': '220b3804b562c0156ee986eff1bdd15c27e52142549362a64f57baf86e304c78',
        'dev.tsv': 'ab66388a309c7ac1ad210c781a6a0ce12281a9ef24619a12422a752cef61bc21'}


def load(name):
    url = f'https://raw.githubusercontent.com/najoungkim/COGS/{COMMIT}/data/{name}'
    with urllib.request.urlopen(url, timeout=20) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024 or sha256(data).hexdigest() != SHAS[name]:
        raise RuntimeError('Fuente COGS alterada')
    rows = [line.split('\t') for line in data.decode('utf8').splitlines()]
    if any(len(row) != 3 for row in rows):
        raise RuntimeError('Formato COGS alterado')
    return [(row[0], row[1]) for row in rows], len(data)


def run():
    start_cpu, start_wall = time.process_time(), time.monotonic()
    train, train_bytes = load('train.tsv')
    dev, dev_bytes = load('dev.tsv')
    valid = [row for row in train if 1 <= len(row[0].split()) <= 128
             and 1 <= len(row[1].split()) <= 128]
    short = sorted(valid, key=lambda row: (len(row[0].split()), row[0]))[:64]
    rest = [row for row in valid if row not in short]
    taught = short + random.Random(1642).sample(rest, 448)
    bot = Bot()
    tick = time.process_time()
    for source, target in taught:
        bot.observe_sequence_example(source, target)
    report = bot.consolidate_sequence_learning()
    acquisition_cpu = time.process_time() - tick
    held = random.Random(2117).sample(dev, 32)
    statuses = Counter();correct = wrong_secure = 0
    for source, target in held:
        try:
            answer = bot.predict_sequence(source)
        except ValueError:
            statuses['too_long'] += 1
            continue
        statuses[answer['status']] += 1
        if answer['status'] == 'sequence_program':
            correct += int(answer.get('output') == target.split())
            wrong_secure += int(answer.get('output') != target.split())
    result = {'level': 'development diagnostic, not independent reserve',
              'source': 'https://github.com/najoungkim/COGS',
              'commit': COMMIT, 'source_bytes': train_bytes + dev_bytes,
              'train_examples': len(taught), 'dev_examples': len(held),
              'consolidation': report, 'correct': correct,
              'wrong_secure': wrong_secure, 'statuses': dict(statuses),
              'acquisition_cpu_s': round(acquisition_cpu, 6),
              'cpu_total_s': round(time.process_time() - start_cpu, 6),
              'wall_total_s': round(time.monotonic() - start_wall, 6),
              'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path = ROOT / 'results_v3' / 'f3b_cogs_transfer_probe.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    run()

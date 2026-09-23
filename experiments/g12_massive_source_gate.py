"""G-12 source gate: independent Spanish role annotations, no learner."""
from __future__ import annotations

import io
import json
import os
import random
import re
import resource
import sys
import tarfile
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
URL = ('https://amazon-massive-nlu-dataset.s3.amazonaws.com/'
       'amazon-massive-dataset-1.1.tar.gz')
CAP = 45 * 1024 * 1024
SEEDS = (719, 787, 853)
SPAN = re.compile(r'\[([^:\[\]]+?)\s*:\s*([^\[\]]+?)\]')


def source():
    with urlopen(URL, timeout=35) as response:
        size = int(response.headers.get('Content-Length', '0'))
        if not 0 < size <= CAP:
            raise RuntimeError('Paquete supera límite preregistrado')
        with tarfile.open(fileobj=response, mode='r|gz') as archive:
            for member in archive:
                if member.isfile() and member.name.endswith('/es-ES.jsonl'):
                    if member.size > CAP:
                        raise RuntimeError('Miembro español supera límite')
                    fileobj = archive.extractfile(member)
                    if fileobj is None:
                        raise RuntimeError('Miembro español inaccesible')
                    raw = fileobj.read(CAP+1)
                    if len(raw) != member.size or len(raw) > CAP:
                        raise RuntimeError('Lectura incompleta del miembro')
                    return raw, size, member.name
    raise RuntimeError('No aparece es-ES.jsonl')


def load_train(raw):
    rows = []
    span_total = span_recovered = malformed = skipped = 0
    for line in io.BytesIO(raw):
        item = json.loads(line)
        if item['partition'] != 'train':
            skipped += 1
            continue
        annot = item['annot_utt']
        matches = list(SPAN.finditer(annot))
        malformed += annot.count('[') != len(matches) or annot.count(']') != len(matches)
        labels = set()
        for match in matches:
            label, content = (part.strip() for part in match.groups())
            labels.add(label)
            span_total += 1
            span_recovered += bool(content) and content.casefold() in item['utt'].casefold()
        rows.append({'scenario': item['scenario'], 'labels': labels})
    return rows, {'train_rows': len(rows), 'nontrain_rows_skipped': skipped,
                  'annotated_spans': span_total, 'literal_spans': span_recovered,
                  'malformed_annotations': malformed}


def partitions(rows, h0):
    by_scenario = defaultdict(list)
    for row in rows:
        by_scenario[row['scenario']].append(row)
    eligible = sorted(name for name, items in by_scenario.items() if len(items) >= 100)
    reports = []
    for seed in SEEDS:
        scenarios = list(eligible)
        random.Random(int(h0[:8], 16) ^ seed ^ 0x69B).shuffle(scenarios)
        holdout = set(scenarios[:max(3, round(.2*len(scenarios)))])
        training = [row for scenario in eligible if scenario not in holdout
                    for row in by_scenario[scenario]]
        test = [row for scenario in eligible if scenario in holdout
                for row in by_scenario[scenario]]
        frequency = Counter(label for row in training for label in row['labels'])
        domains = defaultdict(set)
        for row in training:
            for label in row['labels']:
                domains[label].add(row['scenario'])
        recurrent = {label for label, count in frequency.items()
                     if count >= 20 and len(domains[label]) >= 3}
        test_frequency = Counter(label for row in test for label in row['labels'])
        test_domains = defaultdict(set)
        for row in test:
            for label in row['labels'] & recurrent:
                test_domains[label].add(row['scenario'])
        transferable = {label for label in recurrent
                        if test_frequency[label] >= 20 and len(test_domains[label]) >= 2}
        covered = sum(bool(row['labels'] & recurrent) for row in test)
        reports.append({'seed': seed, 'eligible_scenarios': len(eligible),
                        'training_scenarios': len(eligible)-len(holdout),
                        'heldout_scenarios': len(holdout),
                        'training_utterances': len(training),
                        'heldout_utterances': len(test),
                        'recurrent_roles': len(recurrent),
                        'transferable_roles': len(transferable),
                        'heldout_covered_utterances': covered,
                        'heldout_coverage': covered/len(test) if test else 0,
                        'gate_partition': (len(holdout) >= 4 and
                                           len(recurrent) >= 10 and
                                           len(transferable) >= 5 and
                                           len(test) > 0 and covered/len(test) >= .25)})
    return len(by_scenario), eligible, reports


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    h0 = git('rev-parse', 'estable-E-1:leobot')
    if git('rev-parse', 'HEAD:leobot') != h0 or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor alterado antes del inventario')
    raw, archive_bytes, member = source()
    read_cpu = time.process_time()-cpu0
    rows, annotation = load_train(raw)
    scenario_count, eligible, reports = partitions(rows, h0)
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    fidelity = (annotation['literal_spans']/annotation['annotated_spans']
                if annotation['annotated_spans'] else 0)
    budget = cpu <= 15 and wall <= 60 and rss <= 256*1024
    gate = (all(report['gate_partition'] for report in reports) and
            fidelity >= .98 and budget)
    unchanged = (git('rev-parse', 'HEAD:leobot') == h0 and
                 not git('status', '--porcelain', '--', 'leobot'))
    output = {'kind': 'development_independent_role_source_gate',
              'preregistration': 'prereg/G-12-fuente-independiente-roles.md',
              'source_url': URL, 'archive_content_length': archive_bytes,
              'spanish_member': member, 'spanish_bytes': len(raw),
              'spanish_sha256': sha256(raw).hexdigest(),
              'engine_tree': h0, 'engine_unchanged': unchanged,
              'scenarios': scenario_count, 'eligible_scenarios': len(eligible),
              'annotation': annotation, 'literal_fidelity': fidelity,
              'partitions': reports, 'budget_ok': budget,
              'gate_pass': gate, 'read_cpu_s': round(read_cpu, 6),
              'inventory_cpu_s': round(cpu-read_cpu, 6),
              'cpu_total_s': round(cpu, 6), 'wall_total_s': round(wall, 6),
              'max_rss_kib': rss}
    path = ROOT / f'results_v3/g12_massive_source_hashseed{os.environ.get("PYTHONHASHSEED", "unset")}.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if not unchanged:
        raise RuntimeError('Motor cambió durante el inventario')


if __name__ == '__main__':
    main()

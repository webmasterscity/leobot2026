"""G-23: external, bounded role learner conditional on gold UD trees."""
from __future__ import annotations

import json
import os
import random
import re
import resource
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git
from experiments.g22_ancora_source_gate import (
    H0, UD_URL, UP_URL, annotations, download, index_up, sentences, token_id,
)


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-23-papeles-por-rutas-sintacticas.md'
UP_SHA = '8f155e4309054e0fc6da8d1ca2253d631c0a716744c44958eaf9566c9cbfc260'
UD_SHA = '47b6fc49d6ed48a016e7fa5ad9f5c7ecf3ec21e9db005df3ea14d10f07c6deb6'
ROLES = ('A0', 'A1', 'A2')
SEEDS = (1361, 1423, 1487)


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g23_role_paths.py'))


def split_residue(seed, kind, value):
    payload = f'{H0}:{seed}:{kind}:{value}'.encode('utf-8')
    return int.from_bytes(sha256(payload).digest()[:8], 'big') % 4


def doc_id(sid):
    match = re.fullmatch(r'(.+)-s[0-9]+', sid or '')
    return match.group(1) if match else None


def nodes_from_ud(rows):
    nodes = {}
    for row in rows:
        if len(row) < 8 or not token_id(row[0]):
            continue
        if not re.fullmatch(r'[0-9]+', row[6]):
            return None
        nodes[row[0]] = {
            'form': row[1], 'lemma': row[2], 'upos': row[3],
            'head': row[6], 'deprel': row[7],
        }
    if not nodes:
        return None
    # Reject malformed trees once; all candidate paths then terminate.
    for start in nodes:
        visited = set()
        cursor = start
        while cursor != '0':
            if cursor in visited or cursor not in nodes:
                return None
            visited.add(cursor)
            cursor = nodes[cursor]['head']
    return nodes


def route(nodes, predicate, candidate):
    up = {predicate: ()}
    cursor = predicate
    for depth in range(3):
        if cursor == '0':
            break
        parent = nodes[cursor]['head']
        up[parent] = up[cursor] + ('^' + nodes[cursor]['deprel'],)
        cursor = parent
    cursor = candidate
    down = []
    for depth in range(4):
        if cursor in up:
            path = up[cursor] + tuple(reversed(down))
            return path if 1 <= len(path) <= 3 else None
        if cursor == '0' or depth >= 3:
            return None
        down.append('v' + nodes[cursor]['deprel'])
        cursor = nodes[cursor]['head']
    return None


def core_heads(head_field):
    roles = defaultdict(set)
    for role, head in annotations(head_field):
        if role in ROLES and token_id(head):
            roles[head].add(role)
    return roles


def predicate_cases(nodes, predicate, head_field):
    heads = core_heads(head_field)
    cases = []
    represented = set()
    excluded_ambiguous = 0
    for candidate in sorted(nodes, key=int):
        if candidate == predicate:
            continue
        path = route(nodes, predicate, candidate)
        if path is None:
            continue
        if len(heads.get(candidate, ())) > 1:
            excluded_ambiguous += 1
            continue
        label = next(iter(heads[candidate])) if heads.get(candidate) else 'NONE'
        path_key = '/'.join(path)
        upos = nodes[candidate]['upos']
        keys = {
            'full': path_key + '|' + upos,
            'path': path_key,
            'direct': nodes[candidate]['deprel'] + '|' + upos,
            'side': ('L' if int(candidate) < int(predicate) else 'R') + '|' + upos,
        }
        cases.append((candidate, keys, label))
        if label in ROLES:
            represented.add((candidate, label))
    total_gold = {(head, role) for head, roles_ in heads.items()
                  for role in roles_ if head in nodes}
    return cases, len(total_gold), len(represented), excluded_ambiguous


def new_tables():
    return {name: defaultdict(Counter)
            for name in ('full', 'path', 'direct', 'side', 'shuffled_full', 'shuffled_path')}


def add_training(tables, cases, rng):
    labels = [label for _, _, label in cases]
    scrambled = list(labels)
    rng.shuffle(scrambled)
    for (_, keys, label), shuffled in zip(cases, scrambled):
        for name in ('full', 'path', 'direct', 'side'):
            tables[name][keys[name]][label] += 1
        tables['shuffled_full'][keys['full']][shuffled] += 1
        tables['shuffled_path'][keys['path']][shuffled] += 1


def compile_table(table):
    rules = {}
    for key in sorted(table):
        counts = table[key]
        total = sum(counts.values())
        best = min(ROLES, key=lambda role: (-counts[role], role))
        if total >= 8 and counts[best] >= 5 and counts[best]/total >= .60:
            rules[key] = best
    return rules


def compile_models(tables):
    return {name: compile_table(table) for name, table in tables.items()}


def treatment_choice(models, keys):
    return models['full'].get(keys['full']) or models['path'].get(keys['path']) or 'NONE'


def decide(models, keys, treatment=None):
    return {
        'treatment': treatment if treatment is not None else treatment_choice(models, keys),
        'direct': models['direct'].get(keys['direct'], 'NONE'),
        'side': models['side'].get(keys['side'], 'NONE'),
        'shuffled': (models['shuffled_full'].get(keys['full'])
                     or models['shuffled_path'].get(keys['path']) or 'NONE'),
        'memory': 'NONE',
        'fresh': 'NONE',
    }


def score(test, feature_ms, models):
    if len(test) != len(feature_ms):
        raise RuntimeError('Faltan tiempos de extracción para predicados reservados')
    model_counts = {name: {role: Counter() for role in ROLES}
                    for name in ('treatment', 'direct', 'side', 'shuffled', 'memory', 'fresh')}
    pred_digests = {name: sha256() for name in model_counts}
    exact = Counter()
    latencies = []
    for cases, extraction_ms in zip(test, feature_ms):
        tick = time.perf_counter()
        choices = [treatment_choice(models, keys) for _, keys, _ in cases]
        latencies.append(extraction_ms + (time.perf_counter()-tick)*1000)
        predictions = [decide(models, keys, chosen)
                       for (_, keys, _), chosen in zip(cases, choices)]
        for name in model_counts:
            correct = True
            for (_, _, gold), choices in zip(cases, predictions):
                predicted = choices[name]
                pred_digests[name].update((predicted + '\n').encode())
                if predicted != gold:
                    correct = False
                for role in ROLES:
                    if predicted == role and gold == role:
                        model_counts[name][role]['tp'] += 1
                    elif predicted == role:
                        model_counts[name][role]['fp'] += 1
                    elif gold == role:
                        model_counts[name][role]['fn'] += 1
            exact[name] += correct
    results = {}
    for name, per_role in model_counts.items():
        role_scores = {}
        tp = fp = fn = 0
        for role in ROLES:
            counts = per_role[role]
            a, b, c = (counts.get(key, 0) for key in ('tp', 'fp', 'fn'))
            tp += a
            fp += b
            fn += c
            role_scores[role] = {'tp': a, 'fp': b, 'fn': c,
                                 'f1': (2*a/(2*a+b+c) if 2*a+b+c else 0)}
        results[name] = {
            'roles': role_scores,
            'micro_f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
            'precision': tp/(tp+fp) if tp+fp else 0,
            'recall': tp/(tp+fn) if tp+fn else 0,
            'exact_candidate_labels': exact[name],
            'prediction_sha256': pred_digests[name].hexdigest(),
        }
    ordered = sorted(latencies)
    return results, {
        'p50_ms': statistics.median(ordered) if ordered else None,
        'p95_ms': ordered[int((len(ordered)-1)*.95)] if ordered else None,
        'max_ms': max(ordered) if ordered else None,
    }


def source_stream(up, seed, tables, rng, test, feature_ms, stats, seen):
    used = 0
    digest = sha256()
    with urlopen(UD_URL, timeout=20) as response:
        length = int(response.headers.get('Content-Length', 0))
        if length > 48*1024*1024:
            raise RuntimeError('UD excede 48 MiB')

        def lines():
            nonlocal used
            for raw in response:
                used += len(raw)
                if used > 48*1024*1024:
                    raise RuntimeError('UD excede 48 MiB durante lectura')
                digest.update(raw)
                yield raw.decode('utf-8-sig')

        for sid, _, rows in sentences(lines()):
            stats['ud_sentences'] += 1
            entry = up.pop(sid, None)
            if entry is None:
                stats['unmatched_sentences'] += 1
                continue
            ids = tuple(row[0] for row in rows
                        if len(row) >= 3 and token_id(row[0]))
            if ids != entry[0]:
                stats['token_id_mismatches'] += 1
                continue
            doc = doc_id(sid)
            if doc is None:
                stats['missing_document_id'] += 1
                continue
            nodes = nodes_from_ud(rows)
            if nodes is None:
                stats['invalid_dependency_tree'] += 1
                continue
            for predicate, _, head_field, _ in entry[1]:
                stats['predicate_rows'] += 1
                item = nodes.get(predicate)
                if item is None or item['upos'] != 'VERB':
                    stats['nonverb_or_missing_predicate'] += 1
                    continue
                lemma = item['lemma']
                if lemma in ('_', ''):
                    stats['missing_lemma'] += 1
                    continue
                document_residue = split_residue(seed, 'doc', doc)
                lemma_residue = split_residue(seed, 'lemma', lemma)
                if document_residue == lemma_residue == 0:
                    partition = 'heldout'
                elif document_residue != 0 and lemma_residue != 0:
                    partition = 'train'
                else:
                    stats['cross_partition_ignored'] += 1
                    continue
                case_tick = time.perf_counter()
                cases, gold, represented, ambiguous = predicate_cases(
                    nodes, predicate, head_field)
                case_elapsed_ms = (time.perf_counter()-case_tick)*1000
                stats['gold_core_heads_' + partition] += gold
                stats['representable_core_heads_' + partition] += represented
                stats['ambiguous_candidates_' + partition] += ambiguous
                stats['candidate_cases'] += len(cases)
                if stats['candidate_cases'] > 2_000_000:
                    raise RuntimeError('Se agotó límite de 2 millones de candidatos')
                stats['predicates_' + partition] += 1
                seen[partition]['docs'].add(doc)
                seen[partition]['lemmas'].add(lemma)
                if partition == 'train':
                    add_training(tables, cases, rng)
                else:
                    opaque_nodes = {key: {**value, 'form': 'z'+key, 'lemma': 'opaque'}
                                    for key, value in nodes.items()}
                    opaque_cases, _, _, _ = predicate_cases(
                        opaque_nodes, predicate, head_field)
                    stats['renaming_failures'] += opaque_cases != cases
                    test.append(cases)
                    feature_ms.append(case_elapsed_ms)
    stats['up_without_ud'] = len(up)
    return used, digest.hexdigest()


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    if not frozen():
        raise RuntimeError('Motor o evaluador no congelado')
    up_raw = download(UP_URL, 20*1024*1024)
    if sha256(up_raw).hexdigest() != UP_SHA:
        raise RuntimeError('UP cambió')
    up_bytes = len(up_raw)
    up_download_cpu = time.process_time()-cpu0
    tick = time.process_time()
    up, up_stats = index_up(up_raw)
    del up_raw
    up_index_cpu = time.process_time()-tick

    stats = Counter(up_stats)
    tables = new_tables()
    rng = random.Random(int(H0[:8], 16) ^ seed ^ 0x23A)
    test = []
    feature_ms = []
    seen = {name: {'docs': set(), 'lemmas': set()} for name in ('train', 'heldout')}
    tick = time.process_time()
    ud_bytes, ud_hash = source_stream(up, seed, tables, rng, test,
                                     feature_ms, stats, seen)
    stream_cpu = time.process_time()-tick
    if ud_hash != UD_SHA:
        raise RuntimeError('UD cambió')
    tick = time.process_time()
    models = compile_models(tables)
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json') as stream:
        json.dump(models, stream, sort_keys=True, ensure_ascii=False)
        stream.flush()
        stream.seek(0)
        restored = json.load(stream)
    restart_same = restored == models
    models = restored
    compile_cpu = time.process_time()-tick
    tick = time.process_time()
    results, latency = score(test, feature_ms, models)
    inference_cpu = time.process_time()-tick
    renaming_same = stats.get('renaming_failures', 0) == 0

    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    treatment = results['treatment']
    best = max(results[name]['micro_f1'] for name in ('direct', 'side', 'shuffled'))
    enough = (stats['predicates_heldout'] >= 400
              and len(seen['heldout']['lemmas']) >= 20
              and stats['representable_core_heads_heldout'] >= 500)
    budget = (cpu <= 30 and wall <= 60 and rss <= 256*1024
              and stats['candidate_cases'] <= 2_000_000)
    gate = (budget and enough and treatment['micro_f1'] >= .65
            and treatment['micro_f1'] - best >= .10
            and treatment['roles']['A0']['f1'] >= .60
            and treatment['roles']['A1']['f1'] >= .60
            and treatment['roles']['A2']['f1'] >= .40
            and treatment['micro_f1'] - results['shuffled']['micro_f1'] >= .15
            and renaming_same and restart_same
            and latency['p95_ms'] is not None and latency['p95_ms'] <= 10)
    unchanged = frozen()
    output = {
        'kind': 'G23_oracle_UD_role_path_gate',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': {'up': UP_SHA, 'ud': ud_hash},
        'source_bytes': {'up': up_bytes, 'ud': ud_bytes},
        'seed': seed,
        'counts': dict(stats),
        'split': {name: {'documents': len(groups['docs']),
                         'lemmas': len(groups['lemmas'])}
                  for name, groups in seen.items()},
        'rule_counts': {name: len(rules) for name, rules in models.items()},
        'results': results,
        'latency': latency,
        'renaming_same': renaming_same,
        'restart_same': restart_same,
        'up_download_cpu_s': round(up_download_cpu, 6),
        'up_index_cpu_s': round(up_index_cpu, 6),
        'ud_stream_training_cpu_s': round(stream_cpu, 6),
        'compile_restart_cpu_s': round(compile_cpu, 6),
        'inference_cpu_s': round(inference_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
        'sample_ok': enough,
        'gate_pass': gate and unchanged,
    }
    path = ROOT / ('results_v3/g23_role_paths_seed' + str(seed)
                   + '_hashseed' + os.environ.get('PYTHONHASHSEED', 'unset') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in output.items()
                      if key != 'results'}, ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante ensayo')


if __name__ == '__main__':
    main(int(sys.argv[1]))

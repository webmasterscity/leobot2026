"""G-24: learn a role promotion policy on education, evaluate on unseen lemmas."""
from __future__ import annotations

import itertools
import json
import math
import os
import random
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
from experiments.g22_ancora_source_gate import H0, UD_URL, UP_URL, download, index_up, sentences, token_id
from experiments.g23_role_paths import (
    ROLES, UD_SHA, UP_SHA, compile_table, doc_id, nodes_from_ud,
    predicate_cases, split_residue,
)


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-24-promocion-calibrada-de-papeles.md'
SEEDS = (1423, 1487)
LABELS = ('NONE', *ROLES)
GRID = (-3, -2, -1, 0, 1)
KEY_NAMES = ('full', 'path', 'direct', 'side')


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g24_calibrated_roles.py',
                        'experiments/g23_role_paths.py'))


def compact(cases):
    return tuple((sys.intern(keys['full']), sys.intern(keys['path']),
                  sys.intern(keys['direct']), sys.intern(keys['side']), label)
                 for _, keys, label in cases)


def count_model(groups, *, shuffled, seed):
    tables = {name: defaultdict(Counter) for name in KEY_NAMES}
    global_counts = Counter()
    rng = random.Random(int(H0[:8], 16) ^ seed ^ 0x24A)
    for group in groups:
        labels = [case[4] for case in group]
        if shuffled:
            rng.shuffle(labels)
        for case, label in zip(group, labels):
            global_counts[label] += 1
            for index, name in enumerate(KEY_NAMES):
                tables[name][case[index]][label] += 1
    return {'tables': tables, 'global': global_counts}


def prior(model):
    total = sum(model['global'].values()) + len(LABELS)
    return {label: (model['global'].get(label, 0)+1)/total for label in LABELS}


def posterior(table, key, base):
    counts = table.get(key)
    n = sum(counts.values()) if counts else 0
    return ({label: (counts.get(label, 0)+8*base[label])/(n+8)
             for label in LABELS} if counts else base), n


def logits(model, case, variant, base):
    tables = model['tables']
    if variant in ('treatment', 'shuffled'):
        full, nfull = posterior(tables['full'], case[0], base)
        path, npath = posterior(tables['path'], case[1], base)
        if not nfull and not npath:
            return None
        weight = nfull/(nfull+8)
        probs = {label: weight*full[label]+(1-weight)*path[label]
                 for label in LABELS}
    else:
        index, table_name = ((2, 'direct') if variant == 'direct'
                             else (3, 'side'))
        probs, support = posterior(tables[table_name], case[index], base)
        if not support:
            return None
    absent = probs['NONE']
    return tuple(math.log(probs[role]/absent) for role in ROLES)


def choice(values, thresholds):
    if values is None:
        return 'NONE'
    ranked = [(value-thresholds[i], -i, role)
              for i, (value, role) in enumerate(zip(values, ROLES))]
    score, _, role = max(ranked)
    return role if score > 0 else 'NONE'


def calibration_scores(groups, model, variant):
    base = prior(model)
    return [(logits(model, case, variant, base), case[4])
            for group in groups for case in group]


def count_outcomes(pairs, thresholds):
    by_role = {role: Counter() for role in ROLES}
    for values, gold in pairs:
        predicted = choice(values, thresholds)
        for role in ROLES:
            if predicted == role and gold == role:
                by_role[role]['tp'] += 1
            elif predicted == role:
                by_role[role]['fp'] += 1
            elif gold == role:
                by_role[role]['fn'] += 1
    tp = sum(row.get('tp', 0) for row in by_role.values())
    fp = sum(row.get('fp', 0) for row in by_role.values())
    fn = sum(row.get('fn', 0) for row in by_role.values())
    role_scores = {}
    for role, row in by_role.items():
        a, b, c = (row.get(key, 0) for key in ('tp', 'fp', 'fn'))
        role_scores[role] = {'tp': a, 'fp': b, 'fn': c,
                             'f1': 2*a/(2*a+b+c) if 2*a+b+c else 0}
    return {
        'micro_f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
        'precision': tp/(tp+fp) if tp+fp else 0,
        'recall': tp/(tp+fn) if tp+fn else 0,
        'roles': role_scores,
    }


def calibrate(groups, model, variant):
    pairs = calibration_scores(groups, model, variant)
    best = None
    for thresholds in itertools.product(GRID, repeat=3):
        metric = count_outcomes(pairs, thresholds)
        rank = (metric['micro_f1'], thresholds)
        if best is None or rank > best[0]:
            best = (rank, thresholds, metric)
    return tuple(best[1]), best[2], len(pairs)


def fixed_rules(model):
    return {name: compile_table({key: Counter(counts)
                                 for key, counts in model['tables'][name].items()})
            for name in ('full', 'path')}


def fixed_choice(rules, case):
    return rules['full'].get(case[0]) or rules['path'].get(case[1]) or 'NONE'


def score(test, feature_ms, models, thresholds):
    if len(test) != len(feature_ms):
        raise RuntimeError('Faltan tiempos de extracción')
    names = ('treatment', 'direct', 'side', 'shuffled', 'fixed', 'memory', 'fresh')
    observations = {name: [] for name in names}
    digests = {name: sha256() for name in names}
    bases = {name: prior(models['shuffled' if name == 'shuffled' else 'treatment'])
             for name in ('treatment', 'direct', 'side', 'shuffled')}
    original = fixed_rules(models['treatment'])
    latencies = []
    exact = Counter()
    for group, extraction in zip(test, feature_ms):
        tick = time.perf_counter()
        candidate = [choice(logits(models['treatment'], case, 'treatment',
                                   bases['treatment']), thresholds['treatment'])
                     for case in group]
        latencies.append(extraction + (time.perf_counter()-tick)*1000)
        predictions = {'treatment': candidate}
        for name in ('direct', 'side', 'shuffled'):
            model = models['shuffled' if name == 'shuffled' else 'treatment']
            predictions[name] = [
                choice(logits(model, case, name, bases[name]), thresholds[name])
                for case in group]
        predictions['fixed'] = [fixed_choice(original, case) for case in group]
        predictions['memory'] = ['NONE']*len(group)
        predictions['fresh'] = ['NONE']*len(group)
        for name in names:
            exact[name] += all(value == case[4]
                               for value, case in zip(predictions[name], group))
            for predicted, case in zip(predictions[name], group):
                observations[name].append((predicted, case[4]))
                digests[name].update((predicted+'\n').encode())
    results = {}
    for name in names:
        scored = count_outcomes(((None if predicted == 'NONE' else
                                  tuple(1.0 if role == predicted else -1.0
                                        for role in ROLES), gold)
                                 for predicted, gold in observations[name]),
                                (0, 0, 0))
        # count_outcomes reconstructs the chosen label from the encoded vector.
        scored['exact_candidate_labels'] = exact[name]
        scored['prediction_sha256'] = digests[name].hexdigest()
        results[name] = scored
    ordered = sorted(latencies)
    latency = {'p50_ms': statistics.median(ordered) if ordered else None,
               'p95_ms': ordered[int((len(ordered)-1)*.95)] if ordered else None,
               'max_ms': max(ordered) if ordered else None}
    return results, latency


def source_stream(up, seed, training, test, feature_ms, stats, groups):
    used = 0
    digest = sha256()
    with urlopen(UD_URL, timeout=20) as response:
        length = int(response.headers.get('Content-Length', 0))
        if length > 48*1024*1024:
            raise RuntimeError('UD excede presupuesto')

        def lines():
            nonlocal used
            for raw in response:
                used += len(raw)
                if used > 48*1024*1024:
                    raise RuntimeError('UD excede presupuesto durante lectura')
                digest.update(raw)
                yield raw.decode('utf-8-sig')

        for sid, _, rows in sentences(lines()):
            entry = up.pop(sid, None)
            if entry is None:
                continue
            ids = tuple(row[0] for row in rows
                        if len(row) >= 3 and token_id(row[0]))
            if ids != entry[0]:
                stats['token_id_mismatch_sentences'] += 1
                continue
            doc = doc_id(sid)
            if doc is None:
                stats['missing_document_id'] += 1
                continue
            nodes = nodes_from_ud(rows)
            if nodes is None:
                stats['invalid_dependency_tree'] += 1
                continue
            doc_residue = split_residue(seed, 'doc', doc)
            cal_doc = split_residue(seed, 'caldoc', doc)
            for predicate, _, head_field, _ in entry[1]:
                item = nodes.get(predicate)
                if item is None or item['upos'] != 'VERB':
                    stats['nonverb_or_missing'] += 1
                    continue
                lemma = item['lemma']
                if lemma in ('_', ''):
                    stats['missing_lemma'] += 1
                    continue
                lemma_residue = split_residue(seed, 'lemma', lemma)
                if doc_residue == lemma_residue == 0:
                    partition = 'test'
                elif doc_residue != 0 and lemma_residue != 0:
                    partition = 'train'
                else:
                    stats['external_cross_ignored'] += 1
                    continue
                tick = time.perf_counter()
                expanded, gold, represented, _ = predicate_cases(
                    nodes, predicate, head_field)
                elapsed_ms = (time.perf_counter()-tick)*1000
                cases = compact(expanded)
                stats['candidate_cases'] += len(cases)
                if stats['candidate_cases'] > 2_000_000:
                    raise RuntimeError('Límite de candidatas agotado')
                stats['predicates_' + partition] += 1
                stats['gold_' + partition] += gold
                stats['represented_' + partition] += represented
                groups[partition]['docs'].add(doc)
                groups[partition]['lemmas'].add(lemma)
                if partition == 'test':
                    opaque = {key: {**value, 'form': 'z'+key, 'lemma': 'opaque'}
                              for key, value in nodes.items()}
                    changed, _, _, _ = predicate_cases(opaque, predicate, head_field)
                    stats['renaming_failures'] += compact(changed) != cases
                    test.append(cases)
                    feature_ms.append(elapsed_ms)
                else:
                    idx = len(training)
                    training.append(cases)
                    cal_lemma = split_residue(seed, 'callemma', lemma)
                    if cal_doc == cal_lemma == 0:
                        groups['calibration']['indices'].append(idx)
                        groups['calibration']['docs'].add(doc)
                        groups['calibration']['lemmas'].add(lemma)
                        stats['calibration_gold'] += represented
                    elif cal_doc != 0 and cal_lemma != 0:
                        groups['fit']['indices'].append(idx)
                        groups['fit']['docs'].add(doc)
                        groups['fit']['lemmas'].add(lemma)
                    else:
                        stats['internal_cross_ignored'] += 1
    stats['up_without_ud'] = len(up)
    return used, digest.hexdigest()


def main(seed):
    if seed not in SEEDS:
        raise ValueError('Semilla fuera del preregistro')
    cpu0, wall0 = time.process_time(), time.monotonic()
    if not frozen():
        raise RuntimeError('Motor o evaluador no congelado')
    raw = download(UP_URL, 20*1024*1024)
    if sha256(raw).hexdigest() != UP_SHA:
        raise RuntimeError('UP cambió')
    up_bytes = len(raw)
    up_download_cpu = time.process_time()-cpu0
    tick = time.process_time()
    up, _ = index_up(raw)
    del raw
    up_index_cpu = time.process_time()-tick

    training = []
    test = []
    feature_ms = []
    stats = Counter()
    groups = {
        name: {'docs': set(), 'lemmas': set(), 'indices': []}
        for name in ('train', 'test', 'fit', 'calibration')
    }
    tick = time.process_time()
    ud_bytes, ud_hash = source_stream(up, seed, training, test, feature_ms,
                                      stats, groups)
    stream_cpu = time.process_time()-tick
    if ud_hash != UD_SHA:
        raise RuntimeError('UD cambió')
    fit_groups = [training[index] for index in groups['fit']['indices']]
    calibration_groups = [training[index]
                          for index in groups['calibration']['indices']]
    sample_ok = (len(calibration_groups) >= 300
                 and stats['calibration_gold'] >= 400
                 and stats['predicates_test'] >= 400
                 and len(groups['test']['lemmas']) >= 20
                 and stats['represented_test'] >= 500)
    tick = time.process_time()
    fitting = count_model(fit_groups, shuffled=False, seed=seed)
    shuffled_fitting = count_model(fit_groups, shuffled=True, seed=seed)
    thresholds = {}
    calibration_results = {}
    for name in ('treatment', 'direct', 'side', 'shuffled'):
        model = shuffled_fitting if name == 'shuffled' else fitting
        selected, metric, examined = calibrate(calibration_groups, model, name)
        thresholds[name] = selected
        calibration_results[name] = {'metric': metric, 'cases': examined}
    calibration_cpu = time.process_time()-tick
    tick = time.process_time()
    models = {
        'treatment': count_model(training, shuffled=False, seed=seed),
        'shuffled': count_model(training, shuffled=True, seed=seed),
    }
    stored = {'models': models, 'thresholds': thresholds}
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json') as stream:
        json.dump(stored, stream, sort_keys=True, ensure_ascii=False)
        stream.flush()
        stream.seek(0)
        loaded = json.load(stream)
    restart_same = loaded == json.loads(json.dumps(stored))
    models, thresholds = loaded['models'], loaded['thresholds']
    refit_cpu = time.process_time()-tick
    tick = time.process_time()
    results, latency = score(test, feature_ms, models, thresholds)
    inference_cpu = time.process_time()-tick

    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    treatment = results['treatment']
    best = max(results[name]['micro_f1']
               for name in ('fixed', 'direct', 'side', 'shuffled'))
    budget = (cpu <= 60 and wall <= 90 and rss <= 256*1024
              and stats['candidate_cases'] <= 2_000_000)
    gate = (budget and sample_ok and treatment['micro_f1'] >= .65
            and treatment['micro_f1']-best >= .10
            and treatment['roles']['A0']['f1'] >= .60
            and treatment['roles']['A1']['f1'] >= .60
            and treatment['roles']['A2']['f1'] >= .40
            and treatment['micro_f1']-results['shuffled']['micro_f1'] >= .15
            and stats.get('renaming_failures', 0) == 0 and restart_same
            and latency['p95_ms'] is not None and latency['p95_ms'] <= 10)
    unchanged = frozen()
    output = {
        'kind': 'G24_oracle_UD_calibrated_role_gate',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': {'up': UP_SHA, 'ud': ud_hash},
        'source_bytes': {'up': up_bytes, 'ud': ud_bytes},
        'seed': seed,
        'counts': dict(stats),
        'split': {name: {'documents': len(values['docs']),
                         'lemmas': len(values['lemmas']),
                         'predicates': len(values['indices']) if name in ('fit','calibration')
                         else stats.get('predicates_'+name, 0)}
                  for name, values in groups.items()},
        'thresholds': thresholds,
        'calibration': calibration_results,
        'results': results,
        'latency': latency,
        'renaming_same': stats.get('renaming_failures', 0) == 0,
        'restart_same': restart_same,
        'up_download_cpu_s': round(up_download_cpu, 6),
        'up_index_cpu_s': round(up_index_cpu, 6),
        'ud_stream_training_cpu_s': round(stream_cpu, 6),
        'calibration_cpu_s': round(calibration_cpu, 6),
        'refit_cpu_s': round(refit_cpu, 6),
        'inference_cpu_s': round(inference_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
        'sample_ok': sample_ok,
        'gate_pass': gate and unchanged,
    }
    path = ROOT / ('results_v3/g24_calibrated_seed' + str(seed)
                   + '_hashseed' + os.environ.get('PYTHONHASHSEED', 'unset') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('results', 'calibration')},
                     ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante ensayo')


if __name__ == '__main__':
    main(int(sys.argv[1]))

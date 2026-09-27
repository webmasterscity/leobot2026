"""G-71: bounded, joint role layouts; an external development experiment."""
from __future__ import annotations

import itertools
import json
import math
import random
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.g22_ancora_source_gate import (
    UD_URL, UP_URL, download, index_up, sentences, token_id,
)
from experiments.g23_role_paths import (
    ROLES, UD_SHA, UP_SHA, core_heads, doc_id, nodes_from_ud, predicate_cases,
)
from experiments.g24_calibrated_roles import (
    calibrate, choice, compact, count_model, logits, prior,
)

ROOT = Path(__file__).resolve().parents[1]
ENGINE = '11a1ef5836382d81a643cad0b217a8669ce0f2d1'
NONE = 'NONE'


class JointConstructions:
    """Observed complete layouts, matched injectively against candidate slots."""

    def __init__(self, patterns, anchors):
        self.patterns = patterns
        self.anchors = anchors
        self.index = defaultdict(list)
        for idx, anchor in enumerate(anchors):
            self.index[anchor].append(idx)

    @classmethod
    def learn(cls, frames):
        counts = Counter()
        keys = Counter()
        for frame in frames:
            grouped = defaultdict(list)
            for key, label in frame:
                if label != NONE:
                    grouped[key].append(label)
                    keys[key] += 1
            if not grouped:
                continue
            pattern = tuple((key, tuple(labels))
                            for key, labels in sorted(grouped.items()))
            counts[pattern] += 1
            if len(counts) > 25_000:
                raise RuntimeError('Más de 25 000 construcciones')
        patterns = list(counts.items())
        anchors = [min((key for key, _ in pattern), key=keys.__getitem__)
                   for pattern, _ in patterns]
        return cls(patterns, anchors)

    def predict(self, keys, margins, limit=2048):
        available = defaultdict(list)
        for idx, key in enumerate(keys):
            available[key].append(idx)
        ids = sorted({idx for key in available for idx in self.index.get(key, ())})
        empty = (NONE,) * len(keys)
        best, answer = (0.0, 0), empty
        stats = {'patterns_considered': len(ids), 'applications': 0,
                 'exhausted': False}
        for idx in ids:
            pattern, frequency = self.patterns[idx]
            if any(len(available[key]) < len(labels) for key, labels in pattern):
                continue
            applications = math.prod(math.comb(len(available[key]), len(labels))
                                     for key, labels in pattern)
            if stats['applications'] + applications > limit:
                # product() materializes its inputs: bound their size first.
                stats['exhausted'] = True
                return empty, stats
            # Every key occupies disjoint positions. Within repeated keys, the
            # learned order is retained by combinations, not permutations.
            options = [itertools.combinations(available[key], len(labels))
                       for key, labels in pattern]
            for positions in itertools.product(*options):
                stats['applications'] += 1
                if stats['applications'] > limit:
                    stats['exhausted'] = True
                    return empty, stats
                assignment = [(pos, label)
                              for positions_, (_, labels) in zip(positions, pattern)
                              for pos, label in zip(positions_, labels)]
                score = sum(margins[pos].get(label, -math.inf)
                            for pos, label in assignment)
                rank = (score, frequency)
                if score > 0 and rank > best:
                    best = rank
                    chosen = list(empty)
                    for pos, label in assignment:
                        chosen[pos] = label
                    answer = tuple(chosen)
        return answer, stats

    def payload(self):
        return {'patterns': self.patterns, 'anchors': self.anchors}

    def renamed(self, keys, roles):
        patterns = [([(keys[key], [roles[label] for label in labels])
                      for key, labels in pattern], frequency)
                    for pattern, frequency in self.patterns]
        return JointConstructions(patterns, [keys[key] for key in self.anchors])


def fingerprint():
    paths = [Path(__file__), ROOT / 'experiments/g22_ancora_source_gate.py',
             ROOT / 'experiments/g23_role_paths.py',
             ROOT / 'experiments/g24_calibrated_roles.py',
             ROOT / 'prereg/G-71-construcciones-conjuntas.md']
    if git('rev-parse', 'HEAD:leobot') != ENGINE:
        raise RuntimeError('Motor distinto del preregistrado')
    if git('status', '--porcelain', '--', 'leobot',
           *(str(path.relative_to(ROOT)) for path in paths)):
        raise RuntimeError('Motor, preregistro o fuentes sin congelar')
    return {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in paths}


def cached_source(name, url, expected, cap, local=None):
    path = ROOT / '.leobot-data' / name
    if path.exists():
        raw = path.read_bytes()
    else:
        raw = Path(local).read_bytes() if local and Path(local).exists() else b''
        if sha256(raw).hexdigest() != expected:
            raw = download(url, cap)
        path.parent.mkdir(parents=True, exist_ok=True)
        if sha256(raw).hexdigest() != expected:
            raise RuntimeError('Huella incorrecta: ' + name)
        path.write_bytes(raw)
    if len(raw) > cap or sha256(raw).hexdigest() != expected:
        raise RuntimeError('Caché incorrecta: ' + name)
    return raw


def residue(seed, kind, value):
    return int.from_bytes(sha256(f'{ENGINE}:{seed}:{kind}:{value}'.encode())
                          .digest()[:8], 'big') % 4


def acquire(seed):
    t = time.process_time()
    up, _ = index_up(cached_source('g71_ancora_up.conllup', UP_URL, UP_SHA,
                                  20 * 1024**2))
    raw = cached_source('g71_ancora_ud.conllu', UD_URL, UD_SHA, 48 * 1024**2,
                        '/media/leonardo/data/corpus_ud/es_ancora-ud-train.conllu')
    del raw
    acquisition = time.process_time() - t
    t = time.process_time()
    parts = {name: [] for name in ('fit', 'calibration', 'development')}
    symbols = {name: {'docs': set(), 'lemmas': set()} for name in parts}
    counts = Counter()
    with (ROOT / '.leobot-data/g71_ancora_ud.conllu').open() as handle:
        for sid, _, rows in sentences(handle):
            entry = up.pop(sid, None)
            doc = doc_id(sid)
            if entry is None or doc is None:
                counts['missing_pair_or_document'] += 1
                continue
            ids = tuple(row[0] for row in rows if len(row) >= 3 and token_id(row[0]))
            if ids != entry[0]:
                counts['token_id_mismatch_sentences'] += 1
                continue
            nodes = nodes_from_ud(rows)
            if nodes is None:
                counts['invalid_tree'] += 1
                continue
            d = residue(seed, 'doc', doc)
            for pred, _, field, _ in entry[1]:
                node = nodes.get(pred)
                if not node or node['upos'] != 'VERB' or node['lemma'] in ('', '_'):
                    counts['nonverb_or_missing'] += 1
                    continue
                lemma = node['lemma']
                v = residue(seed, 'lemma', lemma)
                if d == v == 0:
                    part = 'development'
                elif d != 0 and v != 0:
                    cd = residue(seed, 'caldoc', doc)
                    cv = residue(seed, 'callemma', lemma)
                    if cd == cv == 0:
                        part = 'calibration'
                    elif cd != 0 and cv != 0:
                        part = 'fit'
                    else:
                        counts['internal_cross_excluded'] += 1
                        continue
                else:
                    counts['external_cross_excluded'] += 1
                    continue
                tick = time.perf_counter()
                expanded, gold, represented, ambiguous = predicate_cases(nodes, pred, field)
                cases = compact(expanded)
                elapsed = (time.perf_counter() - tick) * 1000
                represented_pairs = {(head, label) for head, _, label in expanded
                                     if label != NONE}
                missed_roles = Counter(role for head, labels in core_heads(field).items()
                                       for role in labels if head in nodes
                                       and (head, role) not in represented_pairs)
                if sum(missed_roles.values()) != gold - represented:
                    raise RuntimeError('Conteo de omisiones inconsistente')
                counts['candidates'] += len(cases)
                counts['ambiguous_excluded'] += ambiguous
                if counts['candidates'] > 2_000_000:
                    raise RuntimeError('Más de dos millones de candidatos')
                parts[part].append({'cases': cases, 'gold': gold,
                                    'represented': represented, 'feature_ms': elapsed,
                                    'missed_roles': dict(missed_roles)})
                for kind, value in (('docs', doc), ('lemmas', lemma)):
                    symbols[part][kind].add(value)
    for left, right in itertools.combinations(parts, 2):
        for kind in ('docs', 'lemmas'):
            if symbols[left][kind] & symbols[right][kind]:
                raise RuntimeError('Contaminación entre particiones')
    splits = {name: {**{kind: len(values) for kind, values in symbols[name].items()},
                    'groups': len(groups), 'candidates': sum(len(g['cases']) for g in groups),
                    'gold': sum(g['gold'] for g in groups),
                    'represented': sum(g['represented'] for g in groups)}
              for name, groups in parts.items()}
    return parts, splits, dict(counts), acquisition, time.process_time() - t


def frames(groups, seed, shuffled=False):
    rng = random.Random(seed)
    excluded = Counter()
    examples = []
    for group in groups:
        if group['gold'] != group['represented']:
            excluded['incomplete'] += 1
            continue
        frame = [(case[0], case[4]) for case in group['cases'] if case[4] != NONE]
        if len(frame) > 8:
            excluded['oversize'] += 1
            continue
        if not frame:
            excluded['empty'] += 1
            continue
        if shuffled:
            labels = [label for _, label in frame]
            rng.shuffle(labels)
            frame = [(key, label) for (key, _), label in zip(frame, labels)]
        examples.append(frame)
    return examples, dict(excluded)


def metric(pairs, missed_roles, exact, n):
    counters = {role: Counter() for role in ROLES}
    for pred, gold in pairs:
        for role, counter in counters.items():
            if pred == gold == role:
                counter['tp'] += 1
            elif pred == role:
                counter['fp'] += 1
            elif gold == role:
                counter['fn'] += 1

    def values(counter):
        tp, fp, fn = (counter[k] for k in ('tp', 'fp', 'fn'))
        return {**{k: counter[k] for k in ('tp', 'fp', 'fn')},
                'precision': tp / (tp + fp) if tp + fp else 0,
                'recall': tp / (tp + fn) if tp + fn else 0,
                'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0}

    total = sum(counters.values(), Counter())
    represented = values(total)
    role_represented = {role: values(c) for role, c in counters.items()}
    missed = sum(missed_roles.values())
    total['fn'] += missed
    for role, count in missed_roles.items():
        counters[role]['fn'] += count
    return {**values(total), 'represented_only': represented,
            'roles_represented_only': role_represented,
            'roles': {role: values(c) for role, c in counters.items()},
            'gold_outside_extractor': missed, 'exact': exact, 'groups': n,
            'exact_rate': exact / n if n else 0}


def timing(samples):
    values = sorted(samples)
    return {'p50_ms': statistics.median(values),
            'p95_ms': values[int((len(values) - 1) * .95)], 'max_ms': max(values)}


def evaluate(groups, local, thresholds, joint, shuffled, restored, renamed,
             rename_keys, rename_roles):
    base = prior(local)
    names = ('independent', 'joint', 'shuffled', 'fresh', 'memory')
    pairs = {name: [] for name in names}
    exact = Counter()
    digests = {name: sha256() for name in names}
    controls, search = Counter(), Counter()
    times = defaultdict(list)
    missed = Counter()
    reverse_roles = {v: k for k, v in rename_roles.items()}
    for group in groups:
        cases = group['cases']
        tick = time.perf_counter()
        scores = [logits(local, case, 'treatment', base) for case in cases]
        independent = tuple(choice(score, thresholds) for score in scores)
        margins = [{} if score is None else
                   {role: score[i] - thresholds[i] for i, role in enumerate(ROLES)}
                   for score in scores]
        shared_ms = (time.perf_counter() - tick) * 1000
        keys = [case[0] for case in cases]
        tick = time.perf_counter()
        prediction, used = joint.predict(keys, margins)
        decision_ms = (time.perf_counter() - tick) * 1000
        times['independent'].append(group['feature_ms'] + shared_ms)
        times['joint'].append(group['feature_ms'] + shared_ms + decision_ms)
        times['joint_decision_only'].append(decision_ms)
        search.update(used)
        scramble, _ = shuffled.predict(keys, margins)
        reload_prediction, _ = restored.predict(keys, margins)
        opaque, _ = renamed.predict([rename_keys[key] for key in keys],
                                    [{rename_roles[role]: val for role, val in row.items()}
                                     for row in margins])
        controls['restart_mismatches'] += prediction != reload_prediction
        controls['renaming_mismatches'] += prediction != tuple(
            reverse_roles.get(role, role) for role in opaque)
        predictions = dict(independent=independent, joint=prediction, shuffled=scramble,
                           fresh=(NONE,) * len(cases), memory=(NONE,) * len(cases))
        outside = group['gold'] - group['represented']
        missed.update(group['missed_roles'])
        exact_flags = {}
        for name, values in predictions.items():
            observations = list(zip(values, (case[4] for case in cases)))
            pairs[name].extend(observations)
            good = not outside and all(pred == gold for pred, gold in observations)
            exact[name] += good
            exact_flags[name] = good
            digests[name].update((json.dumps(values) + '\n').encode())
        controls['changed_groups'] += prediction != independent
        controls['exact_gains'] += exact_flags['joint'] and not exact_flags['independent']
        controls['exact_losses'] += exact_flags['independent'] and not exact_flags['joint']
    metrics = {name: {**metric(pairs[name], missed, exact[name], len(groups)),
                      'prediction_sha256': digests[name].hexdigest()}
               for name in names}
    return metrics, dict(controls), dict(search), {k: timing(v) for k, v in times.items()}


def main(which):
    if which not in (0, 1):
        raise ValueError('Usar partición 0 o 1')
    resource.setrlimit(resource.RLIMIT_CPU, (600, 610))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    cpu0, wall0 = time.process_time(), time.monotonic()
    hashes = fingerprint()
    seed = int(ENGINE[:8], 16) ^ 0x7100 ^ which
    parts, splits, counts, acquisition, extraction = acquire(seed)
    print(json.dumps({'stage': 'acquired', 'seed': seed, 'splits': splits}), flush=True)
    tick = time.process_time()
    local = count_model([g['cases'] for g in parts['fit']], shuffled=False, seed=seed)
    thresholds, cal, _ = calibrate([g['cases'] for g in parts['calibration']],
                                    local, 'treatment')
    local_cpu = time.process_time() - tick
    tick = time.process_time()
    education, excluded = frames(parts['fit'], seed)
    joint = JointConstructions.learn(education)
    shuffled_frames, _ = frames(parts['fit'], seed, shuffled=True)
    shuffled = JointConstructions.learn(shuffled_frames)
    model_path = ROOT / f'.leobot-data/g71_joint_{which}.json'
    model_path.write_text(json.dumps(joint.payload()))
    restored = JointConstructions(**json.loads(model_path.read_text()))
    # A bijection across all observable symbols tests structure, not spellings.
    key_list = sorted({case[0] for groups in parts.values()
                       for group in groups for case in group['cases']})
    rng = random.Random(seed ^ 0xBAD)
    key_names = [f'z{i}' for i in range(len(key_list))]
    rng.shuffle(key_names)
    rename_keys = dict(zip(key_list, key_names))
    rename_roles = {role: f'r{i}' for i, role in enumerate(reversed(ROLES))}
    renamed = joint.renamed(rename_keys, rename_roles)
    construction_cpu = time.process_time() - tick
    tick = time.process_time()
    metrics, controls, search, latencies = evaluate(
        parts['development'], local, thresholds, joint, shuffled, restored, renamed,
        rename_keys, rename_roles)
    evaluation_cpu = time.process_time() - tick
    cpu = time.process_time() - cpu0
    wall = time.monotonic() - wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    b, j, s = (metrics[name] for name in ('independent', 'joint', 'shuffled'))
    budget = (acquisition + extraction <= 120 and local_cpu + construction_cpu <= 300
              and evaluation_cpu <= 180 and wall <= 900 and rss <= 1024**2)
    gates = {
        'f1_gain': j['f1'] >= b['f1'] + .03,
        'precision': j['precision'] >= b['precision'],
        'a2': j['roles']['A2']['f1'] >= b['roles']['A2']['f1'],
        'exact_gain': j['exact_rate'] >= b['exact_rate'] + .05,
        'shuffled_gain': j['f1'] >= s['f1'] + .03,
        'controls': not (controls['restart_mismatches'] or controls['renaming_mismatches']),
        'latency': latencies['joint']['p95_ms'] < 5, 'budget': budget,
        'sample': all(splits[name]['groups'] > 0 for name in parts),
    }
    final_hashes = fingerprint()
    if hashes != final_hashes:
        raise RuntimeError('Las fuentes cambiaron durante el ensayo')
    out = {'experiment': 'G-71', 'partition': which, 'seed': seed,
           'scope': 'development; supplied syntax and predicate; no kiosk claims',
           'engine_sha': ENGINE, 'sources_sha256': hashes, 'frozen_after': True,
           'data_sha256': {'up': UP_SHA, 'ud': UD_SHA},
           'splits': splits, 'source_counts': counts, 'thresholds': thresholds,
           'calibration': cal, 'excluded_frames': excluded,
           'constructions': len(joint.patterns), 'shuffled_constructions': len(shuffled.patterns),
           'teaching_frames': len(education), 'search': search, 'controls': controls,
           'metrics': metrics, 'latency': latencies, 'gates': gates, 'passes': all(gates.values()),
           'cost': {'acquisition_cpu_s': acquisition, 'extraction_cpu_s': extraction,
                    'local_fit_and_calibration_cpu_s': local_cpu,
                    'construction_compile_and_reload_cpu_s': construction_cpu,
                    'evaluation_and_controls_cpu_s': evaluation_cpu,
                    'total_cpu_s': cpu, 'wall_s': wall, 'peak_rss_kib': rss,
                    'model_bytes': model_path.stat().st_size}}
    path = ROOT / f'results_v3/g71_development_{which}.json'
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'result': str(path), 'gates': gates, 'cpu_s': cpu,
                      'f1': {k: v['f1'] for k, v in metrics.items()}}), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))

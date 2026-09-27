"""G-72: learn verb/construction compatibility from disjoint documents."""
from __future__ import annotations

import itertools
import json
import math
import random
import resource
import sys
import time
from collections import Counter, defaultdict
from hashlib import sha256

from experiments import g71_joint_constructions as g71
from experiments.g22_ancora_source_gate import index_up, sentences, token_id
from experiments.g23_role_paths import doc_id, nodes_from_ud, predicate_cases
from experiments.g24_calibrated_roles import calibrate, choice, compact, count_model, logits, prior

ROOT, ENGINE, NONE, ROLES = g71.ROOT, g71.ENGINE, g71.NONE, g71.ROLES
OPTIONS = (0, 16, 4, 1)  # Zero means the shared inventory, first on exact ties.


def fingerprint():
    names = ['experiments/g72_compatibility.py', 'experiments/g71_joint_constructions.py',
             'experiments/g22_ancora_source_gate.py', 'experiments/g23_role_paths.py',
             'experiments/g24_calibrated_roles.py', 'prereg/G-72-compatibilidad-aprendida.md']
    if g71.git('rev-parse', 'HEAD:leobot') != ENGINE:
        raise RuntimeError('Motor incorrecto')
    if g71.git('status', '--porcelain', '--', 'leobot', *names):
        raise RuntimeError('Fuentes sin congelar')
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def structural_profiles(seed):
    """Semantic columns never enter this channel, including for known verbs."""
    up, _ = index_up((ROOT / '.leobot-data/g71_ancora_up.conllup').read_bytes())
    profiles = defaultdict(Counter)
    docs, counts = set(), Counter()
    with (ROOT / '.leobot-data/g71_ancora_ud.conllu').open() as handle:
        for sid, _, rows in sentences(handle):
            doc = doc_id(sid)
            if not doc or not g71.residue(seed, 'doc', doc) or not g71.residue(seed, 'caldoc', doc):
                continue
            entry = up.get(sid)
            if entry is None or tuple(r[0] for r in rows if len(r) >= 3 and token_id(r[0])) != entry[0]:
                continue
            nodes = nodes_from_ud(rows)
            if not nodes:
                continue
            for annotation in entry[1]:
                predicate = annotation[0]  # Only the supplied predicate position.
                node = nodes.get(predicate)
                if not node or node['upos'] != 'VERB' or node['lemma'] in ('_', ''):
                    continue
                expanded, _, _, _ = predicate_cases(nodes, predicate, '')
                profiles[node['lemma']].update(keys['full'] for _, keys, _ in expanded)
                docs.add(doc)
                counts['predicates'] += 1
                counts['candidates'] += len(expanded)
                if counts['candidates'] > 2_000_000 or len(profiles) > 5000:
                    raise RuntimeError('Presupuesto del canal estructural agotado')
    df = Counter(key for counts_ in profiles.values() for key in counts_)
    vectors = {}
    for lemma, counts_ in profiles.items():
        total = sum(counts_.values())
        weights = {key: (n / total) * math.log1p(len(profiles) / df[key])
                   for key, n in counts_.items()}
        norm = math.sqrt(sum(v * v for v in weights.values()))
        vectors[lemma] = {key: v / norm for key, v in weights.items()} if norm else {}
    return vectors, docs, dict(counts)


def verb_constructions(groups, seed, joint):
    ids = {pattern: idx for idx, (pattern, _) in enumerate(joint.patterns)}
    observed = defaultdict(set)
    for group in groups:
        frame, _ = g71.frames([group], seed)
        if frame:
            pattern = g71.JointConstructions.learn(frame).patterns[0][0]
            observed[group['lemma']].add(ids[pattern])
    return dict(observed)


def neighbors(vectors, observed):
    inverted = defaultdict(list)
    for lemma in sorted(observed):
        for key, value in vectors.get(lemma, {}).items():
            inverted[key].append((lemma, value))
    closest = {}
    multiplications = 0
    for lemma, vector in vectors.items():
        products = defaultdict(float)
        for key, value in vector.items():
            for other, other_value in inverted.get(key, ()):
                products[other] += value * other_value
                multiplications += 1
        closest[lemma] = sorted(products, key=lambda other: (-products[other], other))[:16]
    return closest, multiplications


def compile_allowed(closest, observed, k):
    if k == 0:
        return {}
    return {lemma: set().union(*(observed[other] for other in others[:k]))
            for lemma, others in closest.items() if others}


def score(groups, local, thresholds, joint, allowed, *, independent=False,
          rename_keys=None, rename_roles=None, rename_verbs=None):
    base = prior(local)
    pairs, predictions, latencies = [], [], []
    missed, search = Counter(), Counter()
    exact = 0
    reverse = {v: k for k, v in (rename_roles or {}).items()}
    for group in groups:
        cases = group['cases']
        tick = time.perf_counter()
        values = [logits(local, case, 'treatment', base) for case in cases]
        if independent:
            answer = tuple(choice(value, thresholds) for value in values)
        else:
            keys = [case[0] for case in cases]
            margins = [{} if value is None else
                       {role: value[i] - thresholds[i] for i, role in enumerate(ROLES)}
                       for value in values]
            lemma = group['lemma']
            if rename_keys is not None:
                keys = [rename_keys[key] for key in keys]
                margins = [{rename_roles[r]: v for r, v in row.items()} for row in margins]
                lemma = rename_verbs[lemma]
            answer, used = joint.predict(keys, margins, allowed=allowed.get(lemma))
            search.update(used)
            if rename_keys is not None:
                answer = tuple(reverse.get(r, r) for r in answer)
        latencies.append(group['feature_ms'] + (time.perf_counter() - tick) * 1000)
        observations = list(zip(answer, (case[4] for case in cases)))
        pairs.extend(observations)
        missed.update(group['missed_roles'])
        exact += (not group['missed_roles'] and all(a == b for a, b in observations))
        predictions.append(answer)
    result = g71.metric(pairs, missed, exact, len(groups))
    result['prediction_sha256'] = sha256(json.dumps(predictions).encode()).hexdigest()
    return result, predictions, g71.timing(latencies), dict(search)


def main(which):
    if which not in (0, 1):
        raise ValueError('Usar 0 o 1')
    resource.setrlimit(resource.RLIMIT_CPU, (600, 610))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes = fingerprint()
    cpu0, wall0 = time.process_time(), time.monotonic()
    seed = int(ENGINE[:8], 16) ^ 0x7100 ^ which
    parts, splits, source_counts, acquisition, extraction = g71.acquire(seed)
    tick = time.process_time()
    vectors, docs, channel_counts = structural_profiles(seed)
    channel_cpu = time.process_time() - tick
    for part in ('calibration', 'development'):
        if docs & {g['doc'] for g in parts[part]}:
            raise RuntimeError('El canal adicional vio documentos excluidos')
    print(json.dumps({'stage': 'acquired', 'seed': seed, 'verbs': len(vectors)}), flush=True)
    tick = time.process_time()
    local = count_model([g['cases'] for g in parts['fit']], shuffled=False, seed=seed)
    thresholds, _, _ = calibrate([g['cases'] for g in parts['calibration']], local, 'treatment')
    teaching, excluded = g71.frames(parts['fit'], seed)
    joint = g71.JointConstructions.learn(teaching)
    observed = verb_constructions(parts['fit'], seed, joint)
    nearest, operations = neighbors(vectors, observed)
    shuffled_keys = sorted(vectors)
    random.Random(seed ^ 0x72).shuffle(shuffled_keys)
    shuffled_vectors = dict(zip(sorted(vectors), (vectors[k] for k in shuffled_keys)))
    false_nearest, false_operations = neighbors(shuffled_vectors, observed)
    calibration = {}
    chosen, best = 0, -1
    for k in OPTIONS:
        allowed = compile_allowed(nearest, observed, k)
        result, _, _, _ = score(parts['calibration'], local, thresholds, joint, allowed)
        calibration[str(k)] = result
        if result['f1'] > best:
            chosen, best = k, result['f1']
    allowed = compile_allowed(nearest, observed, chosen)
    confused = compile_allowed(false_nearest, observed, chosen)
    path = ROOT / f'.leobot-data/g72_compatibility_{which}.json'
    path.write_text(json.dumps({lemma: sorted(ids) for lemma, ids in allowed.items()}))
    restored = {lemma: set(ids) for lemma, ids in json.loads(path.read_text()).items()}
    compile_cpu = time.process_time() - tick
    tick = time.process_time()
    metrics, predictions, latency, search = {}, {}, {}, {}
    for name, index in (('independent', {}), ('shared', {}), ('treatment', allowed),
                        ('confused', confused), ('reloaded', restored)):
        metrics[name], predictions[name], latency[name], search[name] = score(
            parts['development'], local, thresholds, joint, index, independent=name == 'independent')
    all_keys = sorted({case[0] for groups in parts.values() for g in groups for case in g['cases']})
    all_verbs = sorted(set(allowed) | {g['lemma'] for g in parts['development']})
    key_names = [f'x{i}' for i in range(len(all_keys))]
    verb_names = [f'y{i}' for i in range(len(all_verbs))]
    rng = random.Random(seed ^ 0x7200)
    rng.shuffle(key_names)
    rng.shuffle(verb_names)
    rename_keys = dict(zip(all_keys, key_names))
    rename_verbs = dict(zip(all_verbs, verb_names))
    rename_roles = {role: f'r{i}' for i, role in enumerate(reversed(ROLES))}
    renamed_joint = joint.renamed(rename_keys, rename_roles)
    opaque_allowed = {rename_verbs[lemma]: ids for lemma, ids in allowed.items()}
    _, opaque_predictions, _, _ = score(
        parts['development'], local, thresholds, renamed_joint, opaque_allowed,
        rename_keys=rename_keys, rename_roles=rename_roles, rename_verbs=rename_verbs)
    controls = {'restart_mismatches': sum(a != b for a, b in zip(predictions['treatment'], predictions['reloaded'])),
                'rename_mismatches': sum(a != b for a, b in zip(predictions['treatment'], opaque_predictions))}
    historical = json.loads((ROOT / f'results_v3/g71_development_{which}.json').read_text())
    for current, old in (('independent', 'independent'), ('shared', 'joint')):
        # The output digest serialization differs; verify actual outcome counts.
        for key in ('tp', 'fp', 'fn', 'exact', 'f1'):
            if metrics[current][key] != historical['metrics'][old][key]:
                raise RuntimeError('La extensión cambió la referencia G-71')
    controls['g71_outcome_counts_unchanged'] = True
    evaluation_cpu = time.process_time() - tick
    cpu, wall = time.process_time() - cpu0, time.monotonic() - wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    b, shared, t, confused_result = (metrics[name] for name in ('independent', 'shared', 'treatment', 'confused'))
    budget = (acquisition + extraction + channel_cpu <= 120 and compile_cpu <= 300
              and evaluation_cpu <= 180 and wall <= 900 and rss <= 1024**2)
    gates = {'f1': t['f1'] >= max(b['f1'], shared['f1']) + .03,
             'confused': t['f1'] >= confused_result['f1'] + .03,
             'precision': t['precision'] >= max(b['precision'], shared['precision']),
             'a2': t['roles']['A2']['f1'] >= max(b['roles']['A2']['f1'], shared['roles']['A2']['f1']),
             'exact': t['exact_rate'] >= max(b['exact_rate'], shared['exact_rate']) + .05,
             'controls': not controls['restart_mismatches'] and not controls['rename_mismatches'],
             'latency': latency['treatment']['p95_ms'] < 5, 'budget': budget}
    if fingerprint() != hashes:
        raise RuntimeError('Cambio de fuentes durante el ensayo')
    report = {'experiment': 'G-72', 'scope': 'development; supplied syntax/predicate; no kiosk claims',
              'partition': which, 'seed': seed, 'engine_sha': ENGINE, 'sources_sha256': hashes,
              'frozen_after': True, 'splits': splits, 'source_counts': source_counts,
              'channel': {**channel_counts, 'verbs': len(vectors), 'docs': len(docs),
                          'development_verbs_with_prior_unlabelled_syntax': len(set(vectors) & {g['lemma'] for g in parts['development']}),
                          'development_groups_with_prior_unlabelled_syntax': sum(g['lemma'] in vectors for g in parts['development']),
                          'development_groups_with_compiled_index': sum(g['lemma'] in allowed for g in parts['development'])},
              'calibration': calibration, 'chosen_neighbors': chosen, 'thresholds': thresholds,
              'constructions': len(joint.patterns), 'verbs_with_supervised_constructions': len(observed),
              'compiled_links': sum(len(ids) for ids in allowed.values()),
              'excluded_frames': excluded, 'metrics': metrics, 'controls': controls,
              'latency': latency, 'search': search, 'gates': gates, 'passes': all(gates.values()),
              'cost': {'acquisition_cpu_s': acquisition, 'supervised_extraction_cpu_s': extraction,
                       'unlabelled_channel_cpu_s': channel_cpu,
                       'learning_compilation_calibration_cpu_s': compile_cpu,
                       'evaluation_and_controls_cpu_s': evaluation_cpu, 'total_cpu_s': cpu,
                       'wall_s': wall, 'peak_rss_kib': rss, 'model_bytes': path.stat().st_size,
                       'similarity_products': operations, 'confused_similarity_products': false_operations}}
    output = ROOT / f'results_v3/g72_development_{which}.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'path': str(output), 'chosen_neighbors': chosen, 'gates': gates,
                      'cpu_s': cpu, 'f1': {k: v['f1'] for k, v in metrics.items()}}), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))

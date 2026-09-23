"""G-25: learned case markers plus a surface-only conditional role probe."""
from __future__ import annotations

import itertools
import json
import math
import os
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
    ROLES, UD_SHA, UP_SHA, core_heads, doc_id, nodes_from_ud,
    predicate_cases, split_residue,
)
from experiments.g24_calibrated_roles import (
    GRID, LABELS, calibrate as calibrate_two, choice, count_model,
    count_outcomes, logits as logits_two, posterior, prior,
)
from leobot.language import normalize


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-25-enlace-lexico-y-superficie.md'
SEEDS = (1487, 1559)


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g25_lexical_surface.py',
                        'experiments/g24_calibrated_roles.py',
                        'experiments/g23_role_paths.py'))


def case_markers(nodes):
    markers = defaultdict(list)
    for token_id_, value in nodes.items():
        if value['deprel'] == 'case' and value['head'] in nodes:
            lexical = normalize(value['lemma'] if value['lemma'] != '_' else value['form'])
            if lexical:
                markers[value['head']].append((int(token_id_), lexical))
    return {head: '|'.join(word for _, word in sorted(values)[:2])
            for head, values in markers.items()}


def structured_cases(nodes, predicate, head_field, *, marker_mode):
    expanded, gold, represented, _ = predicate_cases(nodes, predicate, head_field)
    markers = case_markers(nodes)
    out = []
    used_markers = set()
    for candidate, keys, label in expanded:
        marker = (markers.get(candidate, '_') if marker_mode == 'lexical'
                  else 'CONST')
        used_markers.add(marker)
        out.append((sys.intern(keys['full']+'|case='+marker),
                    sys.intern(keys['full']),
                    sys.intern(keys['path']),
                    sys.intern(keys['side']), label))
    return tuple(out), gold, represented, used_markers


def remap_case(case, kind):
    full, middle, general, side, label = case
    if kind == 'constant':
        return (sys.intern(middle+'|case=CONST'), middle, general, side, label)
    if kind == 'baseline':
        return (middle, general, general, side, label)
    if kind == 'position':
        return (sys.intern(general+'|<masked>|<masked>'),
                sys.intern(general+'|<masked>'), general, side, label)
    return case


def mapped_pack(pack, kind):
    if kind in ('structured', 'surface'):
        return pack
    return {'train': [tuple(remap_case(case, kind) for case in group)
                      for group in pack['train']],
            'test': [tuple(remap_case(case, kind) for case in group)
                     for group in pack['test']],
            'feature_ms': pack['feature_ms']}


def distance_bucket(distance):
    if distance <= 3:
        return str(distance)
    return '4-7' if distance <= 7 else '8-32'


def surface_cases(nodes, predicate, head_field, *, lexical):
    ordered = sorted(nodes, key=int)
    positions = {token: index for index, token in enumerate(ordered)}
    if predicate not in positions:
        return (), 0, 0
    ppos = positions[predicate]
    # The learner sees words and a marked target, never the tree or UD classes.
    forms = [normalize(nodes[token]['form']) for token in ordered]
    forms[ppos] = '<pred>'
    gold_heads = core_heads(head_field)
    total_gold = sum(len(labels) for head, labels in gold_heads.items()
                     if head in nodes)
    represented = 0
    cases = []
    for index, token in enumerate(ordered):
        distance = abs(index-ppos)
        if not 1 <= distance <= 32:
            continue
        labels = gold_heads.get(token, ())
        if len(labels) > 1:
            continue
        label = next(iter(labels)) if labels else 'NONE'
        if label != 'NONE':
            represented += 1
        side = 'L' if index < ppos else 'R'
        root = side+':'+distance_bucket(distance)
        prev1 = forms[index-1] if index >= 1 else '<start>'
        prev2 = forms[index-2] if index >= 2 else '<start>'
        if not lexical:
            prev1 = prev2 = '<masked>'
        cases.append((sys.intern(root+'|'+prev2+'|'+prev1),
                      sys.intern(root+'|'+prev1),
                      sys.intern(root),
                      sys.intern(side), label))
    return tuple(cases), total_gold, represented


def logits_three(model, case, base):
    tables = model['tables']
    full, nfull = posterior(tables['full'], case[0], base)
    middle, nmiddle = posterior(tables['path'], case[1], base)
    general, ngeneral = posterior(tables['direct'], case[2], base)
    if not (nfull or nmiddle or ngeneral):
        return None
    wmid = nmiddle/(nmiddle+8)
    middle_mix = {label: wmid*middle[label]+(1-wmid)*general[label]
                  for label in LABELS}
    wfull = nfull/(nfull+8)
    probs = {label: wfull*full[label]+(1-wfull)*middle_mix[label]
             for label in LABELS}
    absent = probs['NONE']
    return tuple(math.log(probs[role]/absent) for role in ROLES)


def calibrate_three(groups, model):
    base = prior(model)
    pairs = [(logits_three(model, case, base), case[4])
             for group in groups for case in group]
    chosen = None
    for thresholds in itertools.product(GRID, repeat=3):
        metric = count_outcomes(pairs, thresholds)
        rank = (metric['micro_f1'], thresholds)
        if chosen is None or rank > chosen[0]:
            chosen = (rank, thresholds, metric)
    return tuple(chosen[1]), chosen[2], len(pairs)


def scored_labels(predictions, gold):
    pairs = ((None if predicted == 'NONE' else
              tuple(1.0 if role == predicted else -1.0 for role in ROLES),
              expected)
             for predicted, expected in zip(predictions, gold))
    return count_outcomes(pairs, (0, 0, 0))


def evaluate(test, feature_ms, models, thresholds, *, baseline=False):
    if len(test) != len(feature_ms):
        raise RuntimeError('Faltan tiempos de extracción')
    names = ('treatment', 'shuffled', 'memory', 'fresh')
    if baseline:
        names = ('baseline',)
    outputs = {name: [] for name in names}
    digests = {name: sha256() for name in names}
    exact = Counter()
    latencies = []
    bases = {name: prior(model) for name, model in models.items()}
    for group, extraction in zip(test, feature_ms):
        tick = time.perf_counter()
        if baseline:
            candidate = [choice(logits_two(models['baseline'], case, 'treatment',
                                            bases['baseline']), thresholds['baseline'])
                         for case in group]
        else:
            candidate = [choice(logits_three(models['treatment'], case,
                                              bases['treatment']),
                                thresholds['treatment']) for case in group]
        latencies.append(extraction+(time.perf_counter()-tick)*1000)
        predictions = {names[0]: candidate}
        if not baseline:
            for name in ('shuffled',):
                predictions[name] = [
                    choice(logits_three(models[name], case, bases[name]),
                           thresholds[name]) for case in group]
            predictions['memory'] = ['NONE']*len(group)
            predictions['fresh'] = ['NONE']*len(group)
        for name in names:
            values = predictions[name]
            exact[name] += all(value == case[4]
                               for value, case in zip(values, group))
            for value in values:
                outputs[name].append(value)
                digests[name].update((value+'\n').encode())
    gold = [case[4] for group in test for case in group]
    results = {}
    for name in names:
        result = scored_labels(outputs[name], gold)
        result['exact_candidate_labels'] = exact[name]
        result['prediction_sha256'] = digests[name].hexdigest()
        results[name] = result
    ordered = sorted(latencies)
    return results, {
        'p50_ms': statistics.median(ordered) if ordered else None,
        'p95_ms': ordered[int((len(ordered)-1)*.95)] if ordered else None,
        'max_ms': max(ordered) if ordered else None,
    }


def source_stream(up, seed, data, stats, groups):
    used = 0
    digest = sha256()
    with urlopen(UD_URL, timeout=20) as response:
        size = int(response.headers.get('Content-Length', 0))
        if size > 48*1024*1024:
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
            ids = tuple(row[0] for row in rows if len(row) >= 3 and token_id(row[0]))
            if ids != entry[0]:
                stats['token_id_mismatches'] += 1
                continue
            doc = doc_id(sid)
            if doc is None:
                stats['missing_document_id'] += 1
                continue
            nodes = nodes_from_ud(rows)
            if nodes is None:
                stats['invalid_tree'] += 1
                continue
            dres = split_residue(seed, 'doc', doc)
            cdoc = split_residue(seed, 'caldoc', doc)
            for predicate, _, head_field, _ in entry[1]:
                verb = nodes.get(predicate)
                if verb is None or verb['upos'] != 'VERB':
                    stats['nonverb_or_missing'] += 1
                    continue
                lemma = verb['lemma']
                if lemma in ('_', ''):
                    stats['missing_lemma'] += 1
                    continue
                lres = split_residue(seed, 'lemma', lemma)
                if dres == lres == 0:
                    partition = 'test'
                elif dres != 0 and lres != 0:
                    partition = 'train'
                else:
                    stats['cross_ignored'] += 1
                    continue
                tick = time.perf_counter()
                structured, gold_s, represented_s, markers = structured_cases(
                    nodes, predicate, head_field, marker_mode='lexical')
                structured_ms = (time.perf_counter()-tick)*1000
                tick = time.perf_counter()
                surface, gold_r, represented_r = surface_cases(
                    nodes, predicate, head_field, lexical=True)
                surface_ms = (time.perf_counter()-tick)*1000
                stats['candidate_cases'] += len(structured)+len(surface)
                if stats['candidate_cases'] > 3_000_000:
                    raise RuntimeError('Se agotó límite de candidatas')
                stats['predicates_'+partition] += 1
                stats['gold_structured_'+partition] += gold_s
                stats['represented_structured_'+partition] += represented_s
                stats['gold_surface_'+partition] += gold_r
                stats['represented_surface_'+partition] += represented_r
                groups[partition]['markers'].update(markers)
                groups[partition]['docs'].add(doc)
                groups[partition]['lemmas'].add(lemma)
                if partition == 'test':
                    gold_heads = set(core_heads(head_field))
                    opaque = {key: {**value,
                                    'form': ('z'+key if (key == predicate or
                                             key in gold_heads) and
                                             value['deprel'] != 'case' else value['form']),
                                    'lemma': ('opaque' if (key == predicate or
                                              key in gold_heads) and
                                              value['deprel'] != 'case' else value['lemma'])}
                              for key, value in nodes.items()}
                    opaque_struct, _, _, _ = structured_cases(
                        opaque, predicate, head_field, marker_mode='lexical')
                    stats['structured_rename_failures'] += opaque_struct != structured
                    opaque_raw, _, _ = surface_cases(
                        opaque, predicate, head_field, lexical=True)
                    # Only the target verb is masked in the surface representation;
                    # changed argument words are a diagnostic, not an invariance gate.
                    verb_only = {key: ({**value, 'form': 'z'+key} if key == predicate
                                       else value) for key, value in nodes.items()}
                    masked_verb, _, _ = surface_cases(
                        verb_only, predicate, head_field, lexical=True)
                    stats['surface_verb_rename_failures'] += masked_verb != surface
                    stats['surface_content_changed_predicates'] += opaque_raw != surface
                    for name, cases in (('structured', structured),
                                        ('surface', surface)):
                        data[name]['test'].append(cases)
                    data['structured']['feature_ms'].append(structured_ms)
                    data['surface']['feature_ms'].append(surface_ms)
                else:
                    idx = len(data['structured']['train'])
                    for name, cases in (('structured', structured),
                                        ('surface', surface)):
                        data[name]['train'].append(cases)
                    clres = split_residue(seed, 'callemma', lemma)
                    if cdoc == clres == 0:
                        groups['calibration']['indices'].append(idx)
                        stats['calibration_gold'] += represented_s
                    elif cdoc != 0 and clres != 0:
                        groups['fit']['indices'].append(idx)
                    else:
                        stats['internal_cross_ignored'] += 1
    stats['up_without_ud'] = len(up)
    return used, digest.hexdigest()


def train_and_calibrate(data, indices_fit, indices_cal, seed, *, two_levels=False):
    fit = [data['train'][i] for i in indices_fit]
    cal = [data['train'][i] for i in indices_cal]
    normal_fit = count_model(fit, shuffled=False, seed=seed)
    shuffled_fit = count_model(fit, shuffled=True, seed=seed)
    if two_levels:
        selected, metric, cases = calibrate_two(cal, normal_fit, 'treatment')
        thresholds = {'baseline': selected}
        calibration = {'baseline': {'metric': metric, 'cases': cases}}
        models = {'baseline': count_model(data['train'], shuffled=False, seed=seed)}
    else:
        thresholds = {}
        calibration = {}
        for name, model in (('treatment', normal_fit),
                            ('shuffled', shuffled_fit)):
            selected, metric, cases = calibrate_three(cal, model)
            thresholds[name] = selected
            calibration[name] = {'metric': metric, 'cases': cases}
        models = {'treatment': count_model(data['train'], shuffled=False, seed=seed),
                  'shuffled': count_model(data['train'], shuffled=True, seed=seed)}
    return models, thresholds, calibration


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
    download_cpu = time.process_time()-cpu0
    tick = time.process_time()
    up, _ = index_up(raw)
    del raw
    up_index_cpu = time.process_time()-tick

    data = {name: {'train': [], 'test': [], 'feature_ms': []}
            for name in ('structured', 'surface')}
    stats = Counter()
    groups = {name: {'docs': set(), 'lemmas': set(), 'markers': set(), 'indices': []}
              for name in ('train', 'test', 'fit', 'calibration')}
    tick = time.process_time()
    ud_bytes, ud_hash = source_stream(up, seed, data, stats, groups)
    stream_cpu = time.process_time()-tick
    if ud_hash != UD_SHA:
        raise RuntimeError('UD cambió')
    fit_idx = groups['fit']['indices']
    cal_idx = groups['calibration']['indices']
    sample_ok = (len(cal_idx) >= 300 and stats['calibration_gold'] >= 400
                 and stats['predicates_test'] >= 400
                 and len(groups['test']['lemmas']) >= 20
                 and stats['represented_structured_test'] >= 500)
    tick = time.process_time()
    models = {}
    thresholds = {}
    calibration = {}
    for name in ('structured', 'constant', 'baseline', 'surface', 'position'):
        base = data['surface' if name in ('surface', 'position') else 'structured']
        pack = mapped_pack(base, name)
        two = name == 'baseline'
        models[name], thresholds[name], calibration[name] = train_and_calibrate(
            pack, fit_idx, cal_idx, seed, two_levels=two)
        if pack is not base:
            del pack
    # The constant-marker and position-only ablations use identical training
    # episodes and candidate sets; their own calibrated thresholds are allowed.
    calibration_cpu = time.process_time()-tick
    tick = time.process_time()
    packed = {'models': models, 'thresholds': thresholds}
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json') as stream:
        json.dump(packed, stream, sort_keys=True, ensure_ascii=False)
        stream.flush()
        stream.seek(0)
        restored = json.load(stream)
    restart_same = restored == json.loads(json.dumps(packed))
    models, thresholds = restored['models'], restored['thresholds']
    persistence_cpu = time.process_time()-tick
    tick = time.process_time()
    results = {}
    latencies = {}
    for name in ('structured', 'constant', 'baseline', 'surface', 'position'):
        base = data['surface' if name in ('surface', 'position') else 'structured']
        pack = mapped_pack(base, name)
        result, latency = evaluate(pack['test'], pack['feature_ms'],
                                   models[name], thresholds[name],
                                   baseline=name == 'baseline')
        results[name] = result
        latencies[name] = latency
        if pack is not base:
            del pack
    inference_cpu = time.process_time()-tick

    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    case_f1 = results['structured']['treatment']['micro_f1']
    oracle_controls = max(
        results['baseline']['baseline']['micro_f1'],
        results['constant']['treatment']['micro_f1'],
        results['structured']['shuffled']['micro_f1'])
    raw_f1 = results['surface']['treatment']['micro_f1']
    raw_controls = max(results['position']['treatment']['micro_f1'],
                       results['surface']['shuffled']['micro_f1'])
    oracle_gate = (case_f1 >= .65 and case_f1-oracle_controls >= .08
                   and results['structured']['treatment']['roles']['A0']['f1'] >= .60
                   and results['structured']['treatment']['roles']['A1']['f1'] >= .60
                   and results['structured']['treatment']['roles']['A2']['f1'] >= .40
                   and case_f1-results['structured']['shuffled']['micro_f1'] >= .15)
    raw_gate = (raw_f1 >= .45 and raw_f1-raw_controls >= .10
                and results['surface']['treatment']['roles']['A2']['f1'] >= .25
                and raw_f1-results['surface']['shuffled']['micro_f1'] >= .15)
    budget = (cpu <= 90 and wall <= 150 and rss <= 256*1024
              and stats['candidate_cases'] <= 3_000_000)
    unchanged = frozen()
    pass_ = (budget and sample_ok and oracle_gate and raw_gate
             and latencies['structured']['p95_ms'] is not None
             and latencies['structured']['p95_ms'] <= 10
             and latencies['surface']['p95_ms'] is not None
             and latencies['surface']['p95_ms'] <= 10
             and stats['structured_rename_failures'] == 0
             and stats['surface_verb_rename_failures'] == 0
             and restart_same and unchanged)
    output = {
        'kind': 'G25_lexical_and_surface_role_gate',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_sha256': {'up': UP_SHA, 'ud': ud_hash},
        'source_bytes': {'up': up_bytes, 'ud': ud_bytes},
        'seed': seed,
        'counts': dict(stats),
        'split': {'train_documents': len(groups['train']['docs']),
                  'train_lemmas': len(groups['train']['lemmas']),
                  'test_documents': len(groups['test']['docs']),
                  'test_lemmas': len(groups['test']['lemmas']),
                  'fit_predicates': len(fit_idx),
                  'calibration_predicates': len(cal_idx)},
        'marker_vocabulary': {'train': len(groups['train']['markers']),
                              'test': len(groups['test']['markers'])},
        'thresholds': thresholds,
        'calibration': calibration,
        'results': results,
        'latencies': latencies,
        'restart_same': restart_same,
        'oracle_gate': oracle_gate,
        'raw_gate': raw_gate,
        'sample_ok': sample_ok,
        'budget_ok': budget,
        'gate_pass': pass_,
        'up_download_cpu_s': round(download_cpu, 6),
        'up_index_cpu_s': round(up_index_cpu, 6),
        'ud_stream_training_cpu_s': round(stream_cpu, 6),
        'calibration_and_refit_cpu_s': round(calibration_cpu, 6),
        'persistence_cpu_s': round(persistence_cpu, 6),
        'inference_cpu_s': round(inference_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
    }
    path = ROOT / ('results_v3/g25_lexical_surface_seed'+str(seed)
                   +'_hashseed'+os.environ.get('PYTHONHASHSEED', 'unset')+'.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: value for key, value in output.items()
                      if key not in ('results', 'calibration')},
                     ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante ensayo')


if __name__ == '__main__':
    main(int(sys.argv[1]))

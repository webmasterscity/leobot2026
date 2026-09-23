"""G-22: source viability of aligned Spanish UP/UD semantic roles."""
from __future__ import annotations

import io
import json
import os
import re
import resource
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from experiments.f7_typed_sequences_dev import git


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-22-fuente-papeles-verbales.md'
H0 = '1f3187f2ced4c97364503187d074815f33612326'
UP_REV = '7a03859143e52c57f94a8c0480c0e6d433f6a91f'
UD_REV = '20adddbfcdd773c6dc97ba48ea11ca9364e74185'
UP_URL = ('https://raw.githubusercontent.com/UniversalPropositions/'
          f'UP_Spanish-AnCora/{UP_REV}/es_ancora-up-train.conllup')
UD_URL = ('https://raw.githubusercontent.com/UniversalDependencies/'
          f'UD_Spanish-AnCora/{UD_REV}/es_ancora-ud-train.conllu')


def frozen():
    return (git('rev-parse', 'HEAD:leobot') == H0
            and not git('status', '--porcelain', '--', 'leobot')
            and not git('status', '--porcelain', '--',
                        'experiments/g22_ancora_source_gate.py'))


def download(url, cap):
    with urlopen(url, timeout=20) as response:
        length = int(response.headers.get('Content-Length', 0))
        if length > cap:
            raise RuntimeError('Archivo supera el tamaño preregistrado')
        data = response.read(cap + 1)
    if not data or len(data) > cap:
        raise RuntimeError('Fuente vacía o superior al presupuesto')
    return data


def sentences(data):
    sid = None
    text_present = False
    rows = []
    for line in io.StringIO(data.decode('utf-8-sig')):
        line = line.rstrip('\n\r')
        if not line:
            if sid is not None or rows:
                yield sid, text_present, rows
            sid = None
            text_present = False
            rows = []
            continue
        if line.startswith('# sent_id = '):
            sid = line[len('# sent_id = '):].strip()
        elif line.startswith('# text = '):
            text_present = bool(line[len('# text = '):].strip())
        elif not line.startswith('#'):
            rows.append(line.split('\t'))
    if sid is not None or rows:
        yield sid, text_present, rows


def token_id(value):
    return bool(re.fullmatch(r'[1-9][0-9]*', value))


def index_up(data):
    by_id = {}
    stats = Counter()
    for sid, _, rows in sentences(data):
        stats['up_sentences'] += 1
        if not sid:
            stats['up_missing_sent_id'] += 1
            continue
        if sid in by_id:
            stats['up_duplicate_sent_id'] += 1
            continue
        ids = []
        predicates = []
        for row in rows:
            if len(row) < 4:
                stats['up_short_token_rows'] += 1
                continue
            if not token_id(row[0]):
                continue
            ids.append(row[0])
            if row[1] not in ('_', ''):
                predicates.append((row[0], row[1], row[2], row[3]))
        by_id[sid] = (tuple(ids), predicates)
        stats['up_tokens'] += len(ids)
        stats['up_predicate_rows'] += len(predicates)
    return by_id, stats


def annotations(field):
    if field in ('_', ''):
        return []
    out = []
    for item in field.split('|'):
        if ':' not in item:
            out.append((None, item))
        else:
            out.append(tuple(item.rsplit(':', 1)))
    return out


def inspect_pair(ud_ids, lemma_by_id, predicates, counts, role_lemmas,
                 role_predicates, senses, lemmas):
    id_set = set(ud_ids)
    for predicate_id, sense, head_field, span_field in predicates:
        counts['predicate_instances'] += 1
        senses.add(sense)
        if predicate_id not in id_set:
            counts['predicate_token_missing'] += 1
            continue
        lemma = lemma_by_id.get(predicate_id, '_')
        if lemma not in ('_', ''):
            lemmas.add(lemma)
        head_by_role = defaultdict(list)
        for role, head in annotations(head_field):
            head_by_role[role].append(head)
        for role, span in annotations(span_field):
            counts['argument_annotations'] += 1
            valid = (role is not None and
                     re.fullmatch(r'([1-9][0-9]*)-([1-9][0-9]*)', span))
            if valid:
                start, end = map(int, span.split('-'))
                valid = (start <= end and str(start) in id_set and str(end) in id_set
                         and any(head in id_set for head in head_by_role.get(role, ())))
            if not valid:
                counts['invalid_argument_annotations'] += 1
                continue
            counts['valid_argument_annotations'] += 1
            counts['role:' + role] += 1
            role_predicates[role] += 1
            if lemma not in ('_', ''):
                role_lemmas[role].add(lemma)


def inspect_ud(data, up):
    counts = Counter()
    role_lemmas = defaultdict(set)
    role_predicates = Counter()
    senses = set()
    lemmas = set()
    for sid, text_present, rows in sentences(data):
        counts['ud_sentences'] += 1
        if not sid:
            counts['ud_missing_sent_id'] += 1
            continue
        item = up.pop(sid, None)
        if item is None:
            counts['ud_without_up'] += 1
            continue
        counts['paired_sentences'] += 1
        counts['paired_with_text'] += bool(text_present)
        ids = tuple(row[0] for row in rows if len(row) >= 3 and token_id(row[0]))
        if ids != item[0]:
            counts['token_id_mismatch_sentences'] += 1
            continue
        counts['paired_token_ids_equal'] += 1
        lemma_by_id = {row[0]: row[2] for row in rows
                       if len(row) >= 3 and token_id(row[0])}
        inspect_pair(ids, lemma_by_id, item[1], counts, role_lemmas,
                     role_predicates, senses, lemmas)
    counts['up_without_ud'] = len(up)
    shared_roles = [role for role in role_predicates
                    if len(role_lemmas[role]) >= 20 and role_predicates[role] >= 100]
    return counts, senses, lemmas, role_lemmas, role_predicates, shared_roles


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    if not frozen():
        raise RuntimeError('Motor o evaluador no congelado')
    up_raw = download(UP_URL, 20*1024*1024)
    ud_raw = download(UD_URL, 40*1024*1024)
    sizes = {'up': len(up_raw), 'ud': len(ud_raw)}
    hashes = {'up': sha256(up_raw).hexdigest(), 'ud': sha256(ud_raw).hexdigest()}
    read_cpu = time.process_time()-cpu0

    tick = time.process_time()
    up, up_stats = index_up(up_raw)
    del up_raw
    counts, senses, lemmas, role_lemmas, role_predicates, shared_roles = inspect_ud(
        ud_raw, up)
    del ud_raw, up
    parse_cpu = time.process_time()-tick
    counts.update(up_stats)
    paired = counts['paired_sentences']
    args = counts['argument_annotations']
    alignment = counts['paired_token_ids_equal']/counts['up_sentences'] if counts['up_sentences'] else 0
    valid = counts['valid_argument_annotations']/args if args else 0
    cpu, wall = time.process_time()-cpu0, time.monotonic()-wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget = cpu <= 15 and wall <= 45 and rss <= 128*1024
    gate = (budget and counts['paired_with_text'] >= 5000
            and counts['predicate_instances'] >= 1000
            and args >= 5000 and alignment >= .95 and valid >= .90
            and len(lemmas) >= 100 and len(shared_roles) >= 3)
    unchanged = frozen()
    output = {
        'kind': 'G22_source_gate_only',
        'preregistration': PREREG,
        'evaluator_commit': git('rev-parse', 'HEAD'),
        'engine_tree': H0,
        'engine_unchanged': unchanged,
        'source_revisions': {'up': UP_REV, 'ud': UD_REV},
        'source_bytes': sizes,
        'source_sha256': hashes,
        'counts': dict(counts),
        'senses': len(senses),
        'predicate_lemmas': len(lemmas),
        'role_lemma_counts': {role: len(values)
                              for role, values in sorted(role_lemmas.items())},
        'role_predicate_counts': dict(sorted(role_predicates.items())),
        'shared_roles': sorted(shared_roles),
        'sentence_token_alignment': alignment,
        'valid_argument_fraction': valid,
        'download_cpu_s': round(read_cpu, 6),
        'parse_cpu_s': round(parse_cpu, 6),
        'cpu_total_s': round(cpu, 6),
        'wall_total_s': round(wall, 6),
        'max_rss_kib': rss,
        'budget_ok': budget,
        'gate_pass': gate and unchanged,
    }
    path = ROOT / ('results_v3/g22_ancora_source_hashseed'
                   + os.environ.get('PYTHONHASHSEED', 'unset') + '.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False), flush=True)
    if not unchanged:
        raise RuntimeError('Motor o evaluador cambió durante ensayo')


if __name__ == '__main__':
    main()

"""External acquisition/schema inspection of Predicate Matrix 1.3."""
import json
import resource
import sys
import tarfile
import time
import io
import subprocess
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.leobot-data/g73b'
URL = 'https://adimen.ehu.eus/web/files/PredicateMatrix/PredicateMatrix.v1.3.tar.gz'
ENGINE = '11a1ef5836382d81a643cad0b217a8669ce0f2d1'


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / 'predicate_matrix.tar.gz'
    if path.exists():
        raise RuntimeError('No sobrescribir datos adquiridos')
    cpu0, wall0 = time.process_time(), time.monotonic()
    attempts = []
    raw = b''
    for _ in range(2):
        try:
            with urlopen(URL, timeout=20) as response:
                if int(response.headers.get('Content-Length', 0)) > 64 * 1024**2:
                    raise RuntimeError('Descarga supera 64 MiB')
                parts, size = [], 0
                while chunk := response.read(1024 * 1024):
                    parts.append(chunk)
                    size += len(chunk)
                    if size > 64 * 1024**2 or time.monotonic() - wall0 > 120:
                        raise RuntimeError('Presupuesto de descarga agotado')
                raw = b''.join(parts)
                final_url = response.url
            attempts.append({'ok': True, 'tls_verified': True})
            break
        except URLError as exc:
            attempts.append({'ok': False, 'error': str(exc), 'tls_verified': True})
    report = {'url': URL, 'attempts': attempts, 'available': bool(raw),
              'cpu_s': time.process_time() - cpu0, 'wall_s': time.monotonic() - wall0}
    if raw:
        path.write_bytes(raw)
        report.update(final_url=final_url, bytes=len(raw), sha256=sha256(raw).hexdigest())
    (ROOT / 'results_v3/g73b_download.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


def schema():
    meta = json.loads((ROOT / 'results_v3/g73b_download.json').read_text())
    path = CACHE / 'predicate_matrix.tar.gz'
    if sha256(path.read_bytes()).hexdigest() != meta['sha256']:
        raise RuntimeError('Cambio de fuente')
    total, members = 0, []
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            total += member.size
            if total > 512 * 1024**2 or len(members) >= 20_000:
                raise RuntimeError('Presupuesto de archivo expandido agotado')
            members.append({'name': member.name, 'bytes': member.size})
            if member.isfile():
                stream = archive.extractfile(member)
                # Read text documentation/header only; never extract or execute.
                preview = stream.read(min(member.size, 16000)).decode('utf8', 'replace')
                (CACHE / ('preview_' + str(len(members)) + '.txt')).write_text(preview)
                print(json.dumps({'member': member.name, 'bytes': member.size,
                                  'preview': preview[:10000]}))
    (ROOT / 'results_v3/g73b_members.json').write_text(json.dumps(members, indent=2) + '\n')


def fingerprint():
    sources = ['experiments/g73b_predicate_source.py', 'prereg/G-73b-fuente-correspondencias.md']
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *sources):
        raise RuntimeError('Motor o lector sin congelar')
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}


def count():
    frozen = fingerprint()
    cpu0, wall0 = time.process_time(), time.monotonic()
    meta = json.loads((ROOT / 'results_v3/g73b_download.json').read_text())
    path = CACHE / 'predicate_matrix.tar.gz'
    if sha256(path.read_bytes()).hexdigest() != meta['sha256']:
        raise RuntimeError('Cambio de fuente')
    counts, language_pos, index_counts = Counter(), Counter(), Counter()
    predicates, role_predicates = defaultdict(set), defaultdict(set)
    projected = {'n': defaultdict(set), 'v': defaultdict(set)}
    missing_projection = {'n': set(), 'v': set()}
    row_digests = set()
    with tarfile.open(path, 'r:gz') as archive:
        member = archive.getmember('PredicateMatrix.v1.3/PredicateMatrix.v1.3.txt')
        if member.size > 512 * 1024**2:
            raise RuntimeError('Tabla demasiado grande')
        stream = io.TextIOWrapper(archive.extractfile(member), encoding='utf8')
        header = stream.readline().rstrip('\r\n').split('\t')
        required = ('1_ID_LANG', '2_ID_POS', '3_ID_PRED', '4_ID_ROLE',
                    '16_PB_ROLESET', '17_PB_ARG')
        if len(header) != 27 or any(name not in header for name in required):
            raise RuntimeError('Encabezado desconocido')
        columns = {name: header.index(name) for name in required}
        for line in stream:
            if time.monotonic() - wall0 > 300:
                raise RuntimeError('Tiempo de inspección agotado')
            fields = line.rstrip('\r\n').split('\t')
            if not line.strip():
                counts['blank_rows'] += 1
                continue
            counts['rows'] += 1
            if len(fields) != 27:
                counts['invalid_columns'] += 1
                continue
            values = [field.split(':', 1)[-1] for field in fields]
            lang, pos, pred, role, pb_pred, pb_role = (values[columns[name]] for name in required)
            if any(v in ('NULL', '') for v in (lang, pos, pred)):
                counts['invalid_identity'] += 1
                continue
            counts['valid_rows'] += 1
            digest = sha256(line.rstrip('\r\n').encode()).digest()
            if digest in row_digests:
                counts['exact_duplicate_rows'] += 1
            row_digests.add(digest)
            index_counts[(lang, pos, pred, role)] += 1
            language_pos[(lang, pos)] += 1
            predicates[(lang, pos)].add(pred)
            if lang != 'spa' or pos not in projected:
                continue
            if role not in ('NULL', ''):
                role_predicates[(pos, role)].add(pred)
            if any(value in ('NULL', '') for value in (pb_pred, pb_role, role)):
                missing_projection[pos].add((pred, role))
                continue
            projected[pos][(pb_pred, pb_role)].add((pred, role))
    nouns_to_verbs, aligned_role_nouns = defaultdict(set), defaultdict(set)
    shared_roles = set(projected['n']) & set(projected['v'])
    aligned_nominal_slots, aligned_verbal_slots = set(), set()
    for common in sorted(shared_roles):
        verb_slots = projected['v'][common]
        for noun, role in projected['n'][common]:
            nouns_to_verbs[noun].update(verb for verb, _ in verb_slots)
            aligned_role_nouns[role].add(noun)
            aligned_nominal_slots.add((noun, role))
        aligned_verbal_slots.update(verb_slots)
    gate = len(nouns_to_verbs) >= 200 and sum(len(v) >= 50 for v in aligned_role_nouns.values()) >= 3
    cpu, wall = time.process_time() - cpu0, time.monotonic() - wall0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if fingerprint() != frozen:
        raise RuntimeError('Fuentes cambiadas durante inspección')
    report = {
        'experiment': 'G-73b', 'scope': 'source inspection, no trained model or kiosk evaluation',
        'engine_sha': ENGINE, 'sources_sha256': frozen, 'archive_sha256': meta['sha256'],
        'frozen_after': True, 'license_in_readme': 'CC BY 3.0', 'table_bytes': member.size,
        'counts': dict(counts), 'unique_rows': len(row_digests),
        'unique_four_field_indices': len(index_counts),
        'indices_with_multiple_rows': sum(v > 1 for v in index_counts.values()),
        'language_pos': {f'{lang}:{pos}': {'rows': n, 'predicates': len(predicates[(lang, pos)])}
                         for (lang, pos), n in sorted(language_pos.items())},
        'spanish_role_predicates': {f'{pos}:{role}': len(v) for (pos, role), v in sorted(role_predicates.items())},
        'spanish_slots_missing_projection': {pos: len(v) for pos, v in missing_projection.items()},
        'spanish_common_predicate_role_keys': len(shared_roles),
        'spanish_nominal_predicates_with_join_candidates': len(nouns_to_verbs),
        'spanish_nominal_slots_aligned': len(aligned_nominal_slots),
        'spanish_verbal_slots_aligned': len(aligned_verbal_slots),
        'spanish_join_candidate_pairs': sum(len(v) for v in nouns_to_verbs.values()),
        'nominal_predicates_with_multiple_verb_candidates': sum(len(v) > 1 for v in nouns_to_verbs.values()),
        'verb_candidates_per_nominal_histogram': dict(sorted(Counter(len(v) for v in nouns_to_verbs.values()).items())),
        'aligned_role_nominal_predicates': {role: len(v) for role, v in sorted(aligned_role_nouns.items())},
        'direct_nominal_to_origin_verb_field': False,
        'spanish_human_questions_or_sentences': 0,
        'content_gate': gate, 'budget_ok': cpu <= 120 and wall <= 300 and rss <= 512 * 1024,
        'cost': {'inspection_cpu_s': cpu, 'inspection_wall_s': wall, 'peak_rss_kib': rss,
                 'download_cpu_s': meta['cpu_s'], 'download_wall_s': meta['wall_s']},
        'limits': ['Projected joins are candidates, not human-verified equivalences.',
                   'Multiple rows per source index include alternative alignments.',
                   'No operational learning; G-73 original corpus gate still unevaluated.'],
    }
    output = ROOT / 'results_v3/g73b_content.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    {'download': download, 'schema': schema, 'count': count}[sys.argv[1]]()

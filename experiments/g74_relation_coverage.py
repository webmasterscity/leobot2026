"""Optimistic availability bound, never an answerer or a learned result."""
from collections import Counter, defaultdict
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import resource
import subprocess
import tarfile
import time

from leobot import Bot
from experiments.g57_kiosco import businesses, contains, plain
from experiments.g68_confianza import DEV

ROOT = Path(__file__).resolve().parents[1]
ENGINE = '11a1ef5836382d81a643cad0b217a8669ce0f2d1'
BASE_SHA = '6fff61c20fcd5812d785eec22b6c595e19568f98ec31559e689c7fb95fe6d79f'
PM_SHA = '4630d1c9aa74e1012238167d43d0a6707589dad8873993d1c023d6e69652f781'


def frozen():
    paths = ['experiments/g74_relation_coverage.py', 'prereg/G-74-alcance-de-relaciones.md']
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *paths):
        raise RuntimeError('Motor o evaluador sin congelar')
    return {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def inventory(bot):
    path = ROOT / '.leobot-data/g73b/predicate_matrix.tar.gz'
    if sha256(path.read_bytes()).hexdigest() != PM_SHA:
        raise RuntimeError('Fuente distinta')
    raw = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    stats = Counter()
    term_cache = {}
    with tarfile.open(path, 'r:gz') as archive:
        file = archive.extractfile('PredicateMatrix.v1.3/PredicateMatrix.v1.3.txt')
        for line in io.TextIOWrapper(file, encoding='utf8'):
            values = [v.split(':', 1)[-1] for v in line.rstrip('\r\n').split('\t')]
            if len(values) != 27 or values[0] != 'spa' or values[1] not in ('n', 'v'):
                continue
            stats['spanish_rows'] += 1
            match = re.fullmatch(r'(.+)\.[0-9]+(?:\..+)?', values[2])
            if match is None:
                stats['unrecognized_predicate_format_rows'] += 1
                continue
            lemma = match.group(1)
            if lemma not in term_cache:
                terms = bot.context_terms(lemma)
                term_cache[lemma] = terms[0] if len(terms) == 1 else None
            term = term_cache[lemma]
            if term is None:
                stats['multiword_rows_outside_token_family'] += 1
                continue
            if values[15] == 'NULL':
                stats['no_common_predicate_rows'] += 1
                continue
            raw[term][values[15]][values[1]].add(values[16])
    result = {term: {frame: {pos: frozenset(roles - {'NULL'}) for pos, roles in poss.items()}
                     for frame, poss in frames.items()} for term, frames in raw.items()}
    stats['terms'] = len(result)
    stats['term_frame_links'] = sum(len(v) for v in result.values())
    return result, dict(stats)


def prepare(terms, mapping):
    by_frame = defaultdict(list)
    for term in sorted(set(terms)):
        for frame, pos in mapping.get(term, {}).items():
            by_frame[frame].append((term, pos))
    return set(terms), by_frame


def new_links(question_terms, prepared, mapping):
    answer_terms, by_frame = prepared
    lexical = role = nominal = False
    for q in sorted(set(question_terms) - answer_terms):
        for frame, qpos in mapping.get(q, {}).items():
            for a, apos in by_frame.get(frame, ()):
                lexical = True
                for qp, qr in qpos.items():
                    for ap, ar in apos.items():
                        if qr & ar:
                            role = True
                            nominal |= qp != ap
    return lexical, role, nominal


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (240, 245))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    before = frozen()
    begin, wall0 = time.process_time(), time.monotonic()
    base = ROOT / '.leobot-data/base_kiosco.json'
    if sha256(base.read_bytes()).hexdigest() != BASE_SHA:
        raise RuntimeError('Base distinta')
    bot = Bot.load(base)
    mapping, source = inventory(bot)
    acquisition = time.process_time() - begin
    t = time.process_time()
    counts, banks = Counter(), defaultdict(Counter)
    for bank in DEV:
        folder = ROOT / 'results_v3/kiosco' / bank
        for _, text, instructions, conversations in businesses(sorted(p for p in folder.iterdir() if p.is_dir())):
            bot.load_context(text, instructions)
            units = bot.context_units
            prepared = [prepare(bot.context_terms(u['text'] + (' ' + u['heading'] if u.get('inherited') else '')), mapping)
                        for u in units]
            for conversation in conversations:
                history = []
                for turn in conversation:
                    q = turn['cliente']
                    reply = bot.answer(q, history)
                    history.extend((q, reply['text']))
                    action = turn.get('accion', 'responder')
                    keys = [k for k in turn.get('claves', []) or [] if plain(k)]
                    if action == 'charla' or reply['status'] == 'phatic' or (action not in ('abstenerse', 'derivar') and not keys):
                        continue
                    _, question = bot._question_part(q)
                    terms = bot.context_terms(question)
                    signals = [new_links(terms, p, mapping) for p in prepared]
                    said = reply['status'] in ('answered', 'closest')
                    if action in ('abstenerse', 'derivar'):
                        counts['absent'] += 1
                        counts['baseline_absent_quotes'] += said
                        counts['absent_with_potential_lexical_signal'] += any(s[0] for s in signals)
                        counts['absent_with_potential_role_signal'] += any(s[1] for s in signals)
                    if action != 'responder' or turn.get('tipo') not in ('directa', 'si_no'):
                        continue
                    good = [all(contains(u['text'], key) for key in keys) for u in units]
                    useful = said and all(contains(reply['text'], key) for key in keys)
                    row = {'core': 1, 'baseline_useful': useful, 'literal_unit_exists': any(good),
                           'question_with_mapped_term': any(w in mapping for w in terms)}
                    for j, name in enumerate(('lexical', 'role', 'nominal')):
                        potential = any(g and s[j] for g, s in zip(good, signals))
                        row[name + '_gold_evidence'] = potential
                        row[name + '_optimistic_useful'] = useful or potential
                        row[name + '_possible_gain'] = potential and not useful
                    counts.update(row)
                    banks[bank].update(row)
    if (counts['core'], counts['baseline_useful'], counts['absent'], counts['baseline_absent_quotes']) != (816, 269, 488, 74):
        raise RuntimeError('La referencia pública no reproduce los conteos históricos')
    validation = time.process_time() - t
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    after = frozen()
    if before != after:
        raise RuntimeError('Cambio durante la prueba')
    report = {'experiment': 'G-74', 'scope': 'spent development; optimistic availability only',
              'engine_sha': ENGINE, 'sources_sha256': before, 'engine_unchanged': True,
              'base_sha256': BASE_SHA, 'matrix_sha256': PM_SHA, 'source': source,
              'counts': dict(counts), 'banks': {k: dict(v) for k, v in banks.items()},
              'can_alone_reach_60_in_this_family': counts['role_optimistic_useful'] / counts['core'] >= .6,
              'enough_possible_gain_for_learner': counts['role_possible_gain'] / counts['core'] >= .05,
              'cost': {'acquisition_cpu_s': acquisition, 'validation_cpu_s': validation,
                       'total_cpu_s': time.process_time() - begin,
                       'wall_s': time.monotonic() - wall0, 'peak_rss_kib': rss},
              'budget_ok': acquisition <= 120 and validation <= 120 and rss <= 1024**2}
    path = ROOT / 'results_v3/g74_relation_coverage.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

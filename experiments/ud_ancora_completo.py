"""Medida fija: UD Spanish-AnCora test COMPLETO con el evaluador oficial CoNLL 2018.

python3 -m experiments.ud_ancora_completo ANCORA_DIR CONLL18_UD_EVAL.py OUT.json

- Educación sintáctica con `es_ancora-ud-train.conllu` (como G-32c/G-35).
- Predicción sobre `es_ancora-ud-test.conllu` completo (SHA-256 679f1c05…),
  con la tokenización de referencia: se reemplazan UPOS, HEAD y DEPREL y se deja
  todo lo demás igual.
- Oraciones más largas que el tope del analizador: árbol de reserva válido (la
  primera palabra es la raíz y las demás dependen de ella); se informan aparte.
- Métricas con `conll18_ud_eval.py` (UPOS, UAS, LAS), p50/p95 por oración y RAM.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_SHA = '679f1c05ca654aa26801c80319df45f8f97606718fb534b91755b48f3e67fa6f'


def sentences(path: Path):
    """Yield (lines, word_rows) per sentence; word_rows index lines of word tokens."""
    block = []
    for line in path.read_text(encoding='utf8').split('\n'):
        if line.strip():
            block.append(line); continue
        if block:
            rows = [i for i, l in enumerate(block) if not l.startswith('#')
                    and '-' not in l.split('\t')[0] and '.' not in l.split('\t')[0]]
            yield block, rows
            block = []


def main():
    ancora, evaluator, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    test = ancora / 'es_ancora-ud-test.conllu'
    if hashlib.sha256(test.read_bytes()).hexdigest() != TEST_SHA:
        raise RuntimeError('El archivo de prueba no es el acordado.')
    from leobot import Bot
    bot = Bot(); t0 = time.process_time()
    for block, rows in sentences(ancora / 'es_ancora-ud-train.conllu'):
        cols = [block[i].split('\t') for i in rows]
        bot.observe_parsed_sentence([c[1] for c in cols], [c[3] for c in cols], [int(c[6]) for c in cols],
                                    [c[7].split(':')[0] for c in cols])
    bot.consolidate_syntax(); education_cpu = time.process_time() - t0
    predicted, times, fallback, n = [], [], 0, 0
    for block, rows in sentences(test):
        cols = [block[i].split('\t') for i in rows]
        words = [c[1] for c in cols]
        t = time.perf_counter(); parse = bot.parse_words(words); times.append((time.perf_counter() - t) * 1000)
        n += 1
        if not parse or parse.get('status') != 'parsed_syntax':
            fallback += 1
            tags = bot.tag_words(words) or ['X'] * len(words)
            heads = [0] + [1] * (len(words) - 1)
            labels = ['root'] + ['dep'] * (len(words) - 1)
        else:
            tags, heads = parse['tags'], parse['heads']
            labels = parse.get('labels') or ['dep'] * len(words)
            labels = ['root' if h == 0 else lab for h, lab in zip(heads, labels)]
        block = list(block)
        for k, i in enumerate(rows):
            c = block[i].split('\t')
            c[3], c[6], c[7] = tags[k], str(heads[k]), labels[k]
            c[4] = c[5] = c[8] = '_'
            block[i] = '\t'.join(c)
        predicted.append('\n'.join(block))
    system = out.with_suffix('.conllu')
    system.write_text('\n\n'.join(predicted) + '\n\n', encoding='utf8')
    spec = importlib.util.spec_from_file_location('conll18_ud_eval', evaluator)
    ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
    gold_ud = ev.load_conllu_file(str(test)); system_ud = ev.load_conllu_file(str(system))
    scores = ev.evaluate(gold_ud, system_ud)
    times.sort()
    report = {'engine_tree': subprocess.check_output(('git', 'rev-parse', 'HEAD:leobot'), cwd=ROOT, text=True).strip(),
              'test_sha256': TEST_SHA, 'evaluator_sha256': hashlib.sha256(evaluator.read_bytes()).hexdigest(),
              'sentences': n, 'fallback_too_long': fallback,
              'UPOS': round(scores['UPOS'].f1, 4), 'UAS': round(scores['UAS'].f1, 4), 'LAS': round(scores['LAS'].f1, 4),
              'parse_ms_p50': round(times[len(times) // 2], 2), 'parse_ms_p95': round(times[int(0.95 * len(times))], 2),
              'education_cpu_s': round(education_cpu, 1),
              'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

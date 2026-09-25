"""G-52: lectura en 2400 casos nuevos de SQuAD-es v1.1 `dev` (excluidos los de G-47b, G-49 y G-51).

python3 -m experiments.g52_lectura_squad_es BASE.json OUT.json

Fuente: https://raw.githubusercontent.com/ccasimiro88/TranslateAlignRetrieve/master/SQuAD-es-v1.1/dev-v1.1-es.json
(traducción automática del SQuAD v1.1 `dev`; 10 570 preguntas; SHA-256 fijado abajo).  El fondo MLQA no visto se
agotó en G-47.  Se excluyen, en orden, los 600 de G-47b, G-49 y G-51 (cada uno con la semilla de su congelado,
sobre lo que quedaba); muestra de 2400 con la semilla de `freeze-G-52` (con 600, el error típico de la diferencia con
el lector superaba la tolerancia).  Variantes: G-52 (con G-53); sus tres ablaciones juntas; sin G-53; las cuatro; lector de G-28 solo.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
import urllib.request
from hashlib import sha256
from pathlib import Path

from experiments.g28b_gap_correspondences import scored, summary
from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://raw.githubusercontent.com/ccasimiro88/TranslateAlignRetrieve/master/SQuAD-es-v1.1/dev-v1.1-es.json'
SHA = '969c846df740ee2725ac23b4d2882a58ef19a4c696767b306227c243ed99f461'
CACHE = Path('/tmp/squad_es_dev_v1.1.json')


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def cases():
    data = CACHE.read_bytes() if CACHE.exists() else urllib.request.urlopen(URL, timeout=60).read()
    if sha256(data).hexdigest() != SHA:
        raise RuntimeError('SQuAD-es cambió.')
    out = []
    for article in json.loads(data)['data']:
        for paragraph in article['paragraphs']:
            for qa in paragraph['qas']:
                out.append({'id': qa['id'], 'context': paragraph['context'], 'question': qa['question'],
                            'answers': [a['text'] for a in qa['answers']]})
    return sorted(out, key=lambda r: r['id'])


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    frozen = git('rev-parse', 'freeze-G-52:leobot')
    if frozen != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    pool = cases()
    for tag in ('freeze-G-47b', 'freeze-G-49', 'freeze-G-51'):
        used = {r['id'] for r in random.Random(int(git('rev-parse', f'{tag}:leobot')[:8], 16)).sample(pool, 600)}
        pool = [r for r in pool if r['id'] not in used]
    seed = int(frozen[:8], 16)
    sample = random.Random(seed).sample(pool, 2400)
    template = Bot.load(base)
    report = {'huella_motor': frozen, 'semilla': seed, 'casos': len(sample), 'fuente': URL, 'sha256': SHA}
    for name, syntax, switches in (('g52', True, {}),
                                   ('ablacion', True, {'predicate_gap': False, 'negative_concord': False,
                                                       'plural_subjects': False}),
                                   ('sin_answer_kind_G53', True, {'answer_kind': False}),
                                   ('sin_las_cuatro', True, {'predicate_gap': False, 'negative_concord': False,
                                                             'plural_subjects': False, 'answer_kind': False}),
                                   ('solo_lector_g28', False, {})):
        results, times = [], []
        for case in sample:
            bot = Bot(); bot.reading_model = template.reading_model
            if syntax:
                bot.syntax_model = template.syntax_model
            for k, v in switches.items():
                setattr(bot, k, v)
            bot.ingest_document_text(case['context'], source=f'caso:{case["id"]}')
            t = time.perf_counter(); reply = bot.respond(case['question']); times.append((time.perf_counter() - t) * 1000)
            results.append(scored(reply.get('text', '') if reply.get('status') == 'literal' else '', case))
        times.sort()
        report[name] = {**summary(results), 'p95_ms': round(times[int(0.95 * len(times))], 2)}
        print(name, json.dumps(report[name]), flush=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')


if __name__ == '__main__':
    main()

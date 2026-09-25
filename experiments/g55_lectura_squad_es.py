"""G-55 y G-56: lectura en 2400 casos nuevos de SQuAD-es v1.1 `dev` (excluidos los de G-47b, G-49, G-51, G-52 y G-54).

python3 -m experiments.g55_lectura_squad_es BASE.json OUT.json

Misma fuente y SHA-256 que `g54_lectura_squad_es`.  Se excluyen, en orden, los 600 de G-47b, G-49 y G-51, los 2400
de G-52 y los 2400 de G-54 (cada uno con la semilla de su congelado, sobre lo que quedaba); muestra de 2400 con la
semilla de `freeze-G-55`.  Variantes: G-55 y G-56; sus interruptores apagados; lector de G-28 solo.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import scored, summary
from experiments.g54_lectura_squad_es import SHA, URL, cases, git
from leobot import Bot

OFF = ('kind_contrast', 'gap_phrase', 'optional_words', 'core_links', 'named_conjuncts')


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    frozen = git('rev-parse', 'freeze-G-55:leobot')
    if frozen != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    pool = cases()
    for tag in ('freeze-G-47b', 'freeze-G-49', 'freeze-G-51'):
        used = {r['id'] for r in random.Random(int(git('rev-parse', f'{tag}:leobot')[:8], 16)).sample(pool, 600)}
        pool = [r for r in pool if r['id'] not in used]
    for tag in ('freeze-G-52', 'freeze-G-54'):
        used = {r['id'] for r in random.Random(int(git('rev-parse', f'{tag}:leobot')[:8], 16)).sample(pool, 2400)}
        pool = [r for r in pool if r['id'] not in used]
    seed = int(frozen[:8], 16)
    sample = random.Random(seed).sample(pool, 2400)
    template = Bot.load(base)
    report = {'huella_motor': frozen, 'semilla': seed, 'casos': len(sample), 'fuente': URL, 'sha256': SHA}
    for name, syntax, switches in (('g55_g56', True, {}),
                                   ('sin_G55_G56', True, {k: False for k in OFF}),
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

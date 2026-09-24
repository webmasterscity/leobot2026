"""G-43: lectura MLQA en una muestra NO vista, con el bot educado completo.

python3 -m experiments.g43_mlqa_reserva BASE.json OUT.json

300 casos de MLQA español cuyo contexto no está en la educación (2000) ni en
los 300 visibles de desarrollo, elegidos con la semilla de `freeze-G-43`
(primeros 8 hex de su huella).  Variantes: G-43; sin clase de respuesta; y el
lector de G-28 solo (sin sintaxis), en la misma muestra.  Motor congelado.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import EDU_SEED, archive, rows, scored, summary
from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    frozen = git('rev-parse', 'freeze-G-43:leobot')
    if frozen != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    test = rows(archive(), 'MLQA_V1/test/test-context-es-question-es.json')
    rng = random.Random(EDU_SEED); chosen = rng.sample(test, 2300)
    edu_contexts = {r['context'] for r in chosen[:2000]}
    visible = [r for r in rng.sample(test, len(test)) if r['context'] not in edu_contexts][:300]
    used = edu_contexts | {r['context'] for r in visible}
    pool = sorted((r for r in test if r['context'] not in used), key=lambda r: r['id'])
    seed = int(frozen[:8], 16)
    sample = random.Random(seed).sample(pool, 300)
    template = Bot.load(base)
    report = {'huella_motor': frozen, 'semilla': seed, 'casos': len(sample), 'pool': len(pool)}
    for name, syntax, classes in (('g43', True, True), ('sin_clase', True, False), ('solo_lector_g28', False, True)):
        results, times = [], []
        for case in sample:
            bot = Bot(); bot.reading_model = template.reading_model
            if syntax:
                bot.syntax_model = template.syntax_model
            bot.answer_classes = classes
            bot.ingest_document_text(case['context'], source=f'caso:{case["id"]}')
            t = time.perf_counter(); reply = bot.respond(case['question']); times.append((time.perf_counter() - t) * 1000)
            results.append(scored(reply.get('text', '') if reply.get('status') == 'literal' else '', case))
        times.sort()
        report[name] = {**summary(results), 'p95_ms': round(times[int(0.95 * len(times))], 2)}
        print(name, json.dumps(report[name]), flush=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')


if __name__ == '__main__':
    main()

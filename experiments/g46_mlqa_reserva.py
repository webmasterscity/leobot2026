"""G-46: lectura MLQA en 600 casos NO vistos, con el bot educado completo.

python3 -m experiments.g46_mlqa_reserva BASE.json OUT.json

Casos cuyo contexto no está en la educación, en los 300 visibles de desarrollo
ni en el tramo chosen[2000:2300] que G-28 usó como desarrollo (salvedad de la
auditoría de G-45), ni en las muestras de G-43, G-43b, G-44b y G-45; semilla
de `freeze-G-46`.  Variantes: G-46; ablación (sin contraste); lector de G-28 solo.
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
    frozen = git('rev-parse', 'freeze-G-46:leobot')
    if frozen != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    test = rows(archive(), 'MLQA_V1/test/test-context-es-question-es.json')
    rng = random.Random(EDU_SEED); chosen = rng.sample(test, 2300)
    used = {r['context'] for r in chosen[:2000]}
    visible = [r for r in rng.sample(test, len(test)) if r['context'] not in used][:300]
    used |= {r['context'] for r in visible}
    pool = sorted((r for r in test if r['context'] not in used), key=lambda r: r['id'])
    for tag, size in (('freeze-G-43', 300), ('freeze-G-43b', 300), ('freeze-G-44b', 600), ('freeze-G-45', 600)):
        earlier = random.Random(int(git('rev-parse', f'{tag}:leobot')[:8], 16)).sample(pool, size)
        used |= {r['context'] for r in earlier}
        pool = [r for r in pool if r['context'] not in used]
    # Also out: the stretch G-28 used as visible development.
    used |= {r['context'] for r in chosen[2000:]}
    pool = [r for r in pool if r['context'] not in used]
    seed = int(frozen[:8], 16)
    sample = random.Random(seed).sample(pool, min(600, len(pool)))
    template = Bot.load(base)
    report = {'huella_motor': frozen, 'semilla': seed, 'casos': len(sample), 'pool': len(pool)}
    for name, syntax, switches in (('g46', True, {}), ('ablacion', True, {'contrast_answers': False}),
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

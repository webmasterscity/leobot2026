"""G-47: lectura MLQA en los casos de la partición `dev` nunca usados.

python3 -m experiments.g47_mlqa_reserva BASE.json OUT.json

El fondo de `test` no visto se agotó en G-46b.  De `dev` se excluyen la porción
fija del tablero AGI y las reservas de G-28 y G-28b (identificadas por sus
resultados guardados); quedan 105 casos, todos usados, en el orden de la
semilla de `freeze-G-47`.  Variantes: G-47; los tres interruptores apagados;
lector de G-28 solo.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

from experiments.g28_reading_alignment import BOARD_SEED
from experiments.g28b_gap_correspondences import archive, rows, scored, summary
from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]
USED = ('g28b_gap_correspondences_724065320_hashseed0.json', 'g28b_gap_correspondences_991163547_hashseed0.json',
        'g28_reading_alignment_2867501594_hashseed0.json')


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    frozen = git('rev-parse', 'freeze-G-47:leobot')
    if frozen != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    dev = rows(archive(), 'MLQA_V1/dev/dev-context-es-question-es.json')
    used = {r['id'] for r in random.Random(BOARD_SEED).sample(dev, 20)}
    for name in USED:
        used |= {r['id'] for r in json.loads((ROOT / 'results_v3' / name).read_text(encoding='utf8'))['rows']}
    pool = sorted((r for r in dev if r['id'] not in used), key=lambda r: r['id'])
    seed = int(frozen[:8], 16)
    sample = random.Random(seed).sample(pool, len(pool))
    template = Bot.load(base)
    report = {'huella_motor': frozen, 'semilla': seed, 'casos': len(sample)}
    for name, syntax, switches in (('g47', True, {}),
                                   ('los_tres_apagados', True, {'reference_resolution': False, 'same_fact': False,
                                                                'answer_type': False}),
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

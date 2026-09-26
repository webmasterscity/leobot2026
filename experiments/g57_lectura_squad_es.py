"""G-57: lectura en 2400 casos nuevos de SQuAD-es v1.1 `dev` (excluidos los de G-47b, G-49, G-51, G-52, G-54 y G-55).

python3 -m experiments.g57_lectura_squad_es BASE.json OUT.json   (cwd = el repositorio del motor que se mide)

Misma fuente y SHA-256 que `g54_lectura_squad_es`; todos los que quedan (1570; el preregistro decía 2400), en el orden de la semilla de `freeze-G-57`.
- `respond`: la vía de siempre (`ingest_document_text` + `respond`), F1 de tramos: no debe bajar más de 0,005
  frente a `estable-G-15`.
- `unidad` (solo si el motor tiene `load_context`): la mejor unidad del contexto sin silencio calibrado; se
  cuenta si contiene la respuesta (acierto de oración) y su F1 contra la respuesta.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import scored, summary
from experiments.g54_lectura_squad_es import SHA, URL, cases
from leobot import Bot

FROZEN = '80d543096ddb2be8a5c145fb175e9c769fe39952'   # freeze-G-57:leobot


def git(*args):
    return subprocess.check_output(('git', *args), text=True).strip()


def plain(text):
    import unicodedata, re
    t = unicodedata.normalize('NFKD', str(text).lower())
    return ' '.join(re.findall(r'[a-z0-9ñ]+', ''.join(c for c in t if not unicodedata.combining(c))))


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    engine = git('rev-parse', 'HEAD:leobot')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor tiene cambios sin commit.')
    pool = cases()
    for tag in ('freeze-G-47b', 'freeze-G-49', 'freeze-G-51'):
        used = {r['id'] for r in random.Random(int(git('rev-parse', f'{tag}:leobot')[:8], 16)).sample(pool, 600)}
        pool = [r for r in pool if r['id'] not in used]
    for tag in ('freeze-G-52', 'freeze-G-54', 'freeze-G-55'):
        used = {r['id'] for r in random.Random(int(git('rev-parse', f'{tag}:leobot')[:8], 16)).sample(pool, 2400)}
        pool = [r for r in pool if r['id'] not in used]
    seed = int(FROZEN[:8], 16)
    # Solo quedan 1570 casos sin usar: se usan todos (el preregistro decía 2400).
    sample = random.Random(seed).sample(pool, min(2400, len(pool)))
    template = Bot.load(base)
    report = {'huella_motor': engine, 'semilla': seed, 'casos': len(sample), 'fuente': URL, 'sha256': SHA}
    results, times = [], []
    for case in sample:
        bot = Bot(); bot.reading_model = template.reading_model; bot.syntax_model = template.syntax_model
        bot.ingest_document_text(case['context'], source=f'caso:{case["id"]}')
        t = time.perf_counter(); reply = bot.respond(case['question']); times.append((time.perf_counter() - t) * 1000)
        results.append(scored(reply.get('text', '') if reply.get('status') == 'literal' else '', case))
    times.sort()
    report['respond'] = {**summary(results), 'p95_ms': round(times[int(0.95 * len(times))], 2)}
    print('respond', json.dumps(report['respond']), flush=True)
    if hasattr(template, 'load_context'):
        template.calibrated = False
        hits, results, times = 0, [], []
        for case in sample:
            template.load_context(case['context'])
            t = time.perf_counter(); reply = template.answer(case['question']); times.append((time.perf_counter() - t) * 1000)
            text = (reply.get('candidate') or {}).get('text') or (reply.get('text') if reply.get('status') == 'answered' else '')
            gold = [a['text'] if isinstance(a, dict) else a for a in case['answers']]
            hits += any(f' {plain(g)} ' in f' {plain(text)} ' for g in gold)
            results.append(scored(text, case))
        times.sort()
        report['unidad'] = {'contiene_respuesta': round(hits / len(sample), 4), **summary(results),
                            'p95_ms': round(times[int(0.95 * len(times))], 2)}
        print('unidad', json.dumps(report['unidad']), flush=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')


if __name__ == '__main__':
    main()

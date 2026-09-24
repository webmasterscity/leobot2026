"""G-42: lectura MLQA en desarrollo limpio con el bot educado COMPLETO.

python3 -m experiments.g42_mlqa_educado BASE.json OUT.json

El evaluador de G-28b/G-43 crea cada bot solo con el modelo de lectura, sin
sintaxis; así las rutas que dependen de interrogativas aprendidas (G-41, G-42)
no se ejercen.  Aquí cada caso recibe también la sintaxis de la base educada
(solo lectura), y se mide con el mismo corte visible de 300 casos limpios de
G-43 y la misma calificación.  Variantes: G-42 completo; sin alineación
(``structural_answers = False``); y el lector de G-28 solo (sin sintaxis).
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import EDU_SEED, archive, rows, scored, summary
from experiments.validacion_comun import huella
from leobot import Bot


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    test = rows(archive(), 'MLQA_V1/test/test-context-es-question-es.json')
    rng = random.Random(EDU_SEED); chosen = rng.sample(test, 2300)
    edu_contexts = {r['context'] for r in chosen[:2000]}
    visible = [r for r in rng.sample(test, len(test)) if r['context'] not in edu_contexts][:300]
    template = Bot.load(base)
    report = {'huella_motor': huella(), 'casos': len(visible)}
    for name, syntax, structural in (('g42', True, True), ('sin_alineacion', True, False), ('solo_lector_g28', False, True)):
        results, statuses, times = [], {}, []
        for case in visible:
            bot = Bot(); bot.reading_model = template.reading_model
            if syntax:
                bot.syntax_model = template.syntax_model
            bot.structural_answers = structural
            source = f'caso:{case["id"]}'
            bot.ingest_document_text(case['context'], source=source)
            t = time.perf_counter(); reply = bot.respond(case['question']); times.append((time.perf_counter() - t) * 1000)
            status = reply.get('status'); statuses[status] = statuses.get(status, 0) + 1
            answer = reply.get('text', '') if status == 'literal' else ''
            results.append(scored(answer, case))
        times.sort()
        report[name] = {**summary(results), 'estados': dict(sorted(statuses.items())),
                        'p95_ms': round(times[int(0.95 * len(times))], 2)}
        print(name, json.dumps(report[name]), flush=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')


if __name__ == '__main__':
    main()

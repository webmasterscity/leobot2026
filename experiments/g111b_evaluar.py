"""G-111b: comparación preregistrada en el banco nuevo (conteo automático por claves).

python3 -m experiments.g111b_evaluar CONTROL.json TRATAMIENTO.json SALIDA.json CARPETA...

Para cada sistema y cada turno directa/si_no con claves o sin_respuesta: confianza de la elegida, si es útil (contiene las claves) y si
sería cita mala (no útil o sin dato).  Útiles con a lo sumo B = 0,26 N, 0,39 N y 0,65 N citas malas (N = turnos directa/si_no con
claves); bootstrap por negocio (10 000, semilla 0) de la diferencia en B = 0,65 N.  Además: B0 y prefijos solos con la base de control,
latencia p95 de `Bot.answer` y reinicio / PYTHONHASHSEED en un subproceso.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from experiments.g106_diagnostico import contains
from leobot import Bot


def points(bot, folders):
    out = []
    for name, text, instructions, conversations in businesses(folders):
        bot.load_context(text, instructions)
        units = bot.context_units
        for conversation in conversations:
            for turn in conversation:
                kind = turn.get('tipo')
                keys = [k for k in turn.get('claves') or [] if plain(k)]
                if kind in ('directa', 'si_no') and keys:
                    answerable = True
                elif kind == 'sin_respuesta':
                    answerable = False
                else:
                    continue
                _, question = bot._question_part(turn['cliente'])
                ranked = bot._rank(bot.context_terms(question), question)
                conf = ranked.get('useful') if ranked and ranked.get('unit') is not None else None
                good = bool(answerable and conf is not None and contains(units[ranked['unit']]['text'], keys))
                out.append({'negocio': name, 'respondible': answerable, 'conf': -1.0 if conf is None else conf, 'util': good})
    return out


def useful_at(rows, budget):
    best, useful, bad = 0, 0, 0
    for row in sorted(rows, key=lambda r: -r['conf']):
        if row['conf'] < 0:
            break
        useful += row['util']
        bad += not row['util']
        if bad <= budget:
            best = useful
    return best


def main():
    control, treatment, out, folders = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4:]
    systems = {}
    for name, path, off in (('b0', control, ('soft_prefix', 'candidate_model')), ('prefijos', control, ('candidate_model',)),
                            ('control', control, ()), ('tratamiento', treatment, ())):
        bot = Bot.load(path)
        for switch in off:
            setattr(bot, switch, False)
        systems[name] = points(bot, folders)
    n = sum(r['respondible'] for r in systems['control'])
    budgets = {'0.26': 0.26 * n, '0.39': 0.39 * n, '0.65': 0.65 * n}
    table = {s: {k: useful_at(rows, b) for k, b in budgets.items()} for s, rows in systems.items()}
    diff = {k: round(100 * (table['tratamiento'][k] - table['control'][k]) / n, 2) for k in budgets}
    names = sorted({r['negocio'] for r in systems['control']})
    by = {s: {b: [r for r in rows if r['negocio'] == b] for b in names} for s, rows in systems.items()}
    rng, samples = random.Random(0), []
    for _ in range(10000):
        pick = [rng.choice(names) for _ in names]
        c = [r for b in pick for r in by['control'][b]]
        t = [r for b in pick for r in by['tratamiento'][b]]
        m = sum(r['respondible'] for r in c) or 1
        samples.append(100 * (useful_at(t, 0.65 * m) - useful_at(c, 0.65 * m)) / m)
    samples.sort()
    ci = [round(samples[249], 2), round(samples[9749], 2)]
    # Latency of Bot.answer with the treatment.
    bot, times = Bot.load(treatment), []
    for _, text, instructions, conversations in businesses(folders):
        bot.load_context(text, instructions)
        for conversation in conversations:
            history = []
            for turn in conversation:
                start = time.perf_counter()
                reply = bot.answer(turn['cliente'], history)
                times.append((time.perf_counter() - start) * 1000)
                history += [{'role': 'user', 'text': turn['cliente']}, {'role': 'assistant', 'text': reply.get('text', '')}]
    times.sort()
    report = {'N': n, 'presupuestos': {k: round(b, 1) for k, b in budgets.items()}, 'utiles': table,
              'diferencia_puntos': diff, 'bootstrap_0.65_ic95': ci,
              'umbral_1': diff['0.39'] >= 2.0 and diff['0.65'] >= 2.0, 'umbral_2': ci[0] > 0, 'umbral_3': diff['0.26'] >= -2.0,
              'answer_p50_p95_ms': [round(times[len(times) // 2], 3), round(times[int(0.95 * (len(times) - 1))], 3)],
              'turnos_latencia': len(times), 'negocios': len(names)}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

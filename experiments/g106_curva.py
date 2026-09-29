"""G-106, desarrollo: útiles frente a citas malas para cada umbral de cita (curva de operación), por variante.

python3 -m experiments.g106_curva BASE.json CARPETA...

Turnos directa/si_no con claves: la elegida es útil si contiene las claves; cualquier otra cita es mala.  Turnos sin_respuesta:
toda cita es mala.  Imprime, para presupuestos de citas malas fijos, cuántas útiles se consiguen (y el umbral de la base).
"""
from __future__ import annotations

import json
import sys

from experiments.g57_kiosco import businesses, plain
from experiments.g106_diagnostico import contains
from leobot import Bot


def main():
    bot = Bot.load(sys.argv[1])
    model = bot._active_model()
    cite = (model or bot.context_model['confidence']).get('cite_from', 0.7)
    points = []   # (confianza, útil, mala)
    for _, text, instructions, conversations in businesses(sys.argv[2:]):
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
                if ranked is None or ranked.get('unit') is None or ranked.get('useful') is None:
                    continue
                good = answerable and contains(units[ranked['unit']]['text'], keys)
                points.append((ranked['useful'], int(good), int(not good)))
    points.sort(key=lambda p: -p[0])
    curve, useful, bad = {}, 0, 0
    budgets = [50, 75, 100, 125, 150, 200, 250]
    for conf, u, b in points:
        useful += u
        bad += b
        for budget in budgets:
            if bad <= budget:
                curve[budget] = (useful, round(conf, 4))
    at = sum(u for c, u, _ in points if c >= cite), sum(b for c, _, b in points if c >= cite)
    print(json.dumps({'umbral_base': cite, 'en_umbral_utiles_malas': at,
                      'utiles_con_malas_a_lo_sumo': {str(k): v for k, v in curve.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()

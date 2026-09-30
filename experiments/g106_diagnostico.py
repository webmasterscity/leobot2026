"""G-106, diagnóstico de desarrollo: ¿el dato se pierde al proponer candidatas, al elegir o al decidir citar?

python3 -m experiments.g106_diagnostico BASE.json CARPETA... [--apagar a,b]

Solo turnos `directa` y `si_no` con claves y alguna unidad que las contiene (conteo automático, sin juez).  Para cada
turno: ¿alguna unidad con las claves tiene ganancia?, ¿entra entre las candidatas?, ¿el modelo la elige primera?,
¿la confianza de la elegida llega al umbral de cita?  Se usa sobre bancos gastados (desarrollo); no lee `leobot/`
más allá de sus métodos, ni guarda nada en la base.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from experiments.g57_kiosco import businesses, plain
from leobot import Bot
from leobot.context import CANDIDATES


def contains(text, keys):
    haystack = f' {plain(text)} '
    return all(f' {plain(k)} ' in haystack for k in keys if plain(k))


def main():
    args = sys.argv[1:]
    off = []
    if '--apagar' in args:
        k = args.index('--apagar'); off = args[k + 1].split(','); del args[k:k + 2]
    bot = Bot.load(args[0])
    for switch in off:
        setattr(bot, switch, False)
    model = bot._active_model()
    cite = (model or bot.context_model['confidence']).get('cite_from', 0.7)
    stages, by_type, confidences = Counter(), Counter(), []
    for name, text, instructions, conversations in businesses(args[1:]):
        bot.load_context(text, instructions)
        units = bot.context_units
        for conversation in conversations:
            for turn in conversation:
                if turn.get('tipo') not in ('directa', 'si_no') or turn.get('accion', 'responder') != 'responder':
                    continue
                keys = [k for k in turn.get('claves') or [] if plain(k)]
                if not keys:
                    continue
                gold = {i for i, u in enumerate(units) if u['kind'] not in ('question', 'heading') and contains(u['text'], keys)}
                if not gold:
                    stages['sin_unidad_con_claves'] += 1
                    continue
                _, question = bot._question_part(turn['cliente'])
                terms = bot.context_terms(question)
                base, gains, how, asked = bot._gains(terms, question)
                ranked = bot._rank(terms, question)
                pool = sorted((-g, i) for i, g in gains.items() if units[i]['kind'] not in ('heading', 'question'))
                order = [i for _, i in pool]
                useful = ranked.get('useful') if ranked else None
                if not gold & set(order):
                    stage = 'sin_ganancia'
                elif not gold & set(order[:CANDIDATES]):
                    stage = 'fuera_de_candidatas'
                elif ranked is None or ranked['unit'] not in gold:
                    stage = 'elige_otra'
                elif useful is None or useful < cite:
                    stage = 'elige_bien_calla'
                else:
                    stage = 'elige_bien_cita'
                stages[stage] += 1
                by_type[(turn['tipo'], stage)] += 1
                if ranked is not None and useful is not None:
                    confidences.append((round(useful, 2), int(ranked['unit'] in gold)))
    total = sum(stages.values())
    curve = Counter()
    for c, y in confidences:
        curve[(c, y)] += 1
    print(json.dumps({'turnos': total, 'umbral_cita': cite, 'etapas': dict(stages.most_common()),
                      'por_tipo': {f'{a}/{b}': n for (a, b), n in sorted(by_type.items())},
                      'confianza_elegida': {str(c): [curve[(c, 0)], curve[(c, 1)]] for c in sorted({c for c, _ in confidences})}},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

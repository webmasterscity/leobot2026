"""G-105: turnos que dependen de las instrucciones, conteo automático (el juez va aparte).

python3 -m experiments.g105_evaluar BASE.json CARPETA... [--sin-instrucciones] [--barajar]

Por turno con tipo `instruccion` o acción `derivar` cuya evidencia está en las instrucciones: acierto si la respuesta cita una frase
de las instrucciones que contiene la evidencia o está contenida en ella.  Se cuenta también cuántas veces se cita una instrucción
en turnos que no la piden (directas, sí/no, seguimientos, sin respuesta que solo piden abstenerse).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from experiments.g103_educar import contains
from leobot import Bot


def matches(evidence, shown):
    pe, ps = plain(evidence or ''), plain(shown or '')
    return bool(pe) and len(ps.split()) >= 3 and (ps in pe or pe in ps)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    base, folders = Path(args[0]), args[1:]
    bot = Bot.load(base)
    bot.follow_instructions = '--sin-instrucciones' not in sys.argv
    items = list(businesses(folders))
    if '--barajar' in sys.argv:
        rng = random.Random(0)
        others = [x[2] for x in items]
        items = [(n, t, others[(k * 7 + 3) % len(others)], c) for k, (n, t, _, c) in enumerate(items)]
    rows = {'pide_instruccion': [0, 0, 0], 'directa_si_no_seguimiento': [0, 0, 0], 'sin_respuesta': [0, 0, 0], 'otros': [0, 0, 0]}
    for name, text, instructions, conversations in items:
        bot.load_context(text, instructions)
        instruction_text = plain(instructions)
        for conversation in conversations:
            history = []
            for turn in conversation:
                reply = bot.answer(turn['cliente'], history)
                history += [{'role': 'user', 'text': turn['cliente']}, {'role': 'assistant', 'text': reply.get('text', '')}]
                evidence = turn.get('evidencia')
                action, tipo = turn.get('accion'), turn.get('tipo')
                cited = reply.get('status') == 'instruction'
                shown = (reply.get('evidence') or {}).get('unit', '')
                asks = bool(evidence) and plain(evidence) in instruction_text and (tipo == 'instruccion' or action == 'derivar')
                if asks:
                    row = rows['pide_instruccion']
                    row[0] += 1
                    row[1] += cited and matches(evidence, shown)
                    row[2] += cited and not matches(evidence, shown)
                elif tipo in ('directa', 'si_no', 'seguimiento', 'combinada'):
                    row = rows['directa_si_no_seguimiento']
                    row[0] += 1
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    row[1] += cited and bool(keys) and contains(shown, keys)
                    row[2] += cited and not (keys and contains(shown, keys))
                elif tipo == 'sin_respuesta':
                    row = rows['sin_respuesta']
                    row[0] += 1
                    row[2] += cited
                else:
                    row = rows['otros']
                    row[0] += 1
                    row[2] += cited
    for key, (n, ok, bad) in rows.items():
        print(f'{key:28s} turnos={n:5d}  cita la instrucción pedida={ok:4d}  cita una instrucción que no corresponde={bad:4d}')


if __name__ == '__main__':
    main()

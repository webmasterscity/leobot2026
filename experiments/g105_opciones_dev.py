"""Diagnóstico de desarrollo: ¿cuánto añadiría mostrar dos unidades cuando la primera no alcanza el umbral de cita?

python3 -m experiments.g105_opciones_dev BASE.json CARPETA...
Cuenta, por turno con acción responder (directa + sí/no) y por turno sin respuesta, si el texto mostrado contendría las claves.
"""
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from experiments.g103_educar import contains
from leobot import Bot


def main():
    bot = Bot.load(Path(sys.argv[1]))
    tau = bot.context_model['usefulness']['cite_from']
    rows = []
    for name, text, instructions, conversations in businesses(sys.argv[2:]):
        bot.load_context(text, instructions)
        for conversation in conversations:
            for t, turn in enumerate(conversation):
                action = turn.get('accion', 'responder')
                if action == 'charla':
                    continue
                keys = [k for k in turn.get('claves') or [] if plain(k)]
                _, question = bot._question_part(turn['cliente'])
                sent = [{'role': 'user', 'text': x['cliente']} for x in conversation[:t]]
                ranked = bot._rank(bot.context_terms(question), question, bot._previous_topic(sent))
                if ranked is None or ranked['unit'] is None:
                    rows.append((turn.get('tipo'), action, 0.0, None, [], bool(keys)))
                    continue
                units = bot.context_units
                first_ok = bool(keys) and contains(units[ranked['unit']]['text'], keys)
                alt = [(u, p, bool(keys) and contains(units[u]['text'], keys)) for u, p in ranked['alternatives']]
                rows.append((turn.get('tipo'), action, ranked['useful'], first_ok, alt, bool(keys)))
    core = [r for r in rows if r[0] in ('directa', 'si_no') and r[1] == 'responder']
    silent = [r for r in rows if r[1] in ('abstenerse', 'derivar')]
    print('umbral de cita', tau, 'núcleo', len(core), 'sin respuesta', len(silent))
    for tau2 in (0.5, 0.4, 0.3, 0.25, 0.2):
        gain = sum(1 for r in core if r[2] < tau and r[2] >= tau2 and any(a[2] for a in r[4][:1]) and not r[3])
        gain_first = sum(1 for r in core if r[2] < tau and r[2] >= tau2 and r[3])
        extra_silent = sum(1 for r in silent if r[2] < tau and r[2] >= tau2)
        print(f'mostrar 2 unidades si p1 en [{tau2},{tau}): añade {gain_first} aciertos de la primera y {gain} de la segunda; '
              f'cita además {extra_silent} de {len(silent)} preguntas sin respuesta')
    print('ya citadas y útiles:', sum(1 for r in core if r[2] >= tau and r[3]), 'de', len(core))


if __name__ == '__main__':
    main()

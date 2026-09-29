"""G-104: acierto de la unidad elegida (sin umbral de cita) por tipo de turno, con historial real, ninguno o barajado.

python3 -m experiments.g104_seleccion BASE.json CARPETA...  (usa los interruptores del motor; solo diagnóstico de desarrollo)
"""
import random
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from experiments.g103_educar import contains
from leobot import Bot


def main():
    base, folders = Path(sys.argv[1]), sys.argv[2:]
    bot = Bot.load(base)
    items = list(businesses(folders))
    pool = [[t['cliente'] for t in conv] for _, _, _, convs in items for conv in convs]
    rng = random.Random(0)
    for mode in ('real', 'ninguno', 'barajado'):
        stats = {}
        for name, text, instructions, conversations in items:
            bot.load_context(text, instructions)
            for conversation in conversations:
                for t, turn in enumerate(conversation):
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    if turn.get('accion', 'responder') != 'responder' or not keys:
                        continue
                    gold = {i for i, u in enumerate(bot.context_units) if u['kind'] != 'question' and contains(u['text'], keys)}
                    if not gold:
                        continue
                    if mode == 'real':
                        sent = [{'role': 'user', 'text': x['cliente']} for x in conversation[:t]]
                    elif mode == 'ninguno':
                        sent = []
                    else:
                        sent = [{'role': 'user', 'text': x} for x in rng.choice(pool)[:t]]
                    _, question = bot._question_part(turn['cliente'])
                    previous = bot._previous_topic(sent)
                    ranked = bot._rank(bot.context_terms(question), question, previous)
                    row = stats.setdefault(turn.get('tipo'), [0, 0])
                    row[0] += 1
                    row[1] += ranked['unit'] in gold
        print(mode, {k: f'{v[1]}/{v[0]}={v[1]/v[0]:.3f}' for k, v in sorted(stats.items())}, flush=True)


if __name__ == '__main__':
    main()

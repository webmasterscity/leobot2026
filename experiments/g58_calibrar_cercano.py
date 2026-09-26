"""G-58: tabla de «lo más cercano», contada en el banco de G-57 ya gastado con los veredictos del juez ciego.

python3 -m experiments.g58_calibrar_cercano BASE.json SALIDA.json

Cada turno del banco (`results_v3/kiosco/congelado`) se contesta con la mejor unidad (sin silencio calibrado).
Etiqueta:
- si la acción esperada es abstenerse o derivar: no útil;
- si no, el veredicto del juez de G-57 para esa misma respuesta (útil = correcta o incompleta); los turnos cuya
  respuesta nunca se juzgó no cuentan.
Celdas `closest`: útil en al menos la mitad de los casos, con 5 casos o más.  Solo se guardan cuentas por celda.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses
from leobot import Bot

JUDGE = Path('results_v3/kiosco/evaluacion_g57/juez')
BANK = Path('results_v3/kiosco/congelado')
MIN_CASES = 5


def verdicts() -> dict:
    out = {}
    for folder in sorted(f for f in JUDGE.glob('juez*') if f.is_dir()):
        items = {it['id']: it for it in json.loads((folder / 'items.json').read_text(encoding='utf8'))}
        for v in json.loads((folder / 'veredictos.json').read_text(encoding='utf8')):
            it = items[v['id']]
            out[(it['negocio'], it['cliente'], it['respuesta_a_calificar'])] = v['veredicto']
    return out


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    judged = verdicts()
    bot = Bot.load(base)
    bot.calibrated, bot.closest, bot.follow_up = False, False, False
    cells, labelled, skipped = {}, 0, 0
    for name, text, instructions, conversations in businesses(sorted(BANK.glob('W*'))):
        bot.load_context(text, instructions)
        for conversation in conversations:
            for turn in conversation:
                reply = bot.answer(turn['cliente'])
                if reply['status'] != 'answered':
                    continue
                if turn.get('accion') in ('abstenerse', 'derivar'):
                    useful = 0
                else:
                    label = judged.get((name.replace('/', '_'), turn['cliente'], reply['text']))
                    if label is None:
                        skipped += 1
                        continue
                    useful = int(label in ('correcta', 'incompleta'))
                row = cells.setdefault(reply['cell'], [0, 0])
                row[0] += 1
                row[1] += useful
                labelled += 1
    closest = sorted(c for c, (n, ok) in cells.items() if n >= MIN_CASES and ok >= 0.5 * n)
    bot = Bot.load(base)
    bot.context_model['closest'] = closest
    bot.context_model['closest_cells'] = {k: cells[k] for k in sorted(cells)}
    bot.context_model['source']['closest'] = {'bank': str(BANK), 'judge': str(JUDGE), 'turns': labelled,
                                              'unjudged': skipped}
    bot.save(out)
    print(json.dumps({'celdas_cercanas': closest, 'turnos': labelled, 'sin_juicio': skipped,
                      'utiles_en_cercanas': sum(cells[c][1] for c in closest),
                      'mostradas_en_cercanas': sum(cells[c][0] for c in closest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

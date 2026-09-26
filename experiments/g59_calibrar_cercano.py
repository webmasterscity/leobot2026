"""G-59: tabla de «lo más cercano», contada en los bancos de G-57 y G-58 ya gastados.

python3 -m experiments.g59_calibrar_cercano BASE.json SALIDA.json

Cada turno se contesta con la mejor unidad (sin silencio calibrado).  Etiqueta:
- acción esperada abstenerse o derivar: no útil;
- si esa misma unidad fue juzgada para ese turno (juez de G-57: correcta o incompleta; juez de G-58: `util`), el
  veredicto del juez;
- si no, el conteo automático (la unidad contiene todas las claves).
Celdas `closest`: útil en al menos la mitad de los casos, con 5 casos o más.  Solo cuentas por celda.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, contains, plain
from leobot import Bot

BANKS = (Path('results_v3/kiosco/congelado'), Path('results_v3/kiosco/congelado_g58'))
JUDGES = (Path('results_v3/kiosco/evaluacion_g57/juez'), Path('results_v3/kiosco/evaluacion_g58/juez'))
MIN_CASES = 5
QUOTE = re.compile(r'«(.*)»\.?$', re.S)


def verdicts() -> dict:
    out = {}
    for judges in JUDGES:
        for folder in sorted(f for f in judges.glob('juez*') if f.is_dir()):
            items = {it['id']: it for it in json.loads((folder / 'items.json').read_text(encoding='utf8'))}
            for v in json.loads((folder / 'veredictos.json').read_text(encoding='utf8')):
                it = items[v['id']]
                said = it['respuesta_a_calificar']
                quoted = QUOTE.search(said)
                unit = quoted.group(1) if quoted and said.startswith('No lo tengo seguro') else said
                out[(it['negocio'], it['cliente'], plain(unit))] = v['veredicto'] in ('correcta', 'incompleta', 'util')
    return out


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    judged = verdicts()
    bot = Bot.load(base)
    bot.calibrated, bot.closest = False, False
    cells, from_judge, automatic = {}, 0, 0
    for bank in BANKS:
        for name, text, instructions, conversations in businesses(sorted(bank.glob('[WV]*'))):
            bot.load_context(text, instructions)
            for conversation in conversations:
                for turn in conversation:
                    reply = bot.answer(turn['cliente'])
                    if reply['status'] != 'answered':
                        continue
                    unit = reply['evidence']['unit']
                    if turn.get('accion') in ('abstenerse', 'derivar'):
                        useful = 0
                    else:
                        label = judged.get((name.replace('/', '_'), turn['cliente'], plain(unit)))
                        if label is None:
                            keys = [k for k in turn.get('claves') or [] if plain(k)]
                            if not keys:
                                continue
                            label = all(contains(unit, k) for k in keys)
                            automatic += 1
                        else:
                            from_judge += 1
                        useful = int(label)
                    row = cells.setdefault(reply['cell'], [0, 0])
                    row[0] += 1
                    row[1] += useful
    closest = sorted(c for c, (n, ok) in cells.items() if n >= MIN_CASES and ok >= 0.5 * n)
    bot = Bot.load(base)
    bot.context_model['closest'] = closest
    bot.context_model['closest_cells'] = {k: cells[k] for k in sorted(cells)}
    bot.context_model['source']['closest'] = {'banks': [str(b) for b in BANKS], 'judge_labels': from_judge,
                                              'automatic_labels': automatic}
    bot.save(out)
    print(json.dumps({'celdas_cercanas': closest, 'etiquetas_juez': from_judge, 'etiquetas_automaticas': automatic,
                      'utiles_en_cercanas': sum(cells[c][1] for c in closest),
                      'mostradas_en_cercanas': sum(cells[c][0] for c in closest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

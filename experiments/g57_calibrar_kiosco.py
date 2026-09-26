"""G-57: tabla de calibración contada en el banco de desarrollo abierto (enmienda previa al congelado).

python3 -m experiments.g57_calibrar_kiosco BASE.json SALIDA.json CARPETA...

Con MFAQ ninguna celda pasaba (precisión ≤ 0,84 en todas): la tabla se cuenta en las partes abiertas del banco de
desarrollo (texto redactado por modelos de lenguaje, declarado; solo se guardan cuentas por celda, ningún texto).
Cada turno con clave o sin respuesta se contesta con la mejor unidad (`calibrated` apagado); es correcto si el
conteo automático lo da por correcto.  Admisión: la misma regla del preregistro (Clopper–Pearson 95 %, error
acumulado ≤ 2 %).  Las cuentas de MFAQ quedan en `cells_mfaq`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from experiments.g57_educar_kiosco import admit
from experiments.g57_kiosco import run
from leobot import Bot


def main():
    base, out, folders = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    rows = run(base, folders, 'g57', off=('calibrated',))
    cells = {}
    for r in rows:
        if r['veredicto'] in ('correcta', 'equivocada', 'contesto_sin_dato') and r['celda']:
            row = cells.setdefault(r['celda'], [0, 0])
            row[0] += 1
            row[1] += r['veredicto'] == 'correcta'
    bot = Bot.load(base)
    model = bot.context_model
    model['cells_mfaq'] = model.get('cells_mfaq', model.get('cells', {}))
    model['admitted_mfaq'] = model.get('admitted_mfaq', model.get('admitted', []))
    model['cells'] = {k: cells[k] for k in sorted(cells)}
    model['admitted'] = admit(cells)
    model['source']['calibration'] = {'folders': [Path(f).name for f in folders],
                                      'turns': sum(v[0] for v in cells.values())}
    bot.save(out)
    print(json.dumps({'celdas': len(cells), 'admitidas': model['admitted'],
                      'turnos': sum(v[0] for v in cells.values()), 'correctos': sum(v[1] for v in cells.values()),
                      'mejor_precision': max((v[1] / v[0] for v in cells.values() if v[0] >= 10), default=None)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

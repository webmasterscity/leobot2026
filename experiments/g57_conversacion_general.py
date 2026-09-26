"""G-57: las pruebas generales de conversación (material de G-55, ya gastado) con el motor actual y `respond`.

python3 -m experiments.g57_conversacion_general BASE.json SALIDA.json
Referencia: `estable-G-15` 101/21/36 = 158 (reserva cuádruple, referencias, charla).  Solo regresión: no decide
ningún mecanismo nuevo.  Se guardan cifras y respuestas.
"""
import json
import sys
from pathlib import Path

from experiments.g54_conversacion import medir
from experiments.validacion_comun import conversaciones

SETS = ('reserva_g55_cuadruple', 'referencias_g55_doble', 'charla_g55_doble')


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    report = {}
    for name in SETS:
        rep, answers = medir(conversaciones(Path('results_v3/conjuntos_conversacion') / f'{name}.tsv'), base)
        report[name] = {'reporte': rep, 'respuestas': answers}
        print(name, json.dumps(rep, ensure_ascii=False), flush=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()

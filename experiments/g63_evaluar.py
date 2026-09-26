"""G-63: el banco congelado de G-63 con los controles del preregistro (conteo automático; el juez va aparte).

python3 -m experiments.g63_evaluar BASE_G62.json WT_G18 SALIDA_DIR CARPETA...

Variantes (motor `freeze-G-63`; la base es la de `estable-G-18`): tratamiento (texto tal cual); partido (texto partido a 70
columnas, G-63); sin_unir_partido (`join_wrapped` apagado, partido); reinicio_partido; renombrado_estricto_partido;
otro_negocio; contesta_siempre_partido (diagnóstico).  `estable-G-18` (copia de trabajo WT_G18): g18 y g18_partido.
Semilla: huella de `freeze-G-63` (variable G63_HUELLA).
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

FROZEN = os.environ.get('G63_HUELLA', '')
VARIANTS = {
    'tratamiento': {},
    'partido': {'wrap': 70},
    'sin_unir_partido': {'off': ('join_wrapped',), 'wrap': 70},
    'reinicio_partido': {'restart': True, 'wrap': 70},
    'renombrado_estricto_partido': {'rename': True, 'strict': True, 'wrap': 70},
    'otro_negocio': {'other': True},
    'contesta_siempre_partido': {'off': ('calibrated', 'closest'), 'wrap': 70},
}


def one(job):
    name, spec, base, folders, out = job
    from experiments.g57_kiosco import run, totals
    rows = run(Path(base), folders, 'g57', spec.get('off', ()), rename=spec.get('rename', False),
               other=spec.get('other', False), restart=spec.get('restart', False), strict=spec.get('strict', False),
               on=spec.get('on', ()), wrap=spec.get('wrap', 0))
    Path(out, f'{name}.json').write_text(json.dumps({'totales': totals(rows), 'filas': rows}, ensure_ascii=False, indent=1))
    return name, totals(rows)


def main():
    base, wt18, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    folders = sys.argv[4:]
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() != FROZEN:
        raise RuntimeError('El motor no es freeze-G-63.')
    jobs = [(name, spec, base, folders, str(out)) for name, spec in VARIANTS.items()]
    with ProcessPoolExecutor(int(os.environ.get('G63_WORKERS', '3'))) as pool:
        for name, tot in pool.map(one, jobs):
            print(name, json.dumps({k: tot[k] for k in ('directa_si_no_utiles', 'directa_si_no_correctas',
                                                          'sin_respuesta_no_lo_se_o_cita', 'veredictos')},
                                   ensure_ascii=False), flush=True)
    env = dict(os.environ, PYTHONPATH=wt18, PYTHONHASHSEED='0')
    for name, extra in (('g18', []), ('g18_partido', ['--partir', '70'])):
        subprocess.run([sys.executable, 'experiments/g57_kiosco.py', base, str(out / f'{name}.json'), *folders,
                        '--respuestas', *extra], env=env, check=True, stdout=subprocess.DEVNULL)
        print(name, 'listo', flush=True)

if __name__ == '__main__':
    main()

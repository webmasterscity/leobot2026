"""G-58: el banco congelado de G-58 con los controles del preregistro (conteo automático; el juez va aparte).

python3 -m experiments.g58_evaluar BASE_G58.json BASE_G57R.json WT_G57R SALIDA_DIR CARPETA...

Variantes (motor `freeze-G-58` salvo `g57r`): tratamiento; sin_cercano (`closest` apagado); sin_seguimiento;
sin_eco_corto (`short_echo` apagado); tabla_barajada (las cuentas de las celdas de lo más cercano se reasignan al
azar entre celdas y se recalculan las celdas); otro_negocio; reinicio; renombrado_estricto.  `g57r`: el motor de
`freeze-G-57r` con su base (worktree WT_G57R).  Semilla: huella de `freeze-G-58`.
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

FROZEN = '86684a218e4cc2cc2c13fdb0915fc5a281953b6f'
VARIANTS = {
    'tratamiento': {},
    'sin_cercano': {'off': ('closest',)},
    'sin_seguimiento': {'off': ('follow_up',)},
    'sin_eco_corto': {'off': ('short_echo',)},
    'tabla_barajada': {'base': 'barajada'},
    'otro_negocio': {'other': True},
    'reinicio': {'restart': True},
    'renombrado_estricto': {'rename': True, 'strict': True},
}


def one(job):
    name, spec, base, folders, out = job
    from experiments.g57_kiosco import run, totals
    rows = run(Path(base), folders, 'g57', spec.get('off', ()), rename=spec.get('rename', False),
               other=spec.get('other', False), restart=spec.get('restart', False), strict=spec.get('strict', False))
    Path(out, f'{name}.json').write_text(json.dumps({'totales': totals(rows), 'filas': rows}, ensure_ascii=False, indent=1))
    return name, totals(rows)


def main():
    base, base57r, wt57r, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    folders = sys.argv[5:]
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() != FROZEN:
        raise RuntimeError('El motor no es freeze-G-58.')
    data = json.loads(Path(base).read_text(encoding='utf8'))
    model = data['context_model']
    keys = sorted(model['closest_cells'])
    counts = [model['closest_cells'][k] for k in keys]
    random.Random(int(FROZEN[:8], 16)).shuffle(counts)
    model['closest_cells'] = dict(zip(keys, counts))
    model['closest'] = sorted(k for k, (n, ok) in model['closest_cells'].items() if n >= 5 and ok >= 0.5 * n)
    tmp = Path(tempfile.mkdtemp(prefix='g58_'))
    (tmp / 'barajada.json').write_text(json.dumps(data, ensure_ascii=False))
    print('celdas barajadas:', model['closest'], flush=True)
    del data
    jobs = [(name, spec, str(tmp / f"{spec['base']}.json") if 'base' in spec else base, folders, str(out))
            for name, spec in VARIANTS.items()]
    with ProcessPoolExecutor(int(os.environ.get('G58_WORKERS', '3'))) as pool:
        for name, tot in pool.map(one, jobs):
            print(name, json.dumps({k: tot[k] for k in ('directa_si_no_utiles', 'sin_respuesta_no_lo_se_o_cita',
                                                          'veredictos', 'p95_ms')}, ensure_ascii=False), flush=True)
    env = dict(os.environ, PYTHONPATH=wt57r, PYTHONHASHSEED='0')
    subprocess.run([sys.executable, 'experiments/g57_kiosco.py', base57r, str(out / 'g57r.json'), *folders,
                    '--respuestas'], env=env, check=True)
    print('g57r listo', flush=True)


if __name__ == '__main__':
    main()

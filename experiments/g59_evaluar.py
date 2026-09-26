"""G-59: el banco congelado de G-59 con los controles del preregistro (conteo automático; el juez va aparte).

python3 -m experiments.g59_evaluar BASE_G59.json BASE_SIN_CONTRASTE.json BASE_G58.json WT_G58R SALIDA_DIR CARPETA...

Variantes (motor `freeze-G-59` salvo las de G-58r): tratamiento; sin_contraste (base educada con el δ de G-58r);
sin_clase (`answer_class` apagado); con_titulos (`bare_headings` encendido); tabla_barajada; otro_negocio;
reinicio; renombrado_estricto; contesta_siempre (diagnóstico).  G-58r (worktree WT_G58R): g58r y
g58r_contesta_siempre.  Semilla: huella de `freeze-G-59`.
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

FROZEN = '79ecdfb6167dc96c63d0d6c736b8d5da82a3866d'
VARIANTS = {
    'tratamiento': {},
    'sin_contraste': {'base': 'sin_contraste'},
    'sin_clase': {'off': ('answer_class',)},
    'con_titulos': {'on': ('bare_headings',)},
    'tabla_barajada': {'base': 'barajada'},
    'otro_negocio': {'other': True},
    'reinicio': {'restart': True},
    'renombrado_estricto': {'rename': True, 'strict': True},
    'contesta_siempre': {'off': ('calibrated', 'closest')},
}


def one(job):
    name, spec, base, folders, out = job
    from experiments.g57_kiosco import run, totals
    rows = run(Path(base), folders, 'g57', spec.get('off', ()), rename=spec.get('rename', False),
               other=spec.get('other', False), restart=spec.get('restart', False), strict=spec.get('strict', False),
               on=spec.get('on', ()))
    Path(out, f'{name}.json').write_text(json.dumps({'totales': totals(rows), 'filas': rows}, ensure_ascii=False, indent=1))
    return name, totals(rows)


def main():
    base, base_nc, base58, wt58r, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], Path(sys.argv[5])
    folders = sys.argv[6:]
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() != FROZEN:
        raise RuntimeError('El motor no es freeze-G-59.')
    data = json.loads(Path(base).read_text(encoding='utf8'))
    model = data['context_model']
    keys = sorted(model['closest_cells'])
    counts = [model['closest_cells'][k] for k in keys]
    random.Random(int(FROZEN[:8], 16)).shuffle(counts)
    model['closest_cells'] = dict(zip(keys, counts))
    model['closest'] = sorted(k for k, (n, ok) in model['closest_cells'].items() if n >= 5 and ok >= 0.5 * n)
    tmp = Path(tempfile.mkdtemp(prefix='g59_'))
    (tmp / 'barajada.json').write_text(json.dumps(data, ensure_ascii=False))
    del data
    paths = {'barajada': str(tmp / 'barajada.json'), 'sin_contraste': base_nc}
    jobs = [(name, spec, paths[spec['base']] if 'base' in spec else base, folders, str(out)) for name, spec in VARIANTS.items()]
    with ProcessPoolExecutor(int(os.environ.get('G59_WORKERS', '3'))) as pool:
        for name, tot in pool.map(one, jobs):
            print(name, json.dumps({k: tot[k] for k in ('directa_si_no_utiles', 'directa_si_no_correctas',
                                                          'sin_respuesta_no_lo_se_o_cita', 'veredictos')},
                                   ensure_ascii=False), flush=True)
    env = dict(os.environ, PYTHONPATH=wt58r, PYTHONHASHSEED='0')
    for name, extra in (('g58r', []), ('g58r_contesta_siempre', ['--apagar', 'calibrated,closest'])):
        subprocess.run([sys.executable, 'experiments/g57_kiosco.py', base58, str(out / f'{name}.json'), *folders,
                        '--respuestas', *extra], env=env, check=True, stdout=subprocess.DEVNULL)
        print(name, 'listo', flush=True)


if __name__ == '__main__':
    main()

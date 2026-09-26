"""G-62: el banco congelado de G-62 con los controles del preregistro (conteo automático; el juez va aparte).

python3 -m experiments.g62_evaluar BASE_G62.json BASE_G58.json WT_G58R SALIDA_DIR CARPETA...

Variantes (motor `freeze-G-62` salvo las de G-58r): tratamiento; todo_encabezado (`inherit_all_headings`, el
alcance de G-61); sin_herencia (`inherit_heading` apagado);
sin_preguntas_en_linea (`inline_questions` apagado); rasgos_barajados; otro_negocio; reinicio; renombrado_estricto;
contesta_siempre (diagnóstico).  G-58r (worktree WT_G58R): g58r y g58r_contesta_siempre.  Semilla: huella de
`freeze-G-62` (variable G62_HUELLA).
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

FROZEN = os.environ.get('G62_HUELLA', '')
VARIANTS = {
    'tratamiento': {},
    'todo_encabezado': {'on': ('inherit_all_headings',)},
    'sin_herencia': {'off': ('inherit_heading',)},
    'sin_preguntas_en_linea': {'off': ('inline_questions',)},
    'rasgos_barajados': {'base': 'barajada'},
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
    base, base58, wt58r, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    folders = sys.argv[5:]
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() != FROZEN:
        raise RuntimeError('El motor no es freeze-G-62.')
    tmp = Path(tempfile.mkdtemp(prefix='g62_'))
    data = json.loads(Path(base).read_text(encoding='utf8'))
    rng = random.Random(int(FROZEN[:8], 16))
    for name, table in sorted(data['context_model']['confidence']['counts'].items()):
        values = sorted(table)
        pairs = [table[v] for v in values]
        rng.shuffle(pairs)
        data['context_model']['confidence']['counts'][name] = dict(zip(values, pairs))
    (tmp / 'barajada.json').write_text(json.dumps(data, ensure_ascii=False))
    del data
    paths = {'barajada': str(tmp / 'barajada.json')}
    jobs = [(name, spec, paths[spec['base']] if 'base' in spec else base, folders, str(out)) for name, spec in VARIANTS.items()]
    with ProcessPoolExecutor(int(os.environ.get('G62_WORKERS', '3'))) as pool:
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

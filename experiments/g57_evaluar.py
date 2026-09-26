"""G-57: el banco de kiosco congelado con los controles del preregistro (conteo automático; el juez va aparte).

python3 -m experiments.g57_evaluar BASE_G57.json BASE_G15.json WT_G15 SALIDA_DIR CARPETA...

Variantes (motor `freeze-G-57` salvo la última):
- tratamiento;
- contesta_siempre (`calibrated` apagado), y sobre ella: sin_titulos, sin_puente, sin_formas, puente_barajado,
  sin_educacion (context_model vacío), otro_negocio, renombrado (invariancia) y reinicio (idénticas);
- estable_g15: `ingest_document_text` + `respond` con el motor de `estable-G-15` (worktree WT_G15).
Semilla del barajado: la huella de `freeze-G-57`.  Se guardan las filas de cada variante para el juez.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

FROZEN = '80d543096ddb2be8a5c145fb175e9c769fe39952'
ALWAYS = ('calibrated',)
VARIANTS = {
    'tratamiento': {},
    'contesta_siempre': {'off': ALWAYS},
    'sin_titulos': {'off': ALWAYS + ('unit_headings',)},
    'sin_puente': {'off': ALWAYS + ('bridge',)},
    'sin_formas': {'off': ALWAYS + ('figure_shapes',)},
    'puente_barajado': {'off': ALWAYS, 'base': 'barajada'},
    'sin_educacion': {'off': ALWAYS, 'base': 'vacia'},
    'otro_negocio': {'off': ALWAYS, 'other': True},
    'renombrado': {'off': ALWAYS, 'rename': True},
    'reinicio': {'off': ALWAYS, 'restart': True},
}


def one(job):
    name, spec, base, folders, out = job
    from experiments.g57_kiosco import run, totals
    rows = run(Path(base), folders, 'g57', spec.get('off', ()), rename=spec.get('rename', False),
               other=spec.get('other', False), restart=spec.get('restart', False))
    Path(out, f'{name}.json').write_text(json.dumps({'totales': totals(rows), 'filas': rows}, ensure_ascii=False, indent=1))
    return name, totals(rows)


def main():
    base, base15, wt15, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    folders = sys.argv[5:]
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() != FROZEN:
        raise RuntimeError('El motor no es freeze-G-57.')
    data = json.loads(Path(base).read_text(encoding='utf8'))
    tmp = Path(tempfile.mkdtemp(prefix='g57_'))
    shuffled = json.loads(json.dumps(data))
    bridge = shuffled['context_model']['bridge']
    keys = sorted(bridge)
    rows = [bridge[k] for k in keys]
    random.Random(int(FROZEN[:8], 16)).shuffle(rows)
    shuffled['context_model']['bridge'] = dict(zip(keys, rows))
    (tmp / 'barajada.json').write_text(json.dumps(shuffled, ensure_ascii=False))
    empty = json.loads(json.dumps(data))
    empty['context_model'] = {'delta': {}, 'rare_delta': 0.5, 'bridge': {}, 'admitted': [], 'cells': {}}
    (tmp / 'vacia.json').write_text(json.dumps(empty, ensure_ascii=False))
    del data, shuffled, empty
    jobs = [(name, spec, str(tmp / f"{spec['base']}.json") if 'base' in spec else base, folders, str(out))
            for name, spec in VARIANTS.items()]
    workers = int(os.environ.get('G57_WORKERS', '3'))
    with ProcessPoolExecutor(workers) as pool:
        for name, tot in pool.map(one, jobs):
            print(name, json.dumps({k: tot[k] for k in ('directa_si_no_correctas', 'con_respuesta_correctas',
                                                          'error_entre_contestadas_pct', 'sin_respuesta_calladas',
                                                          'p95_ms')}, ensure_ascii=False), flush=True)
    env = dict(os.environ, PYTHONPATH=wt15, PYTHONHASHSEED='0')
    subprocess.run([sys.executable, 'experiments/g57_kiosco.py', base15, str(out / 'estable_g15.json'), *folders,
                    '--sistema', 'respond', '--respuestas'], env=env, check=True)
    print('estable_g15 listo', flush=True)


if __name__ == '__main__':
    main()

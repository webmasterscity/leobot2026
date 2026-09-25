"""freeze-G-55r en los tres conjuntos: tratamiento, sin role_check, sin kind_contrast, renombrado y reinicio."""
import sys, json, re, subprocess
from pathlib import Path
sys.path.insert(0, '.')
assert subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() == subprocess.check_output(['git', 'rev-parse', 'freeze-G-55r:leobot'], text=True).strip()
from experiments.g54_conversacion import medir
from experiments.g42_conversacion import run
from experiments.g52_conversacion import reinicio
from experiments.g55_conversacion import mapa_nombres
from experiments.validacion_comun import conversaciones, normal
base = sys.argv[1]; out = {}
for f in ('reserva_g55_cuadruple', 'referencias_g55_doble', 'charla_g55_doble'):
    convs = conversaciones(Path('results_v3/conjuntos_conversacion') / f'{f}.tsv')
    t, a = medir(convs, base)
    mapa = mapa_nombres(convs)
    sub = lambda s: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), s) if s else s
    _, ren = run([[(sub(d), e) for d, e in c] for c in convs], base)
    rei = reinicio(convs, base)
    out[f] = {'tratamiento': t, 'sin_role_check': medir(convs, base, role_check=False)[0],
              'sin_kind_contrast': medir(convs, base, kind_contrast=False)[0],
              'renombrado_invariantes': f'{sum(normal(sub(x)) == normal(y) for x, y in zip(a, ren))}/{len(a)}',
              'reinicio_identicas': f'{sum(x == y for x, y in zip(a, rei))}/{len(a)}'}
    print(f, t['aciertos'], 'falso', t['afirma_falso'], 'conf', t['errores_confiados'], '| sin role', out[f]['sin_role_check']['aciertos'],
          '| sin kind', out[f]['sin_kind_contrast']['aciertos'], '| ren', out[f]['renombrado_invariantes'], '| rei', out[f]['reinicio_identicas'], flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1))

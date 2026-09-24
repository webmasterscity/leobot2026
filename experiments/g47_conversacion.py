"""G-47: referencias y «dice lo mismo de la misma entidad», con los controles del preregistro.

See prereg/G-47-referencias-y-mismo-hecho.md.
python3 -m experiments.g47_conversacion CONJUNTO.tsv BASE.json OUT.json

Controles: ablación de cada interruptor (``reference_resolution``,
``same_fact``, ``answer_type``) y de los tres juntos, sin memoria, memoria
barajada, y renombrado como invariancia (lista de nombres de G-45).  La
estrategia trivial («No lo sé» fijo) acierta las claves «no lo sé» y «sin
afirmar».  Solo se guardan cifras.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from experiments.g41_conversacion import barajada
from experiments.g42_conversacion import run
from experiments.g45_conversacion import mapa_nombres
from experiments.validacion_comun import conversaciones, huella, normal

ROOT = Path(__file__).resolve().parents[1]
OFF = {'reference_resolution': False, 'same_fact': False, 'answer_type': False}


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    if git('rev-parse', 'freeze-G-47:leobot') != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    convs = conversaciones(conjunto)
    mapa = mapa_nombres(convs)
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    tratamiento, respuestas = run(convs, base)
    _, renombradas = run([[(sub(d), e) for d, e in c] for c in convs], base)
    invariantes = sum(normal(sub(a)) == normal(b) for a, b in zip(respuestas, renombradas))
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': tratamiento}
    for name, switch in (('sin_referencias', 'reference_resolution'), ('sin_mismo_hecho', 'same_fact'),
                         ('sin_tipo', 'answer_type')):
        report[name] = run(convs, base, **{switch: False})[0]
    report['los_tres_apagados'] = run(convs, base, **OFF)[0]
    report['sin_memoria'] = run(convs, base, conversation_memory=False)[0]
    report['memoria_barajada'] = run(barajada(convs), base)[0]
    report['renombrado_invariantes'] = f'{invariantes}/{len(respuestas)}'
    report['nombres_sustituidos'] = len(mapa)
    report['estrategia_siempre_no_lo_se'] = sum(normal(e) in ('no lo se', 'sin afirmar')
                                                for c in convs for _, e in c if e is not None)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

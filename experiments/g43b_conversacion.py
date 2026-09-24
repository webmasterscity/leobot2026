"""G-43b: G-43 sin la clase de respuesta, con los controles del preregistro.

See prereg/G-43b-retirar-la-clase-de-respuesta.md.
python3 -m experiments.g43b_conversacion CONJUNTO.tsv BASE.json OUT.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from experiments.g41_conversacion import barajada
from experiments.g42_conversacion import mapa_nombres, run
from experiments.validacion_comun import conversaciones, huella, normal


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    convs = conversaciones(conjunto)
    mapa = mapa_nombres(convs)
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    tratamiento, respuestas = run(convs, base)
    _, renombradas = run([[(sub(d), e) for d, e in c] for c in convs], base)
    invariantes = sum(normal(sub(a)) == normal(b) for a, b in zip(respuestas, renombradas))
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': tratamiento,
              'ablacion_sin_verificacion_estructural': run(convs, base, structural_verification=False)[0],
              'ablacion_sin_alineacion': run(convs, base, structural_answers=False)[0],
              'sin_memoria': run(convs, base, conversation_memory=False)[0],
              'memoria_barajada': run(barajada(convs), base)[0],
              'renombrado_invariantes': f'{invariantes}/{len(respuestas)}', 'nombres_sustituidos': len(mapa),
              'estrategia_siempre_no_lo_se': sum(normal(e) == 'no lo se' for c in convs for _, e in c if e is not None)}
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

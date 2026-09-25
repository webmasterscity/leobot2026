"""G-54: alcance de la negación, valor negado, quien habla, lo último dicho y la voz, con los controles del preregistro.

See prereg/G-54-lo-dicho-en-conversacion-y-la-voz.md.
python3 -m experiments.g54_conversacion CONJUNTO.tsv BASE.json OUT.json

Controles: cada interruptor de contenido apagado (``scoped_polarity``,
``negated_value``, ``speaker``, ``recency``, ``answer_constituent``, ``dative_copy``) y todos juntos; la voz apagada
(``answer_voice``: los aciertos deben ser idénticos); sin memoria, memoria
barajada, renombrado como invariancia y reinicio (guardar y cargar antes de cada
pregunta: respuestas idénticas).  Solo se guardan cifras.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from experiments.g41_conversacion import barajada
from experiments.g42_conversacion import abstiene, run
from experiments.g45_conversacion import mapa_nombres
from experiments.g52_conversacion import reinicio
from experiments.validacion_comun import califica, conversaciones, empieza, huella, normal

ROOT = Path(__file__).resolve().parents[1]
CONTENIDO = ('scoped_polarity', 'negated_value', 'speaker', 'recency', 'answer_constituent', 'dative_copy', 'name_kind', 'gap_case')


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def confiadas(convs, answers) -> int:
    """Hueco señalado por la auditoría 5.10 de G-53: una respuesta con contenido
    (ni abstención ni «sí»/«no») a una pregunta cuya clave es «no lo sé» es un
    error dicho con seguridad, que no contaban ni «afirma lo falso» ni «abiertas
    equivocadas»."""
    keys = [e for c in convs for _, e in c if e is not None]
    return sum(normal(e) == 'no lo se' and not califica(a, e) and not abstiene(a)
               and not empieza(a, 'si') and not empieza(a, 'no') for e, a in zip(keys, answers))


def medir(convs, base, **switches):
    report, answers = run(convs, base, **switches)
    report['contenido_con_clave_no_lo_se'] = confiadas(convs, answers)
    report['errores_confiados'] = report['afirma_falso'] + report['abiertas_equivocadas'] + report['contenido_con_clave_no_lo_se']
    return report, answers


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    if git('rev-parse', 'freeze-G-54:leobot') != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    convs = conversaciones(conjunto)
    mapa = mapa_nombres(convs)
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    tratamiento, respuestas = medir(convs, base)
    _, renombradas = run([[(sub(d), e) for d, e in c] for c in convs], base)
    invariantes = sum(normal(sub(a)) == normal(b) for a, b in zip(respuestas, renombradas))
    reiniciadas = reinicio(convs, base)
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': tratamiento}
    for name in CONTENIDO:
        report[f'sin_{name}'] = medir(convs, base, **{name: False})[0]
    report['sin_contenido_G54'] = medir(convs, base, **{name: False for name in CONTENIDO})[0]
    report['sin_voz'] = medir(convs, base, answer_voice=False)[0]
    # G-52 (sin aporte confirmado en estable-G-13) se vuelve a medir aquí, con su regla de retirada.
    report['sin_G52'] = medir(convs, base, predicate_gap=False, negative_concord=False, plural_subjects=False)[0]
    report['sin_answer_kind_G53'] = medir(convs, base, answer_kind=False)[0]
    report['sin_memoria'] = run(convs, base, conversation_memory=False)[0]
    report['memoria_barajada'] = run(barajada(convs), base)[0]
    report['renombrado_invariantes'] = f'{invariantes}/{len(respuestas)}'
    report['nombres_sustituidos'] = len(mapa)
    report['reinicio_identicas'] = f'{sum(a == b for a, b in zip(respuestas, reiniciadas))}/{len(respuestas)}'
    report['estrategia_siempre_no_lo_se'] = sum(normal(e) in ('no lo se', 'sin afirmar')
                                                for c in convs for _, e in c if e is not None)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

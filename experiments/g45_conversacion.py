"""G-45: contestar solo lo dicho, con los controles del preregistro.

See prereg/G-45-contestar-solo-lo-dicho.md.
python3 -m experiments.g45_conversacion CONJUNTO.tsv BASE.json OUT.json

Controles: ablación (``conversation_guessing = True``, ``noun_clash = False``),
sin memoria, memoria barajada, y renombrado como invariancia con una lista de
nombres suficiente y sin cifras (en G-44b, 27 sustitutos llevaban cifras).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from experiments.g41_conversacion import barajada
from experiments.g42_conversacion import run
from experiments.validacion_comun import conversaciones, huella, normal

NOMBRES = ['Ramiro', 'Celia', 'Octavio', 'Nuria', 'Gaspar', 'Irene', 'Baltasar', 'Leonor', 'Fermín', 'Olga',
           'Anselmo', 'Rebeca', 'Teodoro', 'Aurora', 'Damián', 'Lisandro', 'Noemí', 'Susana', 'Benigno', 'Clotilde',
           'Evaristo', 'Remedios', 'Florencio', 'Genoveva', 'Hilario', 'Inmaculada', 'Leandro', 'Macarena', 'Nicanor', 'Otilia',
           'Porfirio', 'Rosalía', 'Saturnino', 'Tomasa', 'Ulises', 'Virginia', 'Wenceslao', 'Ximena', 'Zacarías', 'Amparo',
           'Bonifacio', 'Casilda', 'Desiderio', 'Eloísa', 'Fabián', 'Gertrudis', 'Horacio', 'Iluminada', 'Jacinto', 'Lorenza',
           'Marcelino', 'Narcisa', 'Onofre', 'Petronila', 'Quintín', 'Romualdo', 'Serafina', 'Tadeo', 'Úrsula', 'Valeriano',
           'Aniceto', 'Brígida', 'Celestino', 'Dorotea', 'Eulogio', 'Filomena', 'Gumersindo', 'Herminia', 'Isidoro', 'Josefa']


def mapa_nombres(convs):
    nombres = []
    for c in convs:
        for dicho, _ in c:
            for k, w in enumerate(re.findall(r'\w+', dicho)):
                if k > 0 and w[:1].isupper() and not w.isupper() and w not in nombres:
                    nombres.append(w)
    usados = {normal(w) for w in nombres}
    libres = [n for n in NOMBRES if normal(n) not in usados]
    if len(libres) < len(nombres):
        raise RuntimeError('Faltan nombres sustitutos sin cifras.')
    return {w: libres[i] for i, w in enumerate(nombres)}


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
              'ablacion': run(convs, base, conversation_guessing=True, noun_clash=False)[0],
              'sin_memoria': run(convs, base, conversation_memory=False)[0],
              'memoria_barajada': run(barajada(convs), base)[0],
              'renombrado_invariantes': f'{invariantes}/{len(respuestas)}', 'nombres_sustituidos': len(mapa),
              'estrategia_siempre_no_lo_se': sum(normal(e) == 'no lo se' for c in convs for _, e in c if e is not None)}
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

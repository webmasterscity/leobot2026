"""G-41: conversación como lectura, con los controles del preregistro.

See prereg/G-41-conversacion-como-lectura.md.
python3 -m experiments.g41_conversacion CONJUNTO.tsv BASE.json OUT.json

Tratamiento: bot educado (BASE) nuevo por conversación.  Controles:
- sin memoria de conversación (``bot.conversation_memory = False``);
- memoria barajada: cada conversación recibe las afirmaciones de la siguiente;
- nombres renombrados: sustitución coherente de los nombres propios (palabras
  con mayúscula que no abren la frase), hecha aquí por el evaluador.
Solo se guardan cifras y tipos de fallo, nunca el contenido del conjunto.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

from experiments.validacion_comun import califica, conversaciones, empieza, huella, normal, pct

NOMBRES = ['Ramiro', 'Celia', 'Octavio', 'Nuria', 'Gaspar', 'Irene', 'Baltasar', 'Leonor', 'Fermín', 'Olga',
           'Anselmo', 'Rebeca', 'Teodoro', 'Aurora', 'Damián', 'Elvira', 'Lisandro', 'Noemí', 'Rodrigo', 'Susana']


def kind(esperado):
    e = normal(esperado)
    return e if e in ('si', 'no', 'no lo se', 'sin afirmar') else 'abierta'


def run(convs, base, memory=True):
    from leobot import Bot
    rows, times = [], []
    for c in convs:
        bot = Bot.load(base); bot.conversation_memory = memory
        for dicho, esperado in c:
            t = time.perf_counter(); r = bot.respond(dicho).get('text', ''); ms = (time.perf_counter() - t) * 1000
            if esperado is None:
                continue
            times.append(ms)
            ok = califica(r, esperado)
            falso = (not ok) and kind(esperado) != 'abierta' and (
                empieza(r, 'si') or (empieza(r, 'no') and not empieza(r, 'no lo se') and not empieza(r, 'no se')))
            rows.append({'tipo': kind(esperado), 'acierto': ok, 'afirma_falso': falso})
    by = {}
    for r in rows:
        b = by.setdefault(r['tipo'], [0, 0]); b[0] += r['acierto']; b[1] += 1
    return {'calificadas': len(rows), 'aciertos': sum(r['acierto'] for r in rows),
            'afirma_falso': sum(r['afirma_falso'] for r in rows),
            'por_tipo': {k: f'{v[0]}/{v[1]}' for k, v in sorted(by.items())},
            'p50_ms': pct(times, 0.5), 'p95_ms': pct(times, 0.95)}


def barajada(convs):
    out = []
    for i, c in enumerate(convs):
        other = [t for t in convs[(i + 1) % len(convs)] if t[1] is None]
        out.append(other + [t for t in c if t[1] is not None])
    return out


def renombrada(convs):
    nombres, mapa = [], {}
    for c in convs:
        for dicho, _ in c:
            palabras = re.findall(r'\w+', dicho)
            for k, w in enumerate(palabras):
                if k > 0 and w[:1].isupper() and not w.isupper() and w not in nombres:
                    nombres.append(w)
    for n, w in enumerate(nombres):
        mapa[w] = NOMBRES[n % len(NOMBRES)] + ('' if n < len(NOMBRES) else str(n))
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    return [[(sub(d), sub(e)) for d, e in c] for c in convs], len(mapa)


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    convs = conversaciones(conjunto)
    renamed, n = renombrada(convs)
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': run(convs, base), 'sin_memoria': run(convs, base, memory=False),
              'memoria_barajada': run(barajada(convs), base), 'nombres_renombrados': run(renamed, base),
              'nombres_sustituidos': n}
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

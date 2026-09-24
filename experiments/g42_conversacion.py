"""G-42: la pregunta como oración con hueco, con los controles del preregistro.

See prereg/G-42-pregunta-como-oracion-con-hueco.md.
python3 -m experiments.g42_conversacion CONJUNTO.tsv BASE.json OUT.json

Tratamiento: bot educado (BASE) nuevo por conversación.  Controles:
- ablación: ``bot.structural_answers = False`` (preguntas abiertas al lector de G-28);
- sin memoria de conversación (``bot.conversation_memory = False``);
- memoria barajada: cada conversación recibe las afirmaciones de la siguiente;
- renombrado, medido como invariancia: la respuesta con nombres cambiados debe
  ser la respuesta original con los mismos cambios (corrección fijada antes del
  código: en G-41 las claves regex no se renombraban).
«Afirma lo falso» excluye toda abstención de ``ABSTENCIONES`` (corrección fijada
antes del código).  Solo se guardan cifras y tipos de fallo, nunca el contenido.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

from experiments.g41_conversacion import NOMBRES, barajada, kind
from experiments.validacion_comun import ABSTENCIONES, califica, conversaciones, empieza, huella, normal, pct


def abstiene(r):
    return any(empieza(r, a) for a in ABSTENCIONES)


def run(convs, base, **switches):
    from leobot import Bot
    rows, times, answers = [], [], []
    for c in convs:
        bot = Bot.load(base)
        for name, value in switches.items():
            setattr(bot, name, value)
        for dicho, esperado in c:
            t = time.perf_counter(); r = bot.respond(dicho).get('text', ''); ms = (time.perf_counter() - t) * 1000
            if esperado is None:
                continue
            times.append(ms); answers.append(r)
            ok = califica(r, esperado)
            tipo = kind(esperado)
            falso = (not ok) and tipo != 'abierta' and not abstiene(r) and (empieza(r, 'si') or empieza(r, 'no'))
            abierta_mal = (not ok) and tipo == 'abierta' and not abstiene(r)
            rows.append({'tipo': tipo, 'acierto': ok, 'afirma_falso': falso, 'abierta_equivocada': abierta_mal})
    by = {}
    for r in rows:
        b = by.setdefault(r['tipo'], [0, 0]); b[0] += r['acierto']; b[1] += 1
    return {'calificadas': len(rows), 'aciertos': sum(r['acierto'] for r in rows),
            'afirma_falso': sum(r['afirma_falso'] for r in rows),
            'abiertas_equivocadas': sum(r['abierta_equivocada'] for r in rows),
            'por_tipo': {k: f'{v[0]}/{v[1]}' for k, v in sorted(by.items())},
            'p50_ms': pct(times, 0.5), 'p95_ms': pct(times, 0.95)}, answers


def mapa_nombres(convs):
    nombres = []
    for c in convs:
        for dicho, _ in c:
            for k, w in enumerate(re.findall(r'\w+', dicho)):
                if k > 0 and w[:1].isupper() and not w.isupper() and w not in nombres:
                    nombres.append(w)
    usados = {normal(w) for w in nombres}
    libres = [n for n in NOMBRES if normal(n) not in usados]
    return {w: libres[i % len(libres)] + ('' if i < len(libres) else str(i)) for i, w in enumerate(nombres)}


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    convs = conversaciones(conjunto)
    mapa = mapa_nombres(convs)
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    renamed = [[(sub(d), e) for d, e in c] for c in convs]
    tratamiento, respuestas = run(convs, base)
    _, renombradas = run(renamed, base)
    invariantes = sum(normal(sub(a)) == normal(b) for a, b in zip(respuestas, renombradas))
    trivial = sum(normal(e) == 'no lo se' for c in convs for _, e in c if e is not None)
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': tratamiento,
              'ablacion_sin_alineacion': run(convs, base, structural_answers=False)[0],
              'sin_memoria': run(convs, base, conversation_memory=False)[0],
              'memoria_barajada': run(barajada(convs), base)[0],
              'renombrado_invariantes': f'{invariantes}/{len(respuestas)}', 'nombres_sustituidos': len(mapa),
              'estrategia_siempre_no_lo_se': trivial}
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

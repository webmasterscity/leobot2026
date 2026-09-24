"""Validación común en español corriente, por la interfaz pública de conversación.

python3 -m experiments.validacion_comun RUTA [--detalle] [--base BOT.json]
python3 -m experiments.validacion_comun RUTA --exportar SALIDA.json
python3 -m experiments.validacion_comun RUTA --respuestas RESPUESTAS.json [--detalle]

Formato del conjunto (UTF-8):
- una línea por turno: «lo que se dice<TAB>lo que se espera»;
- una línea sin TAB se le dice al bot y no se califica;
- una línea en blanco empieza una conversación nueva (bot nuevo, memoria temporal);
- una línea que empieza por «#» es un comentario.

Calificación de lo esperado:
- «sí», «no», «no lo sé»: la respuesta debe EMPEZAR así (sin distinguir mayúsculas
  ni tildes); un «no» esperado nunca acepta una abstención (una respuesta que empieza
  por «no lo sé», «no sé», «no tengo», «no encontré», «no puedo», «no recibí» o
  «no hay información»);
- «sin afirmar»: la respuesta no empieza por sí ni por un no que afirme (una
  abstención como «no sé si…» sí cuenta como sin afirmar; es la intención de la
  regla: no afirmar ni negar);
- «/…/flags»: expresión regular (flags: i, m, s);
- cualquier otro texto: debe aparecer dentro de la respuesta (sin distinguir
  mayúsculas ni tildes).

--base parte cada conversación de una copia nueva de un bot educado de forma
general (guardado con Bot.save), sin memoria entre conversaciones; sin --base,
cada conversación empieza con un bot vacío.
--exportar escribe las conversaciones sin lo esperado (para que otro las conteste
sin ver la clave); --respuestas califica una lista JSON de respuestas, una por
turno dicho, en el mismo orden, con las mismas reglas.
Sin --detalle solo se imprimen cifras totales y la huella del motor.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ABSTENCIONES = ('no lo se', 'no se', 'no tengo', 'no encontre', 'no puedo', 'no recibi', 'no hay informacion')


def normal(texto: str) -> str:
    texto = unicodedata.normalize('NFD', texto.strip().lower())
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn')


def empieza(respuesta: str, palabra: str) -> bool:
    r = normal(respuesta).lstrip('¡¿"\'«( ')
    return r == palabra or (r.startswith(palabra) and not r[len(palabra)].isalnum())


def califica(respuesta: str, esperado: str) -> bool:
    e = normal(esperado)
    if e in ('si', 'no lo se'):
        return empieza(respuesta, e)
    if e == 'no':
        return empieza(respuesta, 'no') and not any(empieza(respuesta, a) for a in ABSTENCIONES)
    if e == 'sin afirmar':
        abstiene = any(empieza(respuesta, a) for a in ABSTENCIONES)
        return not empieza(respuesta, 'si') and (abstiene or not empieza(respuesta, 'no'))
    m = re.fullmatch(r'/(.*)/([ims]*)', esperado.strip(), re.S)
    if m:
        flags = 0
        for f in m.group(2):
            flags |= {'i': re.I, 'm': re.M, 's': re.S}[f]
        return re.search(m.group(1), respuesta, flags) is not None
    return normal(esperado) in normal(respuesta)


def conversaciones(ruta: Path) -> list[list[tuple[str, str | None]]]:
    convs, actual = [], []
    for linea in ruta.read_text(encoding='utf8').splitlines():
        if linea.startswith('#'):
            continue
        if not linea.strip():
            if actual:
                convs.append(actual); actual = []
            continue
        dicho, _, esperado = linea.partition('\t')
        actual.append((dicho.strip(), esperado.strip() if esperado.strip() else None))
    if actual:
        convs.append(actual)
    return convs


def huella() -> str:
    tree = subprocess.check_output(('git', 'rev-parse', 'HEAD:leobot'), cwd=ROOT, text=True).strip()
    sucio = subprocess.check_output(('git', 'status', '--porcelain', '--', 'leobot'), cwd=ROOT, text=True).strip()
    return tree + (' (con cambios sin commit)' if sucio else '')


def pct(valores, q):
    v = sorted(valores)
    return round(v[min(len(v) - 1, int(q * len(v)))], 3) if v else None


def main():
    args = sys.argv[1:]
    ruta = Path(args[0]); detalle = '--detalle' in args
    convs = conversaciones(ruta)
    if '--exportar' in args:
        salida = Path(args[args.index('--exportar') + 1])
        salida.write_text(json.dumps([[d for d, _ in c] for c in convs], ensure_ascii=False, indent=1), encoding='utf8')
        print(f'{sum(len(c) for c in convs)} turnos en {len(convs)} conversaciones exportados sin lo esperado')
        return
    base = Path(args[args.index('--base') + 1]) if '--base' in args else None
    externas = None
    if '--respuestas' in args:
        externas = json.loads(Path(args[args.index('--respuestas') + 1]).read_text(encoding='utf8'))
        externas = [r for c in externas for r in c] if externas and isinstance(externas[0], list) else externas
    calificadas = aciertos = abstenciones = 0
    tiempos, filas, k = [], [], 0
    for c in convs:
        bot = None
        if externas is None:
            from leobot import Bot
            bot = Bot.load(base) if base else Bot()
        for dicho, esperado in c:
            if externas is None:
                t = time.perf_counter()
                respuesta = bot.respond(dicho).get('text', '')
                ms = (time.perf_counter() - t) * 1000
            else:
                respuesta, ms = str(externas[k]), None
            k += 1
            if esperado is None:
                continue
            ok = califica(respuesta, esperado)
            calificadas += 1; aciertos += ok
            abstenciones += any(empieza(respuesta, a) for a in ABSTENCIONES)
            if ms is not None:
                tiempos.append(ms)
            filas.append({'dicho': dicho, 'esperado': esperado, 'respuesta': respuesta, 'acierto': ok})
    resumen = {'conjunto_sha256': __import__('hashlib').sha256(ruta.read_bytes()).hexdigest()[:16],
               'conversaciones': len(convs), 'calificadas': calificadas, 'aciertos': aciertos,
               'no_lo_se': abstenciones, 'p50_ms': pct(tiempos, 0.5), 'p95_ms': pct(tiempos, 0.95),
               'respondido_por': 'lista externa' if externas is not None else 'leobot',
               'base': None if base is None else __import__('hashlib').sha256(base.read_bytes()).hexdigest()[:16],
               'huella_motor': huella()}
    print(json.dumps(resumen, ensure_ascii=False))
    if detalle:
        for f in filas:
            print(json.dumps(f, ensure_ascii=False))


if __name__ == '__main__':
    main()

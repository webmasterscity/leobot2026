"""G-107: preguntas de conocimiento general contra `respond`, con conteo automático (desarrollo) y filas para el juez.

python3 -m experiments.g107_evaluar BASE.json BANCO.json... [--ruta templates|reading|ninguna] [--salida FILAS.json]

Conteo automático: `abstencion` si la respuesta empieza por «No lo sé»; en contestables, `correcta` si contiene la respuesta o una
aceptable (sin tildes ni mayúsculas; «sí»/«no» se miran al comienzo), si no `otra`; en sin_respuesta, toda respuesta que no se
abstiene es `contesto_sin_dato`.  El juez ciego decide en la reserva; esto solo orienta el desarrollo.
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

from leobot import Bot


def plain(text: str) -> str:
    text = unicodedata.normalize('NFKD', str(text).lower())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c) and (c.isalnum() or c.isspace())).split())


def verdict(item: dict, reply: dict) -> str:
    said = plain(reply.get('text', ''))
    if not said or said.startswith('no lo se'):
        return 'abstencion'
    if item.get('tipo') == 'sin_respuesta':
        return 'contesto_sin_dato'
    for expected in [item.get('respuesta', '')] + list(item.get('aceptables') or []):
        e = plain(expected)
        if e in ('si', 'no'):
            if said.split()[:1] == [e]:
                return 'correcta'
        elif e and f' {e} ' in f' {said} ':
            return 'correcta'
    return 'otra'


def main():
    args = sys.argv[1:]
    def option(name, default=None):
        if name in args:
            k = args.index(name); value = args[k + 1]; del args[k:k + 2]; return value
        return default
    route, out = option('--ruta', 'templates'), option('--salida')
    library = option('--biblioteca')
    bot = Bot.load(args[0])
    t_attach = time.perf_counter()
    attached = bot.attach_library(library)['rows'] if library else 0
    t_attach = time.perf_counter() - t_attach
    bot.general_route = None if route == 'ninguna' else route
    items = [item for path in args[1:] for item in json.loads(Path(path).read_text(encoding='utf8'))]
    rows, counts, times = [], {}, []
    for item in items:
        start = time.perf_counter()
        reply = bot.respond(item['pregunta'])
        times.append((time.perf_counter() - start) * 1000)
        v = verdict(item, reply)
        counts[v] = counts.get(v, 0) + 1
        rows.append({'id': item['id'], 'pregunta': item['pregunta'], 'esperada': item.get('respuesta'), 'tipo': item.get('tipo'),
                     'respuesta': reply.get('text', ''), 'estado': reply.get('status'), 'veredicto': v, 'ms': round(times[-1], 3)})
    times.sort()
    summary = {'ruta': route, 'biblioteca': attached, 'adjuntar_s': round(t_attach, 1), 'preguntas': len(items), 'contestables': sum(i.get('tipo') == 'contestable' for i in items),
               'veredictos': counts, 'p50_ms': round(times[len(times) // 2], 3), 'p95_ms': round(times[int(0.95 * (len(times) - 1))], 3), 'max_ms': round(times[-1], 1)}
    if out:
        Path(out).write_text(json.dumps({'resumen': summary, 'filas': rows}, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()

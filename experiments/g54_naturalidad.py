"""G-54: naturalidad de las respuestas, juzgada a ciegas por un juez independiente.

See prereg/G-54-lo-dicho-en-conversacion-y-la-voz.md.

python3 -m experiments.g54_naturalidad respuestas CONJUNTO.tsv BASE.json OUT.json [SWITCHES_JSON]
    Respuestas de Leobot a cada turno (mismo formato que las del subagente: una lista por charla).
python3 -m experiments.g54_naturalidad preparar CONJUNTO.tsv VOZ.json SIN_VOZ.json SUBAGENTE.json SEMILLA ITEMS.json MAPA.json [NOMBRES]
    Para cada pregunta calificada: lo contado antes, la pregunta y tres respuestas sin rótulo en orden al azar.
    ITEMS.json es lo único que ve el juez; MAPA.json dice qué letra es cada sistema.  NOMBRES (separados por
    comas) rotula los tres archivos cuando no son la voz, sin la voz y el subagente (G-56).
python3 -m experiments.g54_naturalidad puntuar MAPA.json JUICIO.json OUT.json
    JUICIO.json: [{"id": n, "A": {"nota": 1-5, "error_gramatical": bool}, "B": …, "C": …}, …]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from experiments.validacion_comun import conversaciones

SISTEMAS = ('leobot_voz', 'leobot_sin_voz', 'subagente')


def respuestas(conjunto: Path, base: Path, out: Path, switches: dict) -> None:
    from leobot import Bot
    todas = []
    for c in conversaciones(conjunto):
        bot = Bot.load(base)
        for name, value in switches.items():
            setattr(bot, name, value)
        todas.append([bot.respond(dicho).get('text', '') for dicho, _ in c])
    out.write_text(json.dumps(todas, ensure_ascii=False, indent=1), encoding='utf8')


def preparar(conjunto: Path, fuentes: list[Path], semilla: int, items_out: Path, mapa_out: Path,
             nombres=SISTEMAS) -> None:
    convs = conversaciones(conjunto)
    por_sistema = [json.loads(f.read_text(encoding='utf8')) for f in fuentes]
    items, mapa = [], []
    for ci, c in enumerate(convs):
        contado = []
        for ti, (dicho, esperado) in enumerate(c):
            if esperado is None:
                contado.append(dicho)
                continue
            orden = list(range(len(nombres)))
            random.Random(semilla * 1000 + len(items)).shuffle(orden)
            letras = {}
            for letra, k in zip('ABC', orden):
                letras[letra] = por_sistema[k][ci][ti]
            items.append({'id': len(items), 'lo_contado': list(contado), 'pregunta': dicho, 'respuestas': letras})
            mapa.append({'id': len(mapa), 'letras': {letra: nombres[k] for letra, k in zip('ABC', orden)}})
    items_out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf8')
    mapa_out.write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding='utf8')


def puntuar(mapa_path: Path, juicio_path: Path, out: Path) -> None:
    mapa = {m['id']: m['letras'] for m in json.loads(mapa_path.read_text(encoding='utf8'))}
    nombres = sorted({s for letras in mapa.values() for s in letras.values()})
    notas = {s: [] for s in nombres}
    errores = {s: 0 for s in nombres}
    for j in json.loads(juicio_path.read_text(encoding='utf8')):
        for letra, sistema in mapa[j['id']].items():
            notas[sistema].append(float(j[letra]['nota']))
            errores[sistema] += bool(j[letra].get('error_gramatical'))
    informe = {s: {'naturalidad_media': round(sum(v) / len(v), 3) if v else None, 'juzgadas': len(v),
                   'con_error_gramatical': errores[s]} for s, v in notas.items()}
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(informe, ensure_ascii=False))


def main():
    orden = sys.argv[1]
    if orden == 'respuestas':
        respuestas(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]),
                   json.loads(sys.argv[5]) if len(sys.argv) > 5 else {})
    elif orden == 'preparar':
        preparar(Path(sys.argv[2]), [Path(p) for p in sys.argv[3:6]], int(sys.argv[6]), Path(sys.argv[7]),
                 Path(sys.argv[8]), tuple(sys.argv[9].split(',')) if len(sys.argv) > 9 else SISTEMAS)
    elif orden == 'puntuar':
        puntuar(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .bot import Bot
from .scalable import ScalableBot
from .core import Atom
from .learning import RelationalLearner

HELP = '''Comandos:
  /cargar ruta.json                Añadir datos y ejemplos estructurados.
  /leer ruta.txt                  Leer frases enseñadas, una por línea; informa rechazos.
  /consulta relacion(a, ?b)        Consultar y guardar la traza de explicación.
  /hecho relacion(a, b)            Añadir un hecho con procedencia.
  /ejemplo habilidad 2,3 -> 6     Enseñar un ejemplo numérico; aprende de nuevo.
  /aprender relacion              Inducir una relación con sus ejemplos guardados.
  /explica                        Mostrar la prueba de la última consulta.
  /estado                         Contadores de memoria.
  /guardar                        Guardar la memoria de forma atómica.
  /salir                          Guardar y salir.
También puedes conversar usando las construcciones enseñadas en los datos.
No comprende español libre ni libros arbitrarios sin anotación.'''


def main() -> None:
    ap = argparse.ArgumentParser(description='Leobot Lab, prototipo experimental sin redes ni GPU.')
    ap.add_argument('--state', default='memoria.json', help='Estado cognitivo. Con --db no contiene los hechos masivos.')
    ap.add_argument('--db', help='SQLite para memoria factual escalable en disco.')
    ap.add_argument('--load', action='append', default=[], help='Dataset JSON para añadir; admite varios.')
    ap.add_argument('--ask', help='Una sola frase o consulta formal.')
    ap.add_argument('--json', action='store_true', help='Mostrar respuesta y traza JSON.')
    args = ap.parse_args()
    try:
        if args.db:
            bot = ScalableBot.load(args.state, args.db) if Path(args.state).exists() else ScalableBot(args.db)
        else:
            bot = Bot.load(args.state) if Path(args.state).exists() else Bot()
        for name in args.load:
            result = bot.ingest(json.loads(Path(name).read_text(encoding='utf8')))
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f'Datos cargados: {result["added"]}')
        if args.ask:
            try:
                atom = Atom.parse(args.ask)
            except ValueError:
                atom = None
            result = bot.answer_atom(atom) if atom else bot.respond(args.ask)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result['text'])
            bot.save(args.state)
            if hasattr(bot, 'close'): bot.close()
            return
        print('Leobot Lab V3 — CPU, no neuronal. /ayuda muestra los comandos.')
        while True:
            try:
                text = input('Tú> ').strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                if not text:
                    continue
                if text == '/salir':
                    break
                if text == '/ayuda':
                    print(HELP); continue
                if text == '/guardar':
                    bot.save(args.state); print('Memoria guardada.'); continue
                if text == '/estado':
                    print(json.dumps(bot.kb.stats(), ensure_ascii=False)); continue
                if text == '/explica':
                    result = bot.explain()
                elif text.startswith('/cargar '):
                    result = bot.ingest(json.loads(Path(text[8:].strip()).read_text(encoding='utf8')))
                elif text.startswith('/leer '):
                    lines = Path(text[6:].strip()).read_text(encoding='utf8').splitlines()
                    result = {'lines': [{'line': i + 1, **bot.respond(line)} for i, line in enumerate(lines) if line.strip()]}
                elif text.startswith('/consulta '):
                    result = bot.answer_atom(Atom.parse(text[10:]))
                elif text.startswith('/hecho '):
                    fid = bot.kb.add(Atom.parse(text[7:]), 'conversación formal')
                    bot.last_fact, bot.last_result = fid, None
                    result = {'text': 'Dato registrado: ' + fid}
                elif text.startswith('/aprender '):
                    result = RelationalLearner(bot.kb).fit(text[10:].strip())
                elif text.startswith('/ejemplo '):
                    name, expr = text[9:].split(' ', 1)
                    lhs, rhs = expr.split('->')
                    inputs = tuple(int(x.strip()) for x in lhs.split(','))
                    changed = bot.programs.add_example(name, inputs, int(rhs.strip()))
                    result = bot.programs.fit(name) if changed else {'text': 'Ejemplo ya registrado; no se cuenta de nuevo.'}
                else:
                    result = bot.respond(text)
                print('Bot> ' + (json.dumps(result, ensure_ascii=False, indent=2) if args.json or 'text' not in result else result['text']))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                print('Error de entrada: ' + str(exc), file=sys.stderr)
        bot.save(args.state)
        if hasattr(bot, 'close'): bot.close()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == '__main__':
    main()

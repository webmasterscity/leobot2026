"""G-57: banco de kiosco (negocio + instrucciones + conversaciones con clave), conteo automático.

python3 experiments/g57_kiosco.py BASE.json SALIDA.json CARPETA... [--sistema g57|respond] [--apagar a,b]
        [--ciega] [--respuestas] [--otro-negocio] [--renombrar] [--reinicio]

Cada CARPETA tiene subcarpetas de negocio con `negocio.txt`, `instrucciones.txt` y `conversaciones.json`.  Es
autónomo (solo importa `leobot`), para correrlo también contra el motor de otro tag con PYTHONPATH.

- `g57`: `Bot.load_context(negocio, instrucciones)` y `Bot.answer(turno, historial)`.
- `respond`: la vía anterior, `ingest_document_text(negocio + instrucciones)` y `respond(turno)`.

Conteo por turno (clave contenida, sin tildes ni puntuación):
- `responder` con claves: correcta | equivocada (contestó sin todas las claves) | abstencion_indebida;
- `abstenerse` o `derivar`: abstencion_correcta | contesto_sin_dato;
- `charla`: charla_ok (saludo devuelto) | charla_otro.
Con --ciega solo se guardan y muestran totales.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

from leobot import Bot

ABSTAINED = ('unknown', 'literal_unknown', 'unrecognized', 'ambiguous')


def plain(text: str) -> str:
    text = unicodedata.normalize('NFKD', str(text).lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(re.findall(r'[a-z0-9ñ]+', text))


def contains(answer: str, key: str) -> bool:
    return f' {plain(key)} ' in f' {plain(answer)} '


def businesses(folders):
    for folder in folders:
        for sub in sorted(Path(folder).iterdir()):
            if (sub / 'conversaciones.json').exists():
                yield (f'{Path(folder).name}/{sub.name}', (sub / 'negocio.txt').read_text(encoding='utf8'),
                       (sub / 'instrucciones.txt').read_text(encoding='utf8') if (sub / 'instrucciones.txt').exists() else '',
                       json.loads((sub / 'conversaciones.json').read_text(encoding='utf8')))


def judge(turn: dict, reply: dict, system: str) -> str:
    text = reply.get('text', '') or ''
    status = reply.get('status', '')
    abstained = status in ABSTAINED or plain(text).startswith('no lo se') or (system == 'g57' and status == 'unknown')
    action = turn.get('accion', 'responder')
    keys = [k for k in turn.get('claves') or [] if plain(k)]
    if action == 'charla':
        return 'charla_ok' if status == 'phatic' else 'charla_otro'
    if action in ('abstenerse', 'derivar'):
        return 'abstencion_correcta' if abstained else 'contesto_sin_dato'
    if not keys:
        return 'sin_clave'
    if abstained:
        return 'abstencion_indebida'
    return 'correcta' if all(contains(text, k) for k in keys) else 'equivocada'


def reply_g57(bot, turn_text, history):
    return bot.answer(turn_text, history)


def run(base: Path, folders, system: str, off=(), rename=False, other=False, restart=False):
    rows = []
    template = Bot.load(base) if system == 'g57' else None
    items = list(businesses(folders))
    for index, (name, text, instructions, conversations) in enumerate(items):
        if other:
            # Control: the questions of one business against the text of the next one.
            _, text, instructions, _ = items[(index + 1) % len(items)]
        if system == 'g57':
            bot = template
            for switch in off:
                setattr(bot, switch, False)
            bot.load_context(text, instructions)
            if restart:
                with tempfile.TemporaryDirectory() as tmp:
                    bot.save(Path(tmp) / 'b.json')
                    bot = Bot.load(Path(tmp) / 'b.json')
                    for switch in off:
                        setattr(bot, switch, False)
        else:
            bot = Bot.load(base)
            bot.ingest_document_text(text + '\n\n' + instructions, source='negocio')
        for c, conversation in enumerate(conversations):
            history = []
            for t, turn in enumerate(conversation):
                said = turn['cliente']
                start = time.perf_counter()
                reply = bot.answer(said, history) if system == 'g57' else bot.respond(said)
                ms = (time.perf_counter() - start) * 1000
                history += [{'role': 'user', 'text': said}, {'role': 'assistant', 'text': reply.get('text', '')}]
                rows.append({'negocio': name, 'conv': c, 'turno': t, 'tipo': turn.get('tipo'),
                             'accion': turn.get('accion'), 'veredicto': judge(turn, reply, system),
                             'ms': round(ms, 3), 'respuesta': reply.get('text', ''), 'estado': reply.get('status'),
                             'celda': reply.get('cell'), 'cliente': said, 'claves': turn.get('claves')})
    return rows


def totals(rows) -> dict:
    out = {'turnos': len(rows)}
    verdicts = {}
    for r in rows:
        verdicts[r['veredicto']] = verdicts.get(r['veredicto'], 0) + 1
    out['veredictos'] = dict(sorted(verdicts.items()))
    by_type = {}
    for r in rows:
        cell = by_type.setdefault(r['tipo'], {})
        cell[r['veredicto']] = cell.get(r['veredicto'], 0) + 1
    out['por_tipo'] = {k: dict(sorted(v.items())) for k, v in sorted(by_type.items(), key=lambda kv: str(kv[0]))}
    answerable = [r for r in rows if r['accion'] == 'responder' and r['veredicto'] in ('correcta', 'equivocada', 'abstencion_indebida')]
    core = [r for r in answerable if r['tipo'] in ('directa', 'si_no')]
    answered = [r for r in rows if r['veredicto'] in ('correcta', 'equivocada', 'contesto_sin_dato')]
    unanswerable = [r for r in rows if r['accion'] in ('abstenerse', 'derivar')]
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    out['directa_si_no_correctas'] = f"{sum(r['veredicto'] == 'correcta' for r in core)}/{len(core)}"
    out['directa_si_no_pct'] = pct(sum(r['veredicto'] == 'correcta' for r in core), len(core))
    out['con_respuesta_correctas'] = f"{sum(r['veredicto'] == 'correcta' for r in answerable)}/{len(answerable)}"
    out['error_entre_contestadas_pct'] = pct(sum(r['veredicto'] != 'correcta' for r in answered), len(answered))
    out['contestadas'] = len(answered)
    out['sin_respuesta_calladas'] = f"{sum(r['veredicto'] == 'abstencion_correcta' for r in unanswerable)}/{len(unanswerable)}"
    times = sorted(r['ms'] for r in rows)
    out['p50_ms'] = times[len(times) // 2] if times else None
    out['p95_ms'] = times[int(0.95 * len(times))] if times else None
    return out


def main():
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith('--') and a not in ('--sistema', '--apagar')}
    system = args[args.index('--sistema') + 1] if '--sistema' in args else 'g57'
    off = tuple(x for x in (args[args.index('--apagar') + 1].split(',') if '--apagar' in args else []) if x)
    positional = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] not in ('--sistema', '--apagar'))]
    base, out, folders = Path(positional[0]), Path(positional[1]), positional[2:]
    rows = run(base, folders, system, off, other='--otro-negocio' in flags, restart='--reinicio' in flags)
    report = {'sistema': system, 'apagados': list(off), 'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16],
              'carpetas': folders, **totals(rows)}
    if '--respuestas' in flags and '--ciega' not in flags:
        report['filas'] = rows
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'filas'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""G-103: variantes del banco con conteo automático (el juez va aparte).

python3 -m experiments.g103_evaluar BASE.json SALIDA_DIR CARPETA... [--variantes a,b] [--base-sin-pares B.json] [--base-barajada B.json]

Variantes: b0 (interruptores apagados: motor de la línea base), prefijo (solo coincidencia por prefijo), tratamiento,
sin_pares (otra base entrenada sin pares), pares_barajados (otra base), otro_negocio, renombrado, reinicio.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import random
import time

from experiments.g57_kiosco import businesses, judge, run, totals
from leobot import Bot


def replay(base, folders, off=(), history='real', seed=0, on=()):
    """Como `run` (sistema g57) pero con control del historial que recibe `answer`: real (las conversaciones tal cual),
    ninguno, o barajado (el historial de otra conversación del mismo banco: señal confundida)."""
    bot = Bot.load(base)
    for switch in off:
        setattr(bot, switch, False)
    for switch in on:
        setattr(bot, switch, True)
    items = list(businesses(folders))
    rng = random.Random(seed)
    pool = [[t['cliente'] for t in conv] for _, _, _, convs in items for conv in convs]
    rows = []
    for name, text, instructions, conversations in items:
        bot.load_context(text, instructions)
        for c, conversation in enumerate(conversations):
            past = []
            for t, turn in enumerate(conversation):
                if history == 'real':
                    sent = list(past)
                elif history == 'ninguno':
                    sent = []
                else:
                    other = rng.choice(pool)
                    sent = [{'role': 'user', 'text': x} for x in other[:t]] if t else []
                said = turn['cliente']
                start = time.perf_counter()
                try:
                    reply = bot.answer(said, sent)
                except Exception as error:
                    reply = {'text': '', 'status': 'excepcion', 'error': type(error).__name__}
                ms = (time.perf_counter() - start) * 1000
                past += [{'role': 'user', 'text': said}, {'role': 'assistant', 'text': reply.get('text', '')}]
                rows.append({'negocio': name, 'conv': c, 'turno': t, 'tipo': turn.get('tipo'), 'accion': turn.get('accion'),
                             'veredicto': judge(turn, reply, 'g57'), 'ms': round(ms, 3), 'respuesta': reply.get('text', ''),
                             'estado': reply.get('status'), 'celda': reply.get('cell'), 'cliente': said,
                             'claves': turn.get('claves'), 'candidata': (reply.get('candidate') or {}).get('text')})
    return rows

OFF = {'b0': ('soft_prefix', 'candidate_model'), 'prefijo': ('candidate_model',), 'tratamiento': ()}


def main():
    args = sys.argv[1:]
    def option(name):
        if name in args:
            k = args.index(name); value = args[k + 1]; del args[k:k + 2]; return value
        return None
    names = (option('--variantes') or 'b0,prefijo,tratamiento,otro_negocio,renombrado,reinicio').split(',')
    no_pairs, shuffled = option('--base-sin-pares'), option('--base-barajada')
    base, out, folders = Path(args[0]), Path(args[1]), args[2:]
    out.mkdir(parents=True, exist_ok=True)
    plans = {
        'b0': dict(base=base, off=OFF['b0']), 'prefijo': dict(base=base, off=OFF['prefijo']),
        'tratamiento': dict(base=base, off=()), 'otro_negocio': dict(base=base, off=(), other=True),
        'renombrado': dict(base=base, off=(), rename=True, strict=True), 'reinicio': dict(base=base, off=(), restart=True),
        'sin_instrucciones': dict(base=base, off=('follow_instructions',)),
        'b0_renombrado': dict(base=base, off=OFF['b0'], rename=True, strict=True),
        'sin_pares': dict(base=Path(no_pairs) if no_pairs else None, off=()),
        'pares_barajados': dict(base=Path(shuffled) if shuffled else None, off=()),
    }
    histories = {'sin_historial': ('history_features',), 'historial_ninguno': (), 'historial_barajado': ()}
    for name in names:
        if name in histories:
            mode = {'sin_historial': 'real', 'historial_ninguno': 'ninguno', 'historial_barajado': 'barajado'}[name]
            rows = replay(base, folders, histories[name], mode)
            plan = None
        else:
            plan = plans[name]
        if plan is not None and plan['base'] is None:
            continue
        rows = rows if plan is None else run(plan['base'], folders, 'g57', plan['off'], rename=plan.get('rename', False), other=plan.get('other', False),
                   restart=plan.get('restart', False), strict=plan.get('strict', False))
        total = totals(rows)
        (out / f'{name}.json').write_text(json.dumps({'totales': total, 'filas': rows}, ensure_ascii=False, indent=1))
        print(name, total['directa_si_no_utiles'], total['sin_respuesta_no_lo_se_o_cita'], 'p50/p95 ms', total['p50_ms'], total['p95_ms'],
              json.dumps(total['veredictos'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

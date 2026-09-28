"""Diagnóstico de recuperación de unidades (sin juez): ¿qué unidad pone primero cada puntuador?

python3 -m experiments.nube_recuperacion BASE.json SALIDA.json CARPETA_BANCO... [--puntuadores a,b]

Para cada turno con acción `responder` y claves, la unidad "alcanzable" es la que contiene todas las claves tal como
se muestra (texto de la unidad).  Se mide en los turnos alcanzables si el puntuador la pone primera (top1), entre las
tres primeras (top3) o las cinco (top5).  Los turnos sin ninguna unidad alcanzable (cuentas, datos repartidos) se
cuentan aparte.  Es diagnóstico de dirección de investigación sobre bancos ya gastados; no es una medida de mejora.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from leobot import Bot

BM25_K1, BM25_B = 1.2, 0.75


def containing(unit_text: str, keys) -> bool:
    text = f' {plain(unit_text)} '
    return all(f' {plain(k)} ' in text for k in keys if plain(k))


def unit_terms(unit, inherit=True):
    return list(unit['terms']) + (list(unit.get('inherited', ())) if inherit else [])


def scorer_mixture(bot, question_terms, units):
    """The engine's own ranker, full order (same formula as `ContextMixin._rank`)."""
    postings, total = bot._index(), len(units)
    bridge = bot._bridge()
    title = set(getattr(bot, 'context_title', ()))
    gains = {}
    for q in dict.fromkeys(question_terms):
        delta = min(max(bot._delta(q), 0.0), 1 - 1e-4)
        p0 = (len(postings.get(q, ())) + 0.5) / (total + 1)
        absent = 0.0 if q in title else math.log(1 - delta)
        best = {}
        for i in postings.get(q, ()):
            best[i] = math.log(delta / p0 + 1 - delta) - absent
        for a, d_a in bridge.get(q, ()):
            pa0 = (len(postings.get(a, ())) + 0.5) / (total + 1)
            gain = math.log(d_a / pa0 + 1 - d_a)
            for i in postings.get(a, ()):
                if i not in best or best[i] < gain:
                    best[i] = gain
        for i, g in best.items():
            gains[i] = gains.get(i, 0.0) + g
    return [gains.get(i, 0.0) for i in range(total)]


def make_bm25(inherit=True, own_weight=1.0):
    def scorer(bot, question_terms, units):
        total = len(units)
        docs = [unit_terms(u, inherit) for u in units]
        lengths = [len(d) or 1 for d in docs]
        avg = sum(lengths) / max(1, total)
        df = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        scores = [0.0] * total
        for q in dict.fromkeys(question_terms):
            n = df.get(q, 0)
            if not n:
                continue
            idf = math.log(1 + (total - n + 0.5) / (n + 0.5))
            for i, d in enumerate(docs):
                tf = d.count(q)
                if tf:
                    scores[i] += idf * tf * (BM25_K1 + 1) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * lengths[i] / avg))
        return scores
    return scorer


SCORERS = {
    'mezcla': scorer_mixture,
    'bm25': make_bm25(True),
    'bm25_sin_herencia': make_bm25(False),
}


def evaluate(base, folders, names):
    bot = Bot.load(base)
    totals = {n: {} for n in names}
    unreachable = {}
    n_biz = 0
    for name, text, instructions, conversations in businesses(folders):
        n_biz += 1
        bot.load_context(text, instructions)
        units = bot.context_units
        for conv in conversations:
            for turn in conv:
                if turn.get('accion', 'responder') != 'responder' or not [k for k in turn.get('claves') or [] if plain(k)]:
                    continue
                kind = turn.get('tipo')
                keys = turn['claves']
                gold = {i for i, u in enumerate(units) if u['kind'] != 'question' and containing(u['text'], keys)}
                if not gold:
                    unreachable[kind] = unreachable.get(kind, 0) + 1
                    continue
                terms = bot.context_terms(turn['cliente'])
                for n in names:
                    scores = SCORERS[n](bot, terms, units)
                    order = sorted((i for i, u in enumerate(units) if u['kind'] != 'question'),
                                   key=lambda i: (-scores[i], i))
                    row = totals[n].setdefault(kind, {'n': 0, 'top1': 0, 'top3': 0, 'top5': 0, 'sin_senal': 0})
                    row['n'] += 1
                    ranked_gold = [k for k, i in enumerate(order) if i in gold]
                    first = ranked_gold[0] if ranked_gold else 10 ** 9
                    if scores[order[0]] <= 0:
                        row['sin_senal'] += 1
                    row['top1'] += first < 1
                    row['top3'] += first < 3
                    row['top5'] += first < 5
    return {'negocios': n_biz, 'inalcanzables_por_tipo': unreachable, 'por_puntuador': totals}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    names = list(SCORERS)
    if '--puntuadores' in sys.argv:
        names = sys.argv[sys.argv.index('--puntuadores') + 1].split(',')
        args = [a for a in args if a != sys.argv[sys.argv.index('--puntuadores') + 1]]
    base, out, folders = args[0], Path(args[1]), args[2:]
    result = evaluate(base, folders, names)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    for n, per_type in result['por_puntuador'].items():
        n_all = sum(r['n'] for r in per_type.values())
        print(f'{n:20s}', 'n', n_all, ' '.join(f"{k}={sum(r[k] for r in per_type.values())/n_all:.3f}"
                                              for k in ('top1', 'top3', 'top5', 'sin_senal')))
        for kind, r in sorted(per_type.items()):
            print(f'   {kind:14s} n={r["n"]:4d} top1={r["top1"]/r["n"]:.3f} top3={r["top3"]/r["n"]:.3f} top5={r["top5"]/r["n"]:.3f}')
    print('inalcanzables', result['inalcanzables_por_tipo'])


if __name__ == '__main__':
    main()

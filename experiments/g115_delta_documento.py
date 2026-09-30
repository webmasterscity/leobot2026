"""G-115: δ contrastivo dentro del documento, contado en los negocios de enseñanza (solo datos; el motor no cambia).

python3 -m experiments.g115_delta_documento BASE.json SALIDA.json --variante reemplazo|media [--confundida]

Ver prereg/G-115-delta-contrastivo-en-documento.md.  Para cada turno directa/si_no con claves y alguna unidad que las contiene,
cada palabra q de la pregunta cuenta n(q), own(q) (alguna correcta la tiene) y other(q) (fracción de las demás unidades del mismo
documento que la tienen).  δ'(q) = max(0, (a − b)/(1 − b)), a = (own+1)/(n+2), b = (other+1)/(n+2).  n < 3: δ' agrupado de su clase
gramatical aprendida más frecuente; `rare_delta`: agrupado de las palabras con n de 1 a 5.  `--confundida`: la unidad correcta se
sustituye por otra al azar del mismo documento (semilla 0).
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

from experiments.g57_kiosco import businesses, plain
from experiments.g103_educar import contains
from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]
TEACH = ['congelado', 'congelado_g58', 'congelado_g59', 'congelado_g60', 'congelado_g61', 'congelado_g62', 'congelado_g63',
         'congelado_g64', 'desarrollo']
PI_MIN = 3
RARE = (1, 5)


def teaching_folders():
    return [str(w) for bank in TEACH for w in sorted((ROOT / 'results_v3/kiosco' / bank).iterdir()) if w.is_dir()]


def mixture(own, other, n):
    a, b = (own + 1) / (n + 2), (other + 1) / (n + 2)
    return max(0.0, (a - b) / (1 - b)) if b < 1 else 0.0


def count(bot, folders, confounded=False):
    rng = random.Random(0)
    n, own, other, tags = Counter(), Counter(), Counter(), {}
    turns = 0
    for _, text, instructions, conversations in businesses(folders):
        bot.load_context(text, instructions)
        units, sets = bot.context_units, bot._unit_sets()
        valid = [i for i, u in enumerate(units) if u['kind'] not in ('heading', 'question')]
        for conversation in conversations:
            for turn in conversation:
                if turn.get('tipo') not in ('directa', 'si_no') or turn.get('accion', 'responder') != 'responder':
                    continue
                keys = [k for k in turn.get('claves') or [] if plain(k)]
                gold = {i for i in valid if keys and contains(units[i]['text'], keys)}
                if not gold or len(valid) < 2:
                    continue
                if confounded:
                    gold = {rng.choice(valid)}
                rest = [i for i in valid if i not in gold]
                _, question = bot._question_part(turn['cliente'])
                words = [w for w in bot.split_words(question) if w[:1].isalnum()]
                if not words:
                    continue
                classes = bot.tag_words(words)
                turns += 1
                seen = set()
                for w, tag in zip(words, classes):
                    q = bot._term(w)
                    if q in seen:
                        continue
                    seen.add(q)
                    n[q] += 1
                    own[q] += any(q in sets[i] for i in gold)
                    other[q] += sum(q in sets[i] for i in rest) / len(rest) if rest else 0.0
                    tags.setdefault(q, Counter())[tag] += 1
    return n, own, other, tags, turns


def learn(n, own, other, tags):
    delta = {q: round(mixture(own[q], other[q], n[q]), 4) for q in n if n[q] >= PI_MIN}
    by_class = {}
    for q in n:
        cls = tags[q].most_common(1)[0][0]
        row = by_class.setdefault(cls, [0, 0.0, 0.0])
        row[0] += n[q]; row[1] += own[q]; row[2] += other[q]
    class_delta = {c: round(mixture(o, x, m), 4) for c, (m, o, x) in by_class.items()}
    for q in n:
        if n[q] < PI_MIN:
            delta[q] = class_delta[tags[q].most_common(1)[0][0]]
    rare = [q for q in n if RARE[0] <= n[q] <= RARE[1]]
    rare_delta = round(mixture(sum(own[q] for q in rare), sum(other[q] for q in rare), sum(n[q] for q in rare)), 4)
    return delta, rare_delta, class_delta


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    variant = sys.argv[sys.argv.index('--variante') + 1]
    t0 = time.process_time()
    bot = Bot.load(base)
    n, own, other, tags, turns = count(bot, teaching_folders(), '--confundida' in sys.argv)
    delta, rare_delta, class_delta = learn(n, own, other, tags)
    old = bot.context_model['delta']
    if variant == 'reemplazo':
        merged = dict(old)
        merged.update(delta)
        new_rare = rare_delta
    else:
        merged = dict(old)
        for q, d in delta.items():
            merged[q] = round((old[q] + d) / 2, 4) if q in old else d
        new_rare = round((bot.context_model['rare_delta'] + rare_delta) / 2, 4)
    bot.context_model['delta'] = merged
    bot.context_model['rare_delta'] = new_rare
    bot.context_model.setdefault('source', {})['g115'] = {'variante': variant, 'confundida': '--confundida' in sys.argv,
                                                           'turnos': turns, 'palabras': len(delta), 'clases': class_delta}
    bot.load_context('')
    bot.save(out)
    sample = {q: [old.get(q), merged[q]] for q in ('haber', 'el', 'a', 'hora', 'tener', 'estacionamiento', 'precio', 'costar')}
    print(json.dumps({'turnos': turns, 'palabras': len(delta), 'rare_delta': [bot.context_model.get('rare_delta'), new_rare],
                      'clases': class_delta, 'muestra': sample, 'cpu_s': round(time.process_time() - t0, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

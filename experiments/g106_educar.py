"""G-106: enseñanza del kiosco con saber general y comparación de cantidades (reutiliza la de G-103).

python3 -m experiments.g106_educar BASE_CON_SABER.json SALIDA.json CARPETA... [--sin-saber] [--sin-cantidades] [--sin-pares]

1. Cuenta, en los turnos de enseñanza, para cada tipo de enlace del saber general (`IsA>`, `Synonym<`, `IsA>>`…), cuántas veces
   una palabra del texto enlazada así con una palabra de la pregunta está en una unidad correcta (tasa por tipo, apoyo ≥ 30).
   Se guarda en `context_model['knowledge_share']`; no se guarda ninguna palabra.
2. Enseña el modelo de utilidad de G-103 con los rasgos nuevos y, salvo `--sin-pares`, solo la familia de pares `cmp`
   («palabra junto al número | comparación»).  Configuración congelada de G-103 (PAIR_SUPPORT=3, PAIR_KEEP=0.03, C_REG=0.1).
"""
from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault('PAIR_SUPPORT', '3')
os.environ.setdefault('PAIR_KEEP', '0.03')
os.environ.setdefault('C_REG', '0.1')
os.environ.setdefault('EPOCHS', '25')
os.environ['PAIR_FAMILIES'] = 'cmp'

import experiments.g103_educar as g103  # noqa: E402
from experiments.g57_kiosco import businesses, plain  # noqa: E402
from leobot import Bot  # noqa: E402

SUPPORT = 30
_family = g103.family


def family(key: str) -> str:
    return 'cmp' if key.split('|')[1].startswith('CMP:') else _family(key)


g103.family = family


def shares(bot: Bot, folders) -> dict:
    hits, seen, chance = {}, {}, [0, 0]
    for _, text, instructions, conversations in businesses(folders):
        bot.load_context(text, instructions)
        units, postings = bot.context_units, bot._index()
        title = set(bot.context_title)
        for conversation in conversations:
            for turn in conversation:
                keys = [k for k in turn.get('claves') or [] if plain(k)]
                if turn.get('accion', 'responder') != 'responder' or not keys:
                    continue
                gold = [u for u in units if u['kind'] != 'question' and g103.contains(u['text'], keys)]
                if not gold:
                    continue
                held = set().union(*(set(u['terms']) | set(u.get('inherited', ())) for u in gold))
                _, question = bot._question_part(turn['cliente'])
                terms = bot.context_terms(question)
                words = [w for w in bot.split_words(question) if w[:1].isalnum()]
                content = {bot._term(w) for w, tag in zip(words, bot.tag_words(words) or []) if tag in ('NOUN', 'PROPN', 'ADJ', 'VERB')}
                # Chance: any word of the text (not asked) that is in a right unit.
                others = [w for w in postings if w not in terms]
                chance[0] += sum(w in held for w in others)
                chance[1] += len(others)
                for q in dict.fromkeys(terms):
                    if q in title or q in postings or q not in content:
                        continue
                    for word, link in set(bot.knowledge_related(q)):
                        if word == q or word in terms or word not in postings:
                            continue
                        seen[link] = seen.get(link, 0) + 1
                        hits[link] = hits.get(link, 0) + (word in held)
    # As δ in G-57, the share is corrected for chance: (rate − P) / (1 − P), P the rate of any word of the text.
    base = chance[0] / chance[1] if chance[1] else 0.0
    table = {}
    for link, n in sorted(seen.items()):
        corrected = (hits[link] / n - base) / (1 - base)
        if n >= SUPPORT and corrected > 0:
            table[link] = round(corrected, 4)
    seen['_azar'] = round(base, 4)
    return table, seen


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    base, out, folders = args[0], args[1], args[2:]
    t0 = time.process_time()
    bot = Bot.load(base)
    table, seen = ({}, {}) if '--sin-saber' in sys.argv else shares(bot, folders)
    if table:
        bot.context_model['knowledge_share'] = table
    else:
        bot.context_model.pop('knowledge_share', None)
    if '--sin-cantidades' in sys.argv:
        bot.number_compare = False
    t_share = time.process_time() - t0
    tmp = out + '.saber.json'
    bot.save(tmp)
    print(json.dumps({'knowledge_share': table, 'apoyo': {k: seen[k] for k in table}, 'cpu_tasas_s': round(t_share, 1)},
                     ensure_ascii=False), flush=True)
    number_off = '--sin-cantidades' in sys.argv
    original_load = Bot.load

    def load(path):
        loaded = original_load(path)
        if number_off:
            loaded.number_compare = False
        return loaded
    Bot.load = staticmethod(load)
    g103.Bot.load = Bot.load
    sys.argv = ['g103_educar', tmp, out, *folders] + (['--sin-pares'] if '--sin-pares' in sys.argv else [])
    g103.main()
    os.remove(tmp)


if __name__ == '__main__':
    main()

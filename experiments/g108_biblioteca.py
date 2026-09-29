"""G-108: biblioteca compilada con las primeras frases de artículos de Wikipedia en español (texto escrito por personas).

python3 -m experiments.g108_biblioteca DIR_DATOS BASE.json SALIDA.json [--max-frases 90000] [--procesos 4] [--confundida]

1. Tildes: tabla «forma sin tilde → forma con tilde» contada en AnCora `train` y SQuAD-es; se usa solo si la forma acentuada es
   ≥ 90 % de los casos de esa forma sin tilde (≥ 3 casos).
2. Selección (preregistro G-108): artículos cuyo título es un lema de sustantivo común (léxico AnCora de la base o WordNet español);
   después, los más largos entre los demás, hasta `--max-frases`.  De cada artículo, sus dos primeras frases de ≤ 40 palabras.
3. Análisis sintáctico en paralelo con el motor (`compile_sentences`) y escritura con `write_library`.
`--confundida`: control adicional declarado; las mismas cantidades de frases, pero de artículos elegidos al azar (semilla 0) entre
los no seleccionados.
"""
from __future__ import annotations

import collections
import heapq
import json
import multiprocessing
import random
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

WORD = re.compile(r'\w+')
MAX_WORDS = 40
PER_ARTICLE = 2


def plain(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def accent_table(data: Path) -> dict:
    counts = collections.defaultdict(collections.Counter)
    for line in (data / 'es_ancora-ud-train.conllu').open(encoding='utf8'):
        if line and line[0].isdigit():
            form = line.split('\t')[1].lower()
            counts[plain(form)][form] += 1
    squad = json.loads((data / 'squad_es_train_v1.1.json').read_text(encoding='utf8'))
    seen = set()
    for article in squad['data']:
        for paragraph in article['paragraphs']:
            if paragraph['context'] in seen:
                continue
            seen.add(paragraph['context'])
            for w in WORD.findall(paragraph['context'].lower()):
                counts[plain(w)][w] += 1
    table = {}
    for key, row in counts.items():
        form, n = row.most_common(1)[0]
        total = sum(row.values())
        if form != key and n >= 3 and n >= 0.9 * total:
            table[key] = form
    return table


def restore(text: str, table: dict) -> str:
    def swap(m):
        w = m.group()
        new = table.get(w.lower())
        if new is None:
            return w
        if w.isupper() and len(w) > 1:
            return new.upper()
        return new[:1].upper() + new[1:] if w[:1].isupper() else new
    return WORD.sub(swap, text)


def articles(path: Path):
    """(title, paragraphs) from the plain dump: a title is a short line without closing punctuation whose next line starts
    with its first half."""
    title, body, previous = None, [], None
    with path.open(encoding='utf8', errors='replace') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if previous is not None:
                head = plain(previous.split(' (')[0].split(',')[0])
                opening = ' ' + plain(' '.join(line.split()[:4]))
                if previous and previous[-1] not in '.:;!?)"' and len(previous) < 80 and head and \
                        ' ' + head[:max(3, len(head) // 2)] in opening:
                    if title is not None:
                        yield title, body
                    title, body = previous, []
                elif title is not None and previous:
                    body.append(previous)
            previous = line
    if title is not None:
        if previous:
            body.append(previous)
        yield title, body


def nouns(base: Path, data: Path) -> set:
    model = json.loads(base.read_text(encoding='utf8'))['syntax_model']
    lemmas = model.get('lemma_counts', {})
    out = set()
    for key in model.get('lexicon', {}):
        word, tag = key.rsplit('\x1f', 1)
        if tag == 'NOUN':
            row = lemmas.get(word) or lemmas.get(word.lower())
            out.add(plain(max(row, key=row.get) if row else word))
    for _, el in ET.iterparse(data / 'omw-1.4/omw-es/omw-es.xml'):
        if el.tag == 'Lemma' and el.get('partOfSpeech') == 'n':
            out.add(plain(el.get('writtenForm')))
    return out


_BOT = None


def _init(base):
    global _BOT
    from leobot import Bot
    _BOT = Bot.load(base)


def _compile(job):
    document, sentences = job
    return _BOT.compile_sentences(sentences, document)


def first_sentences(bot, body, table):
    out = []
    for paragraph in body[:2]:
        for sentence in bot._document_sentences(restore(paragraph, table)):
            if len(sentence.split()) <= MAX_WORDS and sentence[-1:] in '.!?':
                out.append(sentence)
            if len(out) >= PER_ARTICLE:
                return out
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    def option(name, default):
        return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default
    data, base, out = Path(args[0]), Path(args[1]), Path(args[2])
    limit, procs = option('--max-frases', 90000), option('--procesos', 4)
    t0 = time.process_time()
    from leobot import Bot
    bot = Bot.load(base)
    table = accent_table(data)
    common = nouns(base, data)
    t_tables = time.process_time() - t0
    chosen, longest, rest, total_articles = [], [], [], 0
    rng = random.Random(0)
    for title, body in articles(data / 'wiki_es.all'):
        total_articles += 1
        size = sum(len(p) for p in body)
        if plain(title) in common:
            chosen.append((title, body[:2]))
        else:
            item = (size, title, body[:2])
            if len(longest) < limit:
                heapq.heappush(longest, item)
            elif size > longest[0][0]:
                heapq.heapreplace(longest, item)
            if rng.random() < 0.02:
                rest.append((title, body[:2]))
    jobs, count = [], 0
    for title, body in chosen:
        sentences = first_sentences(bot, body, table)
        if sentences and count + len(sentences) <= limit:
            jobs.append((f'Wikipedia: {restore(title, table)}', sentences))
            count += len(sentences)
    from_nouns = count
    for _, title, body in sorted(longest, reverse=True):
        if count >= limit:
            break
        sentences = first_sentences(bot, body, table)
        if sentences:
            jobs.append((f'Wikipedia: {restore(title, table)}', sentences))
            count += len(sentences)
    if '--confundida' in sys.argv:
        picked = {title for title, _ in jobs}
        rng.shuffle(rest)
        control, n = [], 0
        for title, body in rest:
            if n >= count:
                break
            if f'Wikipedia: {restore(title, table)}' in picked:
                continue
            sentences = first_sentences(bot, body, table)
            if sentences:
                control.append((f'Wikipedia: {restore(title, table)}', sentences))
                n += len(sentences)
        jobs = control
    t_select = time.process_time() - t0
    start = time.time()
    with multiprocessing.Pool(procs, initializer=_init, initargs=(str(base),)) as pool:
        rows = [row for part in pool.imap(_compile, jobs, chunksize=64) for row in part]
    size = bot.write_library(rows, out, meta={
        'fuente': 'wikipedia_multilingual/raw/es.all', 'sha256': '48f67d80244308f3e1010240f0cb93121a1d14e70f79093a5e21653125d0b643',
        'articulos_leidos': total_articles, 'articulos': len(jobs), 'frases': len(rows), 'de_sustantivos': from_nouns,
        'confundida': '--confundida' in sys.argv})
    print(json.dumps({'articulos_leidos': total_articles, 'articulos_sustantivo': len(chosen), 'articulos': len(jobs),
                      'frases': len(rows), 'frases_de_sustantivos': from_nouns, 'analizadas': sum(bool(r[2]) for r in rows),
                      'tildes': len(table), 'cpu_tablas_s': round(t_tables, 1), 'cpu_seleccion_s': round(t_select, 1),
                      'pared_analisis_s': round(time.time() - start, 1), 'bytes': size}, ensure_ascii=False))


if __name__ == '__main__':
    main()

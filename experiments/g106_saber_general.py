"""G-106/G-107: reúne el saber general de fuentes humanas en un archivo de datos (fuera del motor).

python3 -m experiments.g106_saber_general DIR_DATOS

Entradas (en DIR_DATOS, descargadas con su SHA registrado en la salida):
- `omw-1.4/omw-es/omw-es.xml` y `omw-1.4/omw-en/omw-en.xml` (Open Multilingual Wordnet 1.4: MCR español sobre PWN 3.0);
- `conceptnet_es.tsv`: aristas de ConceptNet 5.7 con algún extremo en español (filtradas de `conceptnet-assertions-5.7.0.csv.gz`);
- `conceptnet_en_cs.tsv`: aristas de sentido común con ambos extremos en inglés.
Salida `saber_general.json`: relaciones (relación, palabra a, palabra b, fuente), plantillas humanas en español por relación y
caminos cerrados / abiertos por relación (para la transitividad aprendida).  Los nombres de relación son los de ConceptNet; para
WordNet se usa la correspondencia que ConceptNet mismo aplica a WordNet (hiperónimo → IsA, meronimia de parte y de miembro → PartOf,
de sustancia → MadeOf, antónimo → Antonym, mismo synset → Synonym, causa → Causes, implicación → Entails, similar → SimilarTo).
No se traducen frases: del inglés solo pasan aserciones cuyos dos extremos son una palabra con traducción humana inequívoca.
"""
from __future__ import annotations

import collections
import hashlib
import json
import random
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

WORDNET = {'hypernym': 'IsA', 'instance_hypernym': 'IsA', 'mero_part': 'PartOf', 'mero_member': 'PartOf',
           'mero_substance': 'MadeOf', 'causes': 'Causes', 'entails': 'Entails', 'similar': 'SimilarTo'}
SKIP_ES = {'ExternalURL', 'FormOf', 'dbpedia'}
KEEP_EN = {'UsedFor', 'AtLocation', 'CapableOf', 'PartOf', 'HasA', 'MadeOf', 'HasProperty', 'IsA', 'Causes', 'HasPrerequisite',
           'HasSubevent', 'Desires', 'CausesDesire', 'MotivatedByGoal', 'ReceivesAction', 'LocatedNear', 'CreatedBy', 'DefinedAs',
           'NotDesires', 'NotCapableOf', 'NotHasProperty', 'HasFirstSubevent', 'HasLastSubevent', 'SymbolOf'}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def word_of(uri: str) -> str:
    return uri.split('/')[3].replace('_', ' ')


def wordnet(path: Path):
    """synset → lemmas, and relations between synsets (and antonyms between senses)."""
    lemmas, relations, sense_synset, antonyms = collections.defaultdict(list), [], {}, []
    for _, el in ET.iterparse(path):
        if el.tag == 'LexicalEntry':
            lemma = el.find('Lemma').get('writtenForm')
            for sense in el.findall('Sense'):
                synset = '-'.join(sense.get('synset').split('-')[-2:])
                lemmas[synset].append(lemma)
                sense_synset[sense.get('id')] = synset
                for rel in sense.findall('SenseRelation'):
                    if rel.get('relType') == 'antonym':
                        antonyms.append((synset, rel.get('target')))
            el.clear()
        elif el.tag == 'Synset':
            here = '-'.join(el.get('id').split('-')[-2:])
            for rel in el.findall('SynsetRelation'):
                kind = WORDNET.get(rel.get('relType'))
                if kind:
                    relations.append((kind, here, '-'.join(rel.get('target').split('-')[-2:])))
            el.clear()
    antonyms = [(a, sense_synset[t]) for a, t in antonyms if t in sense_synset]
    return lemmas, relations, antonyms


def main():
    data = Path(sys.argv[1])
    t0 = time.process_time()
    edges = set()
    # 1. WordNet: relations are between synsets (PWN 3.0); the Spanish words are the MCR lemmas of each synset.
    es_lemmas, _, _ = wordnet(data / 'omw-1.4/omw-es/omw-es.xml')
    en_lemmas, relations, antonyms = wordnet(data / 'omw-1.4/omw-en/omw-en.xml')
    for synset, words in es_lemmas.items():
        words = sorted(set(words))
        for a in words:
            for b in words:
                if a < b:
                    edges.add(('Synonym', a, b, 'wordnet-es'))
    for kind, a, b in relations:
        # PWN stores «a has part b» as mero_part on a: ConceptNet writes PartOf(b, a).
        if kind in ('PartOf', 'MadeOf'):
            a, b = b, a
        for x in sorted(set(es_lemmas.get(a, ()))):
            for y in sorted(set(es_lemmas.get(b, ()))):
                if x != y:
                    edges.add((kind, x, y, 'wordnet-es'))
    for a, b in antonyms:
        for x in sorted(set(es_lemmas.get(a, ()))):
            for y in sorted(set(es_lemmas.get(b, ()))):
                if x != y:
                    edges.add(('Antonym', x, y, 'wordnet-es'))
    n_wordnet = len(edges)
    # 2. ConceptNet, both ends in Spanish; human templates of Open Mind in Spanish.
    templates = collections.defaultdict(collections.Counter)
    votes = collections.defaultdict(collections.Counter)
    for line in (data / 'conceptnet_es.tsv').open(encoding='utf8'):
        r, a, b, d, w, surface = line.rstrip('\n').split('\t')
        rel = r.split('/')[2]
        if a.startswith('/c/es/') and b.startswith('/c/es/'):
            if rel not in SKIP_ES and 'dbpedia' not in r:
                edges.add((rel, word_of(a), word_of(b), 'conceptnet-' + d.split('/')[2]))
            if surface and '[[' in surface:
                parts = surface.split('[[')
                if len(parts) == 3:
                    first, rest = parts[1].split(']]', 1)
                    second, tail = parts[2].split(']]', 1)
                    # The template keeps the people's words; the slots are {0} (start) and {1} (end) as in the assertion.
                    order = ('{0}', '{1}') if first.strip().lower() == word_of(a).lower() or second.strip().lower() == word_of(b).lower() \
                        else ('{1}', '{0}')
                    templates[rel][(parts[0] + order[0] + rest + order[1] + tail).strip()] += 1
        elif rel == 'Synonym' and d.startswith('/d/wiktionary'):
            es, en = (a, b) if a.startswith('/c/es/') else (b, a)
            if en.startswith('/c/en/'):
                x, y = word_of(es), word_of(en).lower()
                if ' ' not in x and ' ' not in y:
                    votes[y][x] += 1
    n_es = len(edges) - n_wordnet
    # Human translations also from WordNet: an English and a Spanish lemma of the same synset.
    for synset, words in en_lemmas.items():
        for y in words:
            for x in es_lemmas.get(synset, ()):
                if ' ' not in x and ' ' not in y:
                    votes[y.lower()][x] += 1

    def translate(word):
        ranked = votes.get(word)
        if not ranked:
            return None
        top = ranked.most_common(2)
        return top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else None
    # 3. Open Mind in English, one-word ends with an unambiguous human translation; closure statistics on all English edges.
    by_rel = collections.defaultdict(lambda: collections.defaultdict(set))
    for line in (data / 'conceptnet_en_cs.tsv').open(encoding='utf8'):
        r, a, b, d, w, surface = line.rstrip('\n').split('\t')
        rel = r.split('/')[2]
        x, y = word_of(a).lower(), word_of(b).lower()
        by_rel[rel][x].add(y)
        if rel in KEEP_EN and d.startswith('/d/conceptnet/4') and ' ' not in x and ' ' not in y:
            tx, ty = translate(x), translate(y)
            if tx and ty and tx != ty:
                edges.add((rel, tx, ty, 'conceptnet-en-traducido'))
    n_en = len(edges) - n_wordnet - n_es
    # Closure: of the paths a→b→c (b ≠ a, c ∉ {a, b}), how many are closed by an asserted a→c.  Sampled, fixed seed.
    rng, closure = random.Random(0), {}
    for rel, table in sorted(by_rel.items()):
        heads = sorted(table)
        rng.shuffle(heads)
        paths = closed = 0
        for a in heads:
            for b in sorted(table[a]):
                for c in sorted(table.get(b, ())):
                    if c != a and c != b:
                        paths += 1
                        closed += c in table[a]
            if paths >= 200000:
                break
        closure[rel] = [closed, paths]
    out = {'fuentes': {'omw-1.4.tar.xz': sha(data / 'omw-1.4.tar.xz'),
                       'conceptnet-assertions-5.7.0.csv.gz': sha(data / 'conceptnet-assertions-5.7.0.csv.gz')},
           'relaciones': sorted(edges),
           'plantillas': {rel: [t for t, _ in c.most_common()] for rel, c in sorted(templates.items())},
           'cierre': closure,
           'cuentas': {'wordnet': n_wordnet, 'conceptnet_es': n_es, 'conceptnet_en_traducido': n_en, 'total': len(edges),
                       'por_relacion': dict(collections.Counter(e[0] for e in edges).most_common())},
           'cpu_s': round(time.process_time() - t0, 1)}
    (data / 'saber_general.json').write_text(json.dumps(out, ensure_ascii=False), encoding='utf8')
    print(json.dumps({k: out[k] for k in ('cuentas', 'cierre', 'cpu_s')}, ensure_ascii=False))
    print(json.dumps(out['plantillas'], ensure_ascii=False))


if __name__ == '__main__':
    main()

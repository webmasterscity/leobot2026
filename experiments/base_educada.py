"""Bot educado de forma general, para la validación común con --base.

python3 -m experiments.base_educada ANCORA_DIR SALIDA.json [--clases-mlqa]

Educación, toda anterior e independiente de cualquier conjunto de validación:
- sintaxis y separación de palabras con UD AnCora `train` (como G-35), con los
  rasgos morfológicos si el motor los acepta (G-41: negación e interrogativas)
  y los lemas si los acepta (G-44);
- lectura con los 2000 ejemplos MLQA de educación de G-28b (semilla 2828);
- G-53: la clase de respuesta de cada clase de pregunta, contada en SQuAD-es v1.1 `train` (87 595 preguntas);
- G-56: qué palabras de cada pregunta dice la oración que contiene la respuesta (SQuAD-es `train` y MLQA);
- G-54: las formas verbales de cada persona y las de pronombres y posesivos de primera y segunda (lema, clase y
  rasgos → forma), contadas además en UD COSER `train` (habla oral transcrita), solo para esa tabla: no entran al
  analizador.  GSD no, porque mezcla el voseo («salís») con el tuteo.
Se guarda con Bot.save para que cada conversación parta de una copia nueva.
"""
from __future__ import annotations

import inspect
import json
import random
import resource
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import EDU_SEED, archive, rows
from experiments.ud_ancora_completo import sentences
from leobot import Bot


SQUAD_TRAIN_URL = 'https://raw.githubusercontent.com/ccasimiro88/TranslateAlignRetrieve/master/SQuAD-es-v1.1/train-v1.1-es.json'
SQUAD_TRAIN_SHA = '196cfa14b6ba7d903f02e6edc20485bb959b72c965b6a2d6883b8ffd74dc2c3b'
SQUAD_TRAIN_CACHE = Path('/tmp/squad_es_train_v1.1.json')


def squad_es_train():
    import hashlib
    import urllib.request
    data = SQUAD_TRAIN_CACHE.read_bytes() if SQUAD_TRAIN_CACHE.exists() else \
        urllib.request.urlopen(SQUAD_TRAIN_URL, timeout=120).read()
    if hashlib.sha256(data).hexdigest() != SQUAD_TRAIN_SHA:
        raise RuntimeError('SQuAD-es train cambió.')
    return [(qa['question'], qa['answers'][0]['text']) for article in json.loads(data)['data']
            for paragraph in article['paragraphs'] for qa in paragraph['qas'] if qa['answers']]


def answer_sentence(context: str, start: int) -> str:
    """G-56: the sentence of a context that holds the answer (between the
    periods around its first character).  Text preparation only."""
    left = context.rfind('. ', 0, max(start, 0)) + 2 if start > 0 else 0
    right = context.find('. ', max(start, 0))
    return context[left if left > 1 else 0: right + 1 if right >= 0 else len(context)]


def squad_es_train_sentences():
    """G-56: (question, sentence holding the answer) for SQuAD-es v1.1 `train`."""
    data = json.loads(SQUAD_TRAIN_CACHE.read_bytes())
    return [(qa['question'], answer_sentence(paragraph['context'], qa['answers'][0]['answer_start']))
            for article in data['data'] for paragraph in article['paragraphs'] for qa in paragraph['qas']
            if qa['answers']]


def main():
    ancora, out = Path(sys.argv[1]), Path(sys.argv[2])
    bot = Bot(); t0 = time.process_time()
    with_feats = 'feats' in inspect.signature(bot.observe_parsed_sentence).parameters
    with_lemmas = 'lemmas' in inspect.signature(bot.observe_parsed_sentence).parameters
    for block, idx in sentences(ancora / 'es_ancora-ud-train.conllu'):
        cols = [block[i].split('\t') for i in idx]
        words = [c[1] for c in cols]
        extra = {'feats': [c[5] for c in cols]} if with_feats else {}
        if with_lemmas:
            extra['lemmas'] = [c[2] for c in cols]
        bot.observe_parsed_sentence(words, [c[3] for c in cols], [int(c[6]) for c in cols],
                                    [c[7].split(':')[0] for c in cols], **extra)
        position = {c[0]: k for k, c in enumerate(cols)}
        for line in block:
            first = line.split('\t')[0]
            if not line.startswith('#') and '-' in first:
                a, b = first.split('-')
                bot.observe_multiword(line.split('\t')[1], [words[position[str(i)]] for i in range(int(a), int(b) + 1)])
    if hasattr(bot, 'observe_forms'):
        # G-54: forms from a treebank of speech, forms only.
        for name in ('es_coser-ud-train.conllu',):
            for block, idx in sentences(ancora / name):
                cols = [block[i].split('\t') for i in idx]
                bot.observe_forms([c[1] for c in cols], [c[3] for c in cols], [c[2] for c in cols], [c[5] for c in cols])
    bot.consolidate_syntax()
    test = rows(archive(), 'MLQA_V1/test/test-context-es-question-es.json')
    for e in random.Random(EDU_SEED).sample(test, 2300)[:2000]:
        bot.observe_reading_example(e['context'], e['question'], e['answers'][0])
    bot.consolidate_reading()
    # G-53: the kind of answer each kind of question takes, counted from the
    # SQuAD-es v1.1 training questions (question and answer only; no parsing),
    # once the words that ask are learned.
    # Control preregistrado de G-53 («educación sin SQuAD-es»): con --clases-mlqa las clases
    # se cuentan solo en los 2000 ejemplos MLQA de educación.
    if '--clases-mlqa' in sys.argv:
        pairs = [(e['question'], e['answers'][0]) for e in random.Random(EDU_SEED).sample(test, 2300)[:2000]]
    else:
        pairs = squad_es_train()
    for question, answer in pairs:
        bot.observe_answer_kind(question, answer)
    if hasattr(bot, 'observe_question_presence'):
        # G-56: which question words the sentence holding the answer says.
        squad_es_train()                        # checks the cached file's SHA-256
        for e in random.Random(EDU_SEED).sample(test, 2300)[:2000]:
            bot.observe_question_presence(e['question'], answer_sentence(e['context'], e['context'].find(e['answers'][0])))
        for question, sentence in squad_es_train_sentences():
            bot.observe_question_presence(question, sentence)
    bot.save(out)
    print(json.dumps({'feats': with_feats, 'cpu_s': round(time.process_time() - t0, 1), 'mib': round(out.stat().st_size / 2**20, 1),
                      'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}))


if __name__ == '__main__':
    main()

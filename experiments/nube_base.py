"""Base educada reconstruida en la sesión de nube (fuentes alcanzables: AnCora y SQuAD-es).

python3 -m experiments.nube_base DIR_DATOS SALIDA.json

Es la parte general de `base_educada` sin lo que no se puede descargar desde el contenedor (MLQA, COSER, MFAQ):
- sintaxis, separación de palabras, rasgos y lemas con UD AnCora `train`;
- G-53: clase de respuesta de cada clase de pregunta, contada en SQuAD-es v1.1 `train`;
- G-56: qué palabras de la pregunta dice la oración con la respuesta (SQuAD-es `train`).
No usa el motor de otro modo que sus métodos públicos de observación; no toca `leobot/`.
"""
from __future__ import annotations

import inspect
import json
import resource
import sys
import time
from pathlib import Path

from experiments.base_educada import answer_sentence
from experiments.ud_ancora_completo import sentences
from leobot import Bot


def main():
    data, out = Path(sys.argv[1]), Path(sys.argv[2])
    bot, t0 = Bot(), time.process_time()
    with_feats = 'feats' in inspect.signature(bot.observe_parsed_sentence).parameters
    with_lemmas = 'lemmas' in inspect.signature(bot.observe_parsed_sentence).parameters
    for block, idx in sentences(data / 'es_ancora-ud-train.conllu'):
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
    bot.consolidate_syntax()
    squad = json.loads((data / 'squad_es_train_v1.1.json').read_text(encoding='utf8'))
    pairs = [(qa['question'], qa['answers'][0]['text'], paragraph['context'], qa['answers'][0]['answer_start'])
             for article in squad['data'] for paragraph in article['paragraphs'] for qa in paragraph['qas']
             if qa['answers']]
    for question, answer, _, _ in pairs:
        bot.observe_answer_kind(question, answer)
    if hasattr(bot, 'observe_question_presence'):
        for question, _, context, start in pairs:
            bot.observe_question_presence(question, answer_sentence(context, start))
    bot.save(out)
    print(json.dumps({'cpu_s': round(time.process_time() - t0, 1), 'mib': round(out.stat().st_size / 2**20, 1),
                      'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                      'pairs': len(pairs)}))


if __name__ == '__main__':
    main()

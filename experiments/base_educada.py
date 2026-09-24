"""Bot educado de forma general, para la validación común con --base.

python3 -m experiments.base_educada ANCORA_DIR SALIDA.json [SQUAD_ES_TRAIN.json]

Educación, toda anterior e independiente de cualquier conjunto de validación:
- sintaxis y separación de palabras con UD AnCora `train` (como G-35), con los
  rasgos morfológicos si el motor los acepta (G-41: negación e interrogativas)
  y los lemas si los acepta (G-44);
- lectura con los 2000 ejemplos MLQA de educación de G-28b (semilla 2828);
- G-48, si el motor lo acepta: pares de caminos de esos 2000 ejemplos y, si se
  da SQuAD-es v1.1 `train` (SHA-256 fijado), de 20 000 de sus ejemplos
  muestreados con la misma semilla (solo caminos: el lector no se reeduca).
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

from hashlib import sha256

from experiments.g28b_gap_correspondences import EDU_SEED, archive, rows
from experiments.ud_ancora_completo import sentences
from leobot import Bot


SQUAD_TRAIN_SHA = '196cfa14b6ba7d903f02e6edc20485bb959b72c965b6a2d6883b8ffd74dc2c3b'
SQUAD_EXAMPLES = 20000


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
    bot.consolidate_syntax()
    test = rows(archive(), 'MLQA_V1/test/test-context-es-question-es.json')
    for e in random.Random(EDU_SEED).sample(test, 2300)[:2000]:
        bot.observe_reading_example(e['context'], e['question'], e['answers'][0])
    bot.consolidate_reading()
    paths = {}
    if hasattr(bot, 'observe_answer_paths'):
        examples = [(e['context'], e['question'], e['answers'][0])
                    for e in random.Random(EDU_SEED).sample(test, 2300)[:2000]]
        if len(sys.argv) > 3:
            data = Path(sys.argv[3]).read_bytes()
            if sha256(data).hexdigest() != SQUAD_TRAIN_SHA:
                raise RuntimeError('SQuAD-es train cambió.')
            squad = sorted(({'id': q['id'], 'context': p['context'], 'question': q['question'],
                             'answer': q['answers'][0]['text']}
                            for a in json.loads(data)['data'] for p in a['paragraphs'] for q in p['qas']),
                           key=lambda r: r['id'])
            examples += [(r['context'], r['question'], r['answer'])
                         for r in random.Random(EDU_SEED).sample(squad, SQUAD_EXAMPLES)]
        for context, question, answer in examples:
            status = bot.observe_answer_paths(context, question, answer)['status']
            paths[status] = paths.get(status, 0) + 1
        paths.update(bot.consolidate_answer_paths())
    bot.save(out)
    print(json.dumps({'feats': with_feats, 'caminos': paths, 'cpu_s': round(time.process_time() - t0, 1), 'mib': round(out.stat().st_size / 2**20, 1),
                      'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}))


if __name__ == '__main__':
    main()

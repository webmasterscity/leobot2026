"""Bot educado de forma general, para la validación común con --base.

python3 -m experiments.base_educada ANCORA_DIR SALIDA.json

Educación, toda anterior e independiente de cualquier conjunto de validación:
- sintaxis y separación de palabras con UD AnCora `train` (como G-35);
- lectura con los 2000 ejemplos MLQA de educación de G-28b (semilla 2828).
Se guarda con Bot.save para que cada conversación parta de una copia nueva.
"""
from __future__ import annotations

import json
import random
import resource
import sys
import time
from pathlib import Path

from experiments.g28b_gap_correspondences import EDU_SEED, archive, rows
from experiments.ud_ancora_completo import sentences
from leobot import Bot


def main():
    ancora, out = Path(sys.argv[1]), Path(sys.argv[2])
    bot = Bot(); t0 = time.process_time()
    for block, idx in sentences(ancora / 'es_ancora-ud-train.conllu'):
        cols = [block[i].split('\t') for i in idx]
        words = [c[1] for c in cols]
        bot.observe_parsed_sentence(words, [c[3] for c in cols], [int(c[6]) for c in cols],
                                    [c[7].split(':')[0] for c in cols])
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
    bot.save(out)
    print(json.dumps({'cpu_s': round(time.process_time() - t0, 1), 'mib': round(out.stat().st_size / 2**20, 1),
                      'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}))


if __name__ == '__main__':
    main()

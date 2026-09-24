"""G-51, control de marcos barajados: la base educada con los marcos de identidad aprendidos de preguntas que no
corresponden a su respuesta.

python3 -m experiments.g51_marcos_barajados BASE.json SALIDA.json

Parte de la base educada de siempre y vuelve a aprender solo los marcos de identidad, con los mismos 2000 ejemplos
MLQA de educación, en el mismo orden, con las preguntas reasignadas al azar entre los ejemplos (semilla 5151):
cada contexto y su respuesta llevan la pregunta de otro ejemplo.  Según el preregistro, así no debe aprenderse
ningún verbo de identidad.  Se informa además, como dato y no como criterio, la variante en la que cada ejemplo
conserva su pregunta y la respuesta se sustituye por un tramo al azar de la misma frase.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from experiments.g28b_gap_correspondences import EDU_SEED, archive, rows
from leobot import Bot
from leobot.reading import _TOKEN, _is_word, _norm


def answer_sentence(bot, context, answer):
    target = [_norm(t) for t in _TOKEN.findall(answer) if _is_word(t)]
    for sentence in bot._document_sentences(context):
        words = [_norm(t) for t in _TOKEN.findall(sentence) if _is_word(t)]
        if target and any(words[k:k + len(target)] == target for k in range(len(words) - len(target) + 1)):
            return sentence
    return None


def relearn(bot, examples):
    bot.reading_model['identity_frames'] = {}
    for question, sentence, answer in examples:
        if sentence is not None:
            bot._observe_identity_frame(question, sentence, answer)
    bot._compile_identity_frames()
    return {'marcos': bot.reading_model['identity_frames_learned'], 'verbos': bot.reading_model['identity_verbs']}


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    test = rows(archive(), 'MLQA_V1/test/test-context-es-question-es.json')
    education = random.Random(EDU_SEED).sample(test, 2300)[:2000]
    bot = Bot.load(base)
    original = {'marcos': bot.reading_model.get('identity_frames_learned'), 'verbos': bot.reading_model.get('identity_verbs')}
    sentences = [answer_sentence(bot, e['context'], e['answers'][0]) for e in education]
    rng = random.Random(5151)
    order = list(range(len(education)))
    rng.shuffle(order)
    # Informative variant: own question, a random span of the same length in the same sentence as the answer.
    spans = []
    for e, sentence in zip(education, sentences):
        words = [t for t in _TOKEN.findall(sentence) if _is_word(t)] if sentence else []
        size = max(1, len([t for t in _TOKEN.findall(e['answers'][0]) if _is_word(t)]))
        start = rng.randrange(max(1, len(words) - size + 1)) if words else 0
        spans.append(' '.join(words[start:start + size]))
    variante = relearn(bot, [(e['question'], s, a) for e, s, a in zip(education, sentences, spans)])
    barajados = relearn(bot, [(education[i]['question'], sentences[k], education[k]['answers'][0])
                              for k, i in enumerate(order)])
    bot.save(out)
    report = {'original': original, 'marcos_barajados': barajados, 'variante_tramo_al_azar': variante}
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

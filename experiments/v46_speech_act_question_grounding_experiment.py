"""V4.6: prevent question-as-assertion corruption and ground questions from facts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.bot import Bot
from leobot.core import KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v46_speech_act_question_grounding.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def main():
    bot=Bot(KnowledgeBase())
    for text in [
        'equipo alfa enlaza modulo rojo',
        'grupo beta enlaza pieza azul',
        'unidad gamma enlaza nodo verde',
    ]:
        learned=bot.respond(text)
    pred=learned['predicate']
    for i in range(102):
        assert bot.respond(f'sujeto consulta {i} enlaza objeto consulta {i}')['status']=='stored'

    facts_before=bot.kb.stats()['facts']; hash_before=code_hash()
    q1=bot.respond('¿que enlaza sujeto consulta 0?')
    mid_facts=bot.kb.stats()['facts']
    q2=bot.respond('¿que enlaza sujeto consulta 1?')
    after_learning_facts=bot.kb.stats()['facts']
    que_known=bool(bot.kb.known_entities({'que'}))

    exact_question_memory={
        '¿que enlaza sujeto consulta 0?',
        '¿que enlaza sujeto consulta 1?',
    }
    correct=0; mutation=0; times=[]; exact_hits=0
    baseline=bot.kb.stats()['facts']
    for i in range(2,102):
        text=f'¿que enlaza sujeto consulta {i}?'
        exact_hits += text in exact_question_memory
        t=perf_counter();r=bot.respond(text);times.append((perf_counter()-t)*1000)
        atoms=[p.get('atom',{}) for p in r.get('proofs',[])]
        correct += r.get('status')=='bindings' and any(
            a.get('pred')==pred and a.get('args')==[f'sujeto consulta {i}',f'objeto consulta {i}']
            for a in atoms
        )
        mutation += bot.kb.stats()['facts'] != baseline
        baseline=bot.kb.stats()['facts']

    wrong_anchor=0
    facts_pre_wrong=bot.kb.stats()['facts']
    for i in range(100):
        r=bot.respond(f'¿que separa sujeto consulta {i}?')
        wrong_anchor += r.get('status') in ('unrecognized','grounding_pending')
    facts_post_wrong=bot.kb.stats()['facts']
    hash_after=code_hash()

    report={
        'version':'0.4.6',
        'experiment':'speech_act_gate_and_grounded_questions',
        'code_hash_before_frozen_eval':hash_before,
        'code_hash_after_frozen_eval':hash_after,
        'code_unchanged_during_frozen_phase':hash_before==hash_after,
        'primitive_predicate':pred,
        'question_learning':{
            'first_status':q1.get('status'),
            'second_status':q2.get('status'),
            'facts_before':facts_before,
            'facts_after_first':mid_facts,
            'facts_after_second':after_learning_facts,
            'question_word_became_entity':que_known,
            'learned_parse':bot.language.parse('¿que enlaza sujeto consulta 99?'),
        },
        'heldout_questions':{
            'correct_answers':correct,'cases':100,
            'fact_mutations':mutation,
            'exact_question_memory_hits':exact_hits,
            'median_response_ms':median(times),
        },
        'changed_relation_control':{
            'nonassertive_or_pending':wrong_anchor,'cases':100,
            'fact_delta':facts_post_wrong-facts_pre_wrong,
        },
        'limits':[
            'El detector de acto interrogativo usa señales superficiales y todavía no cubre todas las formas pragmáticas del español.',
            'La construcción interrogativa se aprende porque existen hechos estructurados que la fundamentan; no implica comprensión abierta de preguntas arbitrarias.',
            'Evaluación interna y sintética; no demuestra AGI ni ASI.',
        ],
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

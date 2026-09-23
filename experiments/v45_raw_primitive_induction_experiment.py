"""V4.5: induce an opaque primitive relation from repeated raw assertions.

No entity names, semantic predicate, arity annotation, or structured facts are
provided for the support utterances.  Token anti-unification is promoted only
when one unambiguous binary surface has >=3 independent supports and both role
values vary across every support.  The experiment then checks whether invented
primitives can seed a different learned conjunctive concept.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v45_raw_primitive_induction.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def main():
    bot=Bot(KnowledgeBase(),raw_relation_min_support=3)
    held=[f'sujeto inedito {i} enlaza objeto inedito {i}' for i in range(100)]
    pre_parsed=sum(bot.language.parse(t)['status']=='parsed' for t in held)

    # Noise has no repeated informative lexical anchor.
    for i in range(60):
        bot.observe_raw_relation(f'ruidoizq{i} marca{i} ruidoder{i}',source='v45_noise')
    promotions_after_noise=len(bot.raw_relation_promotions)

    support_a=[
        'equipo alfa enlaza modulo rojo',
        'grupo beta enlaza pieza azul',
        'unidad gamma enlaza nodo verde',
    ]
    support_b=[
        'objeto cobre reposa sector norte',
        'artefacto plata reposa zona sur',
        'componente oro reposa area este',
    ]
    episodic=set(support_a+support_b)
    train_times=[]; reports=[]
    for text in support_a+support_b:
        t=perf_counter();r=bot.respond(text);train_times.append((perf_counter()-t)*1000);reports.append(r)
    learned=[r for r in reports if r.get('status')=='raw_relation_learned']
    assert len(learned)==2, reports
    by_surface={r['surface']:r for r in learned}
    pa=by_surface['{s0} enlaza {s1}']['predicate']
    pb=by_surface['{s0} reposa {s1}']['predicate']

    # Freeze implementation for the evaluation phase.
    before=code_hash()
    exact_memory_hits=sum(t in episodic for t in held)
    parsed=stored=entailed=0; eval_times=[]
    for i,text in enumerate(held):
        p=bot.language.parse(text)
        parsed += p.get('status')=='parsed' and p.get('frame',{}).get('pred')==pa
        t=perf_counter();r=bot.respond(text);eval_times.append((perf_counter()-t)*1000)
        stored += r.get('status')=='stored'
        entailed += bot.answer_atom(Atom(pa,(f'sujeto inedito {i}',f'objeto inedito {i}')))['status']=='supported'

    changed_anchor=sum(
        bot.language.parse(f'sujeto alterno {i} separa objeto alterno {i}')['status']=='unrecognized'
        for i in range(100)
    )

    function_control=Bot(KnowledgeBase())
    for text in ['alfa con beta','gamma con delta','epsilon con zeta']:
        function_report=function_control.observe_raw_relation(text,source='v45_control')
    function_promotions=len(function_control.raw_relation_promotions)

    ambiguous_control=Bot(KnowledgeBase())
    for text in ['alfa enlaza beta','gamma enlaza delta','epsilon enlaza zeta enlaza eta']:
        ambiguous_report=ambiguous_control.observe_raw_relation(text,source='v45_control')
    ambiguous_promotions=len(ambiguous_control.raw_relation_promotions)

    # Populate entirely new structured experience through the learned raw surfaces.
    for i in range(120):
        assert bot.respond(f'agente nuevo {i} enlaza modulo nuevo {i}')['status']=='stored'
        assert bot.respond(f'modulo nuevo {i} reposa zona nueva {i}')['status']=='stored'

    schema_examples=[
        'agente nuevo 0 coordina modulo nuevo 0 en zona nueva 0',
        'agente nuevo 1 coordina modulo nuevo 1 en zona nueva 1',
        'agente nuevo 0 no coordina modulo nuevo 0 en zona nueva 1',
        'agente nuevo 0 no coordina modulo nuevo 1 en zona nueva 0',
        'agente nuevo 1 no coordina modulo nuevo 0 en zona nueva 0',
    ]
    schema_report=None
    for text in schema_examples:
        schema_report=bot.observe_schema_statement(text)
    assert schema_report and schema_report['status']=='schema_learned', schema_report
    selected=schema_report['learning']['selected']
    downstream_pos=downstream_neg=0; query_times=[]
    for i in range(20,120):
        t=perf_counter();pos=bot.query_schema(f'agente nuevo {i} coordina modulo nuevo {i} en zona nueva {i}');query_times.append((perf_counter()-t)*1000)
        neg=bot.query_schema(f'agente nuevo {i} coordina modulo nuevo {i} en zona nueva {(i+1)%120}')
        downstream_pos += pos.get('status')=='entailed'
        downstream_neg += neg.get('status')=='unknown'

    # A same-information episodic control has only literal strings, no executable
    # primitive, so none of the new transfer assertions are exact memories.
    downstream_memory_hits=sum(
        f'agente nuevo {i} enlaza modulo nuevo {i}' in episodic for i in range(20,120)
    )
    after=code_hash()
    report={
        'version':'0.4.5',
        'experiment':'raw_opaque_primitive_induction',
        'code_hash_before_frozen_eval':before,
        'code_hash_after_frozen_eval':after,
        'code_unchanged_during_frozen_phase':before==after,
        'initial_conditions':{
            'known_entities':0,
            'pretraining_heldout_parsed':pre_parsed,
            'heldout_cases':len(held),
            'noise_observations':60,
            'promotions_after_noise':promotions_after_noise,
        },
        'acquisition':{
            'raw_support_sentences':len(support_a)+len(support_b),
            'learned_relations':len(learned),
            'surfaces':{r['surface']:r['predicate'] for r in learned},
            'median_support_response_ms':median(train_times),
        },
        'heldout_transfer':{
            'parsed':parsed,'stored':stored,'entailed':entailed,'cases':len(held),
            'exact_text_memory_hits':exact_memory_hits,
            'changed_anchor_unrecognized':changed_anchor,'changed_anchor_cases':100,
            'median_response_ms':median(eval_times),
        },
        'safety_controls':{
            'function_word_only_promotions':function_promotions,
            'function_word_last_status':function_report.get('status'),
            'repeated_anchor_promotions':ambiguous_promotions,
            'repeated_anchor_last_status':ambiguous_report.get('status'),
        },
        'downstream_composition':{
            'primitive_a':pa,'primitive_b':pb,
            'selected_schema':selected,
            'uses_both_invented_primitives':pa in selected and pb in selected,
            'positive_entailed':downstream_pos,'positive_cases':100,
            'mismatched_unknown':downstream_neg,'negative_cases':100,
            'episodic_control_hits':downstream_memory_hits,
            'median_query_ms':median(query_times),
        },
        'limits':[
            'Induce solo relaciones primitivas binarias opacas con dos spans separados por anclas compartidas.',
            'La repeticion de una superficie no demuestra que Leobot conozca una definicion intensional del predicado.',
            'No interpreta aun polaridad cruda, preguntas nuevas ni roles adyacentes sin delimitadores.',
            'Evaluacion interna y sintetica; no demuestra AGI ni ASI.',
        ],
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

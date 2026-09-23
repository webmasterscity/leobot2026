"""V4.2: acquire unseen entity spans/facts through already learned surfaces.

The learner first grounds two binary surfaces using only known entities.  Code is
then frozen.  New multiword referents are introduced only through ordinary text.
Those acquired facts must become indexed primitives that support learning a new
composed ternary concept.  Controls verify that the V4.1 known-entity parser
cannot parse the same novel utterances and that ambiguous span boundaries abstain.
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
RESULT=ROOT/'results_v3'/'v42_open_entity_acquisition.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def seed_bot(junk=5000):
    kb=KnowledgeBase()
    for i in range(8):
        kb.add(Atom('socio',(f'persona{i}',f'objeto{i}')))
        kb.add(Atom('sitio',(f'objeto{i}',f'lugar{i}')))
    for j in range(junk):
        kb.add(Atom(f'junk{j}',(f'jx{j}',f'jy{j}')))
    bot=Bot(kb)
    first=second=None
    for text in [
        'persona0 conecta objeto0','persona1 conecta objeto1',
        'persona0 no conecta objeto1','persona1 no conecta objeto0',
    ]:
        first=bot.observe_schema_statement(text)
    for text in [
        'objeto0 descansa en lugar0','objeto1 descansa en lugar1',
        'objeto0 no descansa en lugar1','objeto1 no descansa en lugar0',
    ]:
        second=bot.observe_schema_statement(text)
    assert first and second and first['status']=='schema_learned' and second['status']=='schema_learned'
    return bot,first,second


def names(i):
    return f'agente externo {i}', f'modulo experimental {i}', f'zona remota {i}'


def main():
    bot,first,second=seed_bot()
    target_left=first['learning']['target']; target_right=second['learning']['target']
    before=code_hash()

    # V4.1 control: exact same novel utterances are not parseable because none of
    # their referents is in the entity index yet.
    baseline_texts=[]
    for i in range(100):
        a,b,c=names(i)
        baseline_texts.extend((f'{a} conecta {b}',f'{b} descansa en {c}'))
    baseline_known=sum(bot.schemas.parse(t) is not None for t in baseline_texts)
    learned_surface_matches=sum(bot.schemas.parse_learned_surface(t).get('status')=='schema_surface_matched'
                                for t in baseline_texts)

    acquisition_times=[]; stored=0; exact_training_texts=set()
    for i in range(120):
        a,b,c=names(i)
        for text in (f'{a} conecta {b}',f'{b} descansa en {c}'):
            started=perf_counter(); report=bot.acquire_schema_assertion(text,source='v42_frozen')
            acquisition_times.append((perf_counter()-started)*1000)
            stored += report.get('status')=='schema_fact_stored'
            exact_training_texts.add(text)

    # The learned construction itself contains a repeated anchor here; there are
    # two legal slot boundaries, so acquisition must abstain and memory must not grow.
    before_ambiguous=bot.kb.stats()['facts']
    ambiguous=bot.acquire_schema_assertion('agente conecta modulo conecta extra',source='v42_frozen')
    after_ambiguous=bot.kb.stats()['facts']

    # New concept: compose *acquired* predicates.  No socio/sitio facts exist for
    # the new referents, so success cannot come from the original seed predicates.
    compose_training=[]
    a0,b0,c0=names(0); a1,b1,c1=names(1)
    compose_training=[
        f'{a0} coordina {b0} en {c0}',
        f'{a1} coordina {b1} en {c1}',
        f'{a0} no coordina {b0} en {c1}',
        f'{a0} no coordina {b1} en {c0}',
        f'{a1} no coordina {b0} en {c0}',
    ]
    composed=None
    for text in compose_training:
        exact_training_texts.add(text)
        composed=bot.observe_schema_statement(text)

    positives=negatives=0; query_times=[]; exact_memory_hits=0
    for i in range(20,120):
        a,b,c=names(i); _,_,wrong=names((i+1)%120)
        pos=f'{a} coordina {b} en {c}'
        neg=f'{a} coordina {b} en {wrong}'
        exact_memory_hits += pos in exact_training_texts
        t=perf_counter(); rp=bot.query_schema(pos); query_times.append((perf_counter()-t)*1000)
        t=perf_counter(); rn=bot.query_schema(neg); query_times.append((perf_counter()-t)*1000)
        positives += rp.get('status')=='entailed'
        negatives += rn.get('status')!='entailed'

    # Ablation: same grounded surfaces but no acquisition.  The later concept
    # examples contain wholly unseen entities, so V4.1 cannot even establish slots.
    control,_,_=seed_bot(junk=0)
    ablation_reports=[control.observe_schema_statement(t).get('status') for t in compose_training]

    new_entities={v for i in range(120) for v in names(i)}
    indexed=len(bot.kb.known_entities(new_entities))
    audit_events=[x for x in bot.kb.audit if x.get('event')=='schema_surface_assertion']
    selected=(composed or {}).get('learning',{}).get('selected')
    selected_preds=(composed or {}).get('learning',{}).get('predicates',[])
    after=code_hash()

    report={
        'version':'0.4.2',
        'experiment':'open_entity_surface_acquisition_and_transfer',
        'code_hash_before':before,
        'seed_surfaces':{
            'left_target':target_left,'right_target':target_right,
            'left_selected':first['learning']['selected'],
            'right_selected':second['learning']['selected'],
            'unrelated_predicates_in_world':5000,
        },
        'controls':{
            'v41_known_entity_parser_novel_matches':baseline_known,
            'v41_known_entity_parser_cases':len(baseline_texts),
            'learned_surface_matcher_novel_matches':learned_surface_matches,
            'learned_surface_matcher_cases':len(baseline_texts),
            'ambiguous_boundary_status':ambiguous.get('status'),
            'ambiguous_boundary_fact_delta':after_ambiguous-before_ambiguous,
            'without_acquisition_composed_training_statuses':ablation_reports,
            'exact_text_memory_positive_heldout_hits':exact_memory_hits,
            'exact_text_memory_positive_heldout_cases':100,
        },
        'acquisition':{
            'assertions_stored':stored,'assertion_cases':240,
            'novel_entities_indexed':indexed,'novel_entities_expected':360,
            'audit_events':len(audit_events),
            'median_assertion_ms':median(acquisition_times),
            'max_assertion_ms':max(acquisition_times),
        },
        'transfer':{
            'status':(composed or {}).get('status'),
            'arity':(composed or {}).get('learning',{}).get('arity'),
            'projection':(composed or {}).get('learning',{}).get('projection'),
            'selected':selected,'predicates_considered':selected_preds,
            'expected_acquired_primitives':sorted((target_left,target_right)),
            'heldout_positive':positives,'heldout_positive_cases':100,
            'heldout_negative_rejected':negatives,'heldout_negative_cases':100,
            'median_query_ms':median(query_times),
        },
        'code_hash_after':after,
        'code_unchanged_during_frozen_phase':before==after,
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

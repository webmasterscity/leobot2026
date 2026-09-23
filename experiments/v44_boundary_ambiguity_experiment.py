"""V4.4: ambiguity-aware boundaries for learned generic language constructions.

V4.3 exposed that the legacy non-greedy regex selected one slot boundary when a
fixed anchor repeated inside a possible slot.  This experiment compares that
legacy acceptance signal with the new bounded segmentation enumerator, then checks
that unique unseen multiword referents still transfer through the paraphrase.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase
from leobot.language import normalize

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v44_boundary_ambiguity.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def bootstrap():
    bot=Bot(KnowledgeBase(),allow_extensional_grounding=True)
    for i in range(6):
        bot.kb.add(Atom('socio',(f'persona{i}',f'objeto{i}')))
    for text in [
        'persona0 conecta objeto0','persona1 conecta objeto1',
        'persona0 no conecta objeto1','persona1 no conecta objeto0',
    ]:
        root=bot.observe_schema_statement(text)
    for i in range(2):
        bot.acquire_schema_assertion(f'agente externo {i} conecta modulo experimental {i}',source='v44_seed')
        bot.respond(f'agente externo {i} se asocia con modulo experimental {i}')
    grounded=[c for c,e in zip(bot.language.constructions,bot.language.examples)
              if e.get('source')=='grounded_induction']
    assert len(grounded)==1
    return bot,root['learning']['target'],grounded[0]


def main():
    bot,target,construction=bootstrap();before=code_hash()
    legacy_accept=detected=respond_ambiguous=0;parse_times=[]
    before_facts=bot.kb.stats()['facts']
    for i in range(100):
        text=f'persona alfa {i} se asocia con modulo se asocia con extra {i}'
        legacy_accept += re.fullmatch(construction.pattern,normalize(text)) is not None
        t=perf_counter(); parsed=bot.language.parse(text);parse_times.append((perf_counter()-t)*1000)
        detected += parsed.get('status')=='ambiguous'
        response=bot.respond(text)
        respond_ambiguous += response.get('status')=='ambiguous'
    ambiguous_fact_delta=bot.kb.stats()['facts']-before_facts

    unique_stored=unique_entailed=0;unique_times=[]
    for i in range(100,200):
        person=f'persona unica extendida {i}';module=f'modulo azul profundo {i}'
        text=f'{person} se asocia con {module}'
        t=perf_counter(); response=bot.respond(text);unique_times.append((perf_counter()-t)*1000)
        unique_stored += response.get('status')=='stored'
        unique_entailed += bot.query_schema(f'{person} conecta {module}').get('status')=='entailed'

    after=code_hash()
    report={
        'version':'0.4.4',
        'experiment':'ambiguity_aware_learned_slot_boundaries',
        'code_hash_before':before,
        'target':target,
        'construction_surface':construction.surface,
        'controls':{
            'legacy_regex_would_accept':legacy_accept,'ambiguous_cases':100,
        },
        'ambiguity_detection':{
            'reported_ambiguous':detected,'cases':100,
            'conversation_abstained':respond_ambiguous,'conversation_cases':100,
            'fact_delta_from_ambiguous_inputs':ambiguous_fact_delta,
            'median_parse_ms':median(parse_times),
        },
        'unique_boundary_transfer':{
            'stored':unique_stored,'cases':100,
            'entailed_via_original_schema':unique_entailed,'query_cases':100,
            'median_response_ms':median(unique_times),
        },
        'code_hash_after':after,
        'code_unchanged_during_frozen_phase':before==after,
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

"""V4.3: bootstrapped language growth from V4.2-acquired facts.

No new semantic frame is annotated.  Two independent acquired facts ground a new
paraphrase through the existing version-space language learner.  Once promoted,
that paraphrase must accept wholly unseen referents and store the same predicate,
showing a chain: learned relation -> open entities -> grounded paraphrase -> more
open entities.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v43_bootstrapped_paraphrase.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def seed(junk=5000):
    kb=KnowledgeBase()
    for i in range(8):
        kb.add(Atom('socio',(f'persona{i}',f'objeto{i}')))
    for j in range(junk):
        kb.add(Atom(f'junk{j}',(f'jx{j}',f'jy{j}')))
    bot=Bot(kb,allow_extensional_grounding=True); report=None
    for text in [
        'persona0 conecta objeto0','persona1 conecta objeto1',
        'persona0 no conecta objeto1','persona1 no conecta objeto0',
    ]:
        report=bot.observe_schema_statement(text)
    assert report and report['status']=='schema_learned'
    return bot,report['learning']['target']


def main():
    bot,target=seed()
    before=code_hash()

    # Control: the new paraphrase has neither known entities nor factual grounding.
    control,_=seed(junk=0)
    control_response=control.respond('agente externo cero se asocia con modulo experimental cero')
    control_language=control.language.parse('agente externo uno se asocia con modulo experimental uno')

    acquired_ids=[]
    for i in range(6):
        report=bot.acquire_schema_assertion(f'agente externo {i} conecta modulo experimental {i}',source='v43_seed')
        acquired_ids.append(report['id'])

    first=bot.respond('agente externo 0 se asocia con modulo experimental 0')
    second=bot.respond('agente externo 1 se asocia con modulo experimental 1')
    promoted_states=[s for s in bot.grounding_hypotheses.values() if s.get('promoted')]
    support_evidence=sorted({fid for s in promoted_states for obs in s.get('observations',[])
                             for detail in obs.get('candidates',{}).values()
                             for fid in detail.get('evidence',[])})
    grounded_examples=[e for e in bot.language.examples if e.get('source')=='grounded_induction']

    times=[];stored=0;new_entities=set();query_ok=0
    paraphrase_texts=set()
    for i in range(100,200):
        person=f'persona emergente {i}'; module=f'modulo emergente {i}'
        text=f'{person} se asocia con {module}'
        paraphrase_texts.add(text)
        t=perf_counter(); result=bot.respond(text); times.append((perf_counter()-t)*1000)
        stored += result.get('status')=='stored'
        new_entities.update((person,module))
        query_ok += bot.query_schema(f'{person} conecta {module}').get('status')=='entailed'

    indexed=len(bot.kb.known_entities(new_entities))
    # Root-surface queries were never literal paraphrase training strings.
    exact_memory_hits=sum(f'persona emergente {i} conecta modulo emergente {i}' in paraphrase_texts
                          for i in range(100,200))

    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'bot.json';bot.save(path);loaded=Bot.load(path)
        persisted=loaded.respond('persona posterior se asocia con modulo posterior')
        persisted_query=loaded.query_schema('persona posterior conecta modulo posterior')

    # Expose the next concrete failure: generic Language constructions currently
    # use a non-greedy regex and do not enumerate alternative slot boundaries.
    ambiguous_probe='persona alfa se asocia con modulo se asocia con extra'
    ambiguous_parse=bot.language.parse(ambiguous_probe)

    after=code_hash()
    report={
        'version':'0.4.3',
        'experiment':'bootstrapped_paraphrase_from_acquired_facts',
        'code_hash_before':before,
        'target':target,
        'controls':{
            'without_acquired_facts_response_status':control_response.get('status'),
            'without_acquired_facts_language_status':control_language.get('status'),
            'exact_text_memory_root_query_hits':exact_memory_hits,
            'exact_text_memory_root_query_cases':100,
        },
        'grounding':{
            'first_support_status':first.get('status'),
            'second_support_status':second.get('status'),
            'promoted_version_spaces':len(promoted_states),
            'independent_supports':len(promoted_states[0].get('observations',[])) if promoted_states else 0,
            'support_fact_ids':support_evidence,
            'support_fact_ids_from_v42_acquisition':all(x in acquired_ids for x in support_evidence),
            'grounded_language_constructions':len(grounded_examples),
            'grounded_language_evidence':grounded_examples[0].get('evidence',[]) if grounded_examples else [],
        },
        'open_entity_transfer':{
            'new_paraphrase_assertions_stored':stored,'cases':100,
            'new_entities_indexed':indexed,'new_entities_expected':200,
            'root_schema_queries_entailed':query_ok,'root_schema_query_cases':100,
            'median_response_ms':median(times),
            'persisted_new_assertion_status':persisted.get('status'),
            'persisted_root_query_status':persisted_query.get('status'),
        },
        'next_failure_probe':{
            'text':ambiguous_probe,
            'language_parse_status':ambiguous_parse.get('status'),
            'parsed_frame':ambiguous_parse.get('frame'),
            'risk':'slot_boundary_ambiguity_not_explicitly_detected' if ambiguous_parse.get('status')=='parsed' else None,
        },
        'unrelated_predicates_in_seed_world':5000,
        'code_hash_after':after,
        'code_unchanged_during_frozen_phase':before==after,
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

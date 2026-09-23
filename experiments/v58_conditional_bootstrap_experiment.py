"""V5.8 internal experiment: bootstrap opaque clause meanings inside hypotheticals.

Three repeated single-antecedent conditionals are presented from an empty ontology.
The clauses may teach language constructions, but the hypothetical examples must
never become facts.  Only after those constructions are grounded by repetition may
the ordinary conditional learner induce a Horn rule.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from time import perf_counter

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]


def code_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


CONDITIONALS=[
    'si ana frobla caja a luis entonces caja zenda luis',
    'si bea frobla libro a mario entonces libro zenda mario',
    'si cora frobla mapa a nora entonces mapa zenda nora',
]


def evaluate(bot,n=100):
    correct=0; wrong=0; lat=[]
    start_facts=bot.kb.stats()['facts']
    for i in range(n):
        actor=f'actor{i:03d}'; obj=f'objeto{i:03d}'; dst=f'destino{i:03d}'
        stored=bot.respond(f'{actor} frobla {obj} a {dst}')
        t0=perf_counter(); ans=bot.respond(f'¿{obj} zenda {dst}?'); lat.append((perf_counter()-t0)*1000)
        if stored.get('status') in ('stored','schema_fact_stored') and ans.get('status') in ('hypothesis','supported'):
            correct+=1
        else:
            wrong+=1
    return {'correct':correct,'wrong':wrong,'facts_added':bot.kb.stats()['facts']-start_facts,
            'p50_ms':statistics.median(lat),'p95_ms':sorted(lat)[int(.95*(len(lat)-1))]}


def run():
    before=code_hash()
    educated=Bot(allow_extensional_grounding=False)
    reports=[educated.respond(x) for x in CONDITIONALS]
    assert [r['status'] for r in reports]==['conditional_unresolved','conditional_unresolved','conditional_bootstrap_learned']
    assert educated.kb.stats()['facts']==0
    assert len(educated.kb.rules)==1
    assert len(educated.raw_relation_observations)==0
    educated_eval=evaluate(educated,100)

    control=Bot(allow_extensional_grounding=False)
    control_reports=[control.respond(x) for x in CONDITIONALS[:2]]
    assert all(r['status']=='conditional_unresolved' for r in control_reports)
    assert len(control.kb.rules)==0 and control.kb.stats()['facts']==0
    control_eval=evaluate(control,100)

    noise=Bot(allow_extensional_grounding=False)
    for i in range(60):
        r=noise.respond(f'si sujeto{i} verbo{i} objeto{i} entonces salida{i} cambia valor{i}')
        assert r['status']=='conditional_unresolved', r
    assert noise.kb.stats()['facts']==0 and len(noise.kb.rules)==0
    assert not noise.raw_relation_promotions

    after=code_hash()
    result={
        'version':'0.5.8',
        'mechanism':'hypothetical clause anti-unification -> constructions -> ordinary grounded Horn induction',
        'bootstrap_statuses':[r['status'] for r in reports],
        'hypothetical_facts_after_training':0,
        'learned_rule':reports[-1]['rule']['rule'],
        'educated_heldout':educated_eval,
        'two_support_control':control_eval,
        'noise_control':{'conditionals':60,'facts':noise.kb.stats()['facts'],'rules':len(noise.kb.rules),
                         'promotions':len(noise.raw_relation_promotions)},
        'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
        'claim_boundary':'Internal acquisition/transfer evidence; not open-domain comprehension or AGI.'
    }
    assert educated_eval['correct']==100 and educated_eval['wrong']==0, result
    assert educated_eval['facts_added']==100, result
    assert control_eval['correct']==0, result
    assert result['noise_control']=={'conditionals':60,'facts':0,'rules':0,'promotions':0}, result
    assert before==after, result
    return result


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))

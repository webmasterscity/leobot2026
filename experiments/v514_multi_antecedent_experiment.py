#!/usr/bin/env python3
"""Frozen V5.14 experiment: evidence-selected 4-antecedent raw rules.

No neural model or external semantic parser is used.  The control receives only
three hypothetical episodes, which is intentionally below the four-antecedent
complexity threshold.  The treatment receives the fourth independent episode,
then both are evaluated on structurally new facts.
"""
from __future__ import annotations
from time import perf_counter
import json
from leobot import Bot


def condition(i: int) -> str:
    return (f'si a{i} alfa b{i} y b{i} bravo c{i} y c{i} charlie d{i} '
            f'y d{i} delta e{i} entonces a{i} omega e{i}')


def main() -> None:
    control=Bot(allow_extensional_grounding=False)
    treatment=Bot(allow_extensional_grounding=False)
    for i in range(3):
        control.respond(condition(i))
        treatment.respond(condition(i))
    before_promotions=len(treatment.raw_relation_promotions)
    started=perf_counter()
    learned=treatment.respond(condition(3))
    learn_ms=(perf_counter()-started)*1000

    control_hits=treatment_hits=0
    latencies=[]
    for i in range(100,200):
        facts=[f'x{i} alfa y{i}',f'y{i} bravo z{i}',f'z{i} charlie q{i}',f'q{i} delta w{i}']
        for fact in facts:
            control.respond(fact)
            t0=perf_counter(); treatment.respond(fact); latencies.append((perf_counter()-t0)*1000)
        control_hits += control.respond(f'¿x{i} omega w{i}?')['status']=='hypothesis'
        treatment_hits += treatment.respond(f'¿x{i} omega w{i}?')['status']=='hypothesis'

    # Wrong joins must stay rejected.
    wrong=0
    for i in range(100,200):
        wrong += treatment.respond(f'¿x{i} omega w{100 + ((i-99) % 100)}?')['status']=='unknown'

    report={
        'version':'5.14',
        'learned_status':learned.get('status'),
        'antecedents':learned.get('antecedents'),
        'required':learned.get('required'),
        'facts_added_by_hypothetical_learning':treatment.kb.stats()['facts']-400,
        'promotions_before_fourth_support':before_promotions,
        'treatment_transfer':f'{treatment_hits}/100',
        'control_transfer':f'{control_hits}/100',
        'wrong_join_rejected':f'{wrong}/100',
        'learn_ms':round(learn_ms,3),
        'median_store_ms':round(sorted(latencies)[len(latencies)//2],3),
        'rules':len(treatment.kb.rules),
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert learned.get('status')=='conditional_bootstrap_learned'
    assert learned.get('antecedents')==4 and learned.get('required')==4
    assert before_promotions==0
    assert treatment_hits==100 and control_hits==0 and wrong==100
    assert report['facts_added_by_hypothetical_learning']==0


if __name__=='__main__':
    main()

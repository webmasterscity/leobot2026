"""V5.10 internal experiment: compositional explicit Spanish negation.

The experiment first acquires one opaque positive relation.  The learner is then
frozen and receives unseen negative assertions using the same surface.  It must
store explicit !predicate facts, refute the corresponding positive queries, keep
contradictions four-valued, and use the negative relation in a learned rule.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from time import perf_counter

from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]


def code_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


def ground(bot,prefix='frobla'):
    last=None
    for text in [
        f'ana {prefix} caja a luis',
        f'bea {prefix} libro a mario',
        f'cora {prefix} mapa a nora',
    ]:
        last=bot.respond(text)
    assert last['status']=='raw_relation_learned', last
    return last['predicate']


def run():
    before=code_hash()
    bot=Bot(allow_extensional_grounding=False)
    pred=ground(bot)
    start=bot.kb.stats()['facts']
    correct=0; lat=[]
    for i in range(100):
        actor=f'actor{i:03d}'; obj=f'obj{i:03d}'; dst=f'dst{i:03d}'
        stored=bot.respond(f'{actor} no frobla {obj} a {dst}')
        t0=perf_counter(); ans=bot.respond(f'¿{actor} frobla {obj} a {dst}?'); lat.append((perf_counter()-t0)*1000)
        if stored.get('status')=='stored' and ans.get('status')=='refuted' and bot.kb.contains(Atom('!'+pred,(actor,obj,dst))):
            correct+=1
    negative_phase_facts=bot.kb.stats()['facts']-start
    # Contradiction is preserved, not overwritten.
    bot.respond('actor000 frobla obj000 a dst000')
    conflict=bot.respond('¿actor000 frobla obj000 a dst000?')

    # Negative predicates can participate in induced rules.
    head=ground(bot,'zenda')
    conds=[
        'si dora no frobla carta a raul entonces dora zenda carta a raul',
        'si eva no frobla paquete a sara entonces eva zenda paquete a sara',
        'si fede no frobla llave a tomas entonces fede zenda llave a tomas',
    ]
    rule_reports=[bot.respond(x) for x in conds]
    bot.respond('gina no frobla cuaderno a hugo')
    derived=bot.respond('¿gina zenda cuaderno a hugo?')

    double_before=bot.kb.stats()['facts']
    double=bot.respond('hugo no no frobla papel a iris')
    after=code_hash()
    result={
        'version':'0.5.10',
        'negative_heldout':{'correct':correct,'total':100,'facts_added':negative_phase_facts,
                            'p50_ms':statistics.median(lat),'p95_ms':sorted(lat)[int(.95*(len(lat)-1))]},
        'conflict_status':conflict['status'],
        'conditional_statuses':[r['status'] for r in rule_reports],
        'derived_from_negative_antecedent':derived['status'],
        'double_negation':{'status':double['status'],'reason':double.get('reason'),
                           'fact_delta':bot.kb.stats()['facts']-double_before},
        'allow_extensional_grounding':bot.allow_extensional_grounding,
        'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
        'claim_boundary':'Explicit polarity composition and rule use only; not general natural-language negation or AGI.'
    }
    assert correct==100, result
    assert conflict['status']=='conflict', result
    assert rule_reports[-1]['status']=='conditional_rule_learned', result
    assert derived['status']=='hypothesis', result
    assert double['status']=='unrecognized' and bot.kb.stats()['facts']==double_before, result
    assert before==after, result
    return result


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))

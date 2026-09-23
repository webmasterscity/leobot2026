"""V5.6 internal experiment: grounded Spanish conditionals -> executable Horn rule.

Internal development evidence only.  No source code changes occur during the
held-out evaluation.  The control sees the same grounded relation surfaces but
only two independent conditional examples, below the promotion threshold.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from time import perf_counter

from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]


def code_hash() -> str:
    h = hashlib.sha256()
    for path in sorted((ROOT / 'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


def ground_surfaces(bot: Bot) -> tuple[str, str]:
    body = head = None
    for text in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
        body = bot.respond(text)
    for text in ['caja queda con luis','libro queda con mario','mapa queda con nora']:
        head = bot.respond(text)
    assert body and body['status']=='raw_relation_learned', body
    assert head and head['status']=='raw_relation_learned', head
    return body['predicate'], head['predicate']


CONDITIONALS = [
    'si dora entrega carta a raul entonces carta queda con raul',
    'si eva entrega paquete a sara entonces paquete queda con sara',
    'si fede entrega llave a tomas entonces llave queda con tomas',
]


def teach(bot: Bot, count: int) -> list[dict]:
    return [bot.respond(text) for text in CONDITIONALS[:count]]


def heldout(bot: Bot, n: int = 100) -> dict:
    correct = unknown = other = 0
    query_ms=[]
    facts_before_questions=None
    for i in range(n):
        actor=f'actor{i:03d}'; obj=f'item{i:03d}'; dst=f'zona{i:03d}'
        stored=bot.respond(f'{actor} entrega {obj} a {dst}')
        assert stored['status'] in ('stored','schema_fact_stored'), stored
        if facts_before_questions is None:
            facts_before_questions=bot.kb.stats()['facts']
        t0=perf_counter(); answer=bot.respond(f'¿{obj} queda con {dst}?'); query_ms.append((perf_counter()-t0)*1000)
        if answer.get('status') in ('hypothesis','supported'):
            correct += 1
        elif answer.get('status') == 'unknown':
            unknown += 1
        else:
            other += 1
    # Every iteration adds one antecedent fact before its question, so compare the
    # final fact count against seed facts + n, not the first iteration's count.
    expected_facts = 6 + n
    return {
        'correct':correct,'unknown':unknown,'other':other,
        'facts':bot.kb.stats()['facts'],'expected_facts':expected_facts,
        'question_fact_delta':bot.kb.stats()['facts']-expected_facts,
        'query_ms_p50':statistics.median(query_ms),
        'query_ms_p95':sorted(query_ms)[int(0.95*(len(query_ms)-1))],
    }


def run() -> dict:
    before=code_hash()

    educated=Bot(allow_extensional_grounding=False)
    body_pred,head_pred=ground_surfaces(educated)
    seed_facts=educated.kb.stats()['facts']
    reports=teach(educated,3)
    assert [r['status'] for r in reports]==['conditional_rule_pending','conditional_rule_pending','conditional_rule_learned']
    assert educated.kb.stats()['facts']==seed_facts
    learned=reports[-1]
    eval_educated=heldout(educated,100)

    control=Bot(allow_extensional_grounding=False)
    ground_surfaces(control)
    control_reports=teach(control,2)
    assert all(r['status']=='conditional_rule_pending' for r in control_reports)
    eval_control=heldout(control,100)

    noise=Bot(allow_extensional_grounding=False)
    for i in range(60):
        r=noise.respond(f'si ruido{i} cambia cosa{i} entonces salida{i} varia valor{i}')
        assert r['status']=='conditional_unresolved', r

    # A contradictory role mapping after promotion must withdraw the learned rule.
    conflict=educated.respond('si iris entrega sobre a julio entonces iris queda con julio')
    post_conflict=educated.respond('actorx entrega itemx a zonax')
    assert post_conflict['status'] in ('stored','schema_fact_stored')
    post_conflict_answer=educated.respond('¿itemx queda con zonax?')

    after=code_hash()
    result={
        'version':'0.5.6',
        'mechanism':'repeated grounded natural-language conditional -> Horn rule',
        'learned_rule':{
            'body_pred':body_pred,'head_pred':head_pred,
            'support':learned['support'],'mapping':learned['mapping'],
            'rule_id':learned['rule_id'],'rule':learned['rule'],
        },
        'educated_heldout':eval_educated,
        'two_support_control':eval_control,
        'noise_control':{
            'unresolved_conditionals':60,
            'rules':len(noise.kb.rules),'facts':noise.kb.stats()['facts'],
            'raw_observations':len(noise.raw_relation_observations),
        },
        'late_conflict':{
            'status':conflict['status'],'withdrawn':conflict.get('withdrawn',False),
            'post_conflict_answer':post_conflict_answer.get('status'),
        },
        'safety':{
            'allow_extensional_grounding':educated.allow_extensional_grounding,
            'conditional_examples_added_facts':seed_facts != 6,
        },
        'code_hash_before':before,'code_hash_after':after,
        'code_unchanged_during_experiment':before==after,
        'claim_boundary':'Internal rule-learning/transfer evidence; not open-domain understanding or AGI.',
    }
    assert eval_educated['correct']==100 and eval_educated['unknown']==0 and eval_educated['other']==0, result
    assert eval_educated['question_fact_delta']==0, result
    assert eval_control['correct']==0 and eval_control['unknown']==100 and eval_control['other']==0, result
    assert eval_control['question_fact_delta']==0, result
    assert result['noise_control']=={'unresolved_conditionals':60,'rules':0,'facts':0,'raw_observations':0}, result
    assert conflict['status']=='conditional_rule_ambiguous' and conflict.get('withdrawn') is True, result
    assert post_conflict_answer.get('status')=='unknown', result
    assert before==after, result
    return result


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))

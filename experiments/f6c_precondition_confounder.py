"""Frozen F-6c intervention: an unchanged object may be a necessary precondition."""
from __future__ import annotations

import json
import random
import resource
import statistics
import time
from hashlib import sha256

from leobot import Bot
from experiments.b1_aggregate_operator import ROOT
from experiments.f6b_role_geometry_freeze import (
    FAMILIES, ORDERS, action_episode, frozen, remove_transfer,
    restart, source_experience, train_action,
)


def clock(fn):
    start=time.process_time(); wall=time.monotonic(); result=fn()
    return result,{'cpu_s':round(time.process_time()-start,6),
                   'wall_s':round(time.monotonic()-wall,6)}


def taught(spec,prefix,seed,mode):
    bot=Bot(); costs={}; source=None; size=None
    if mode!='fresh':
        source,costs['source']=clock(lambda:source_experience(bot,spec,prefix,seed))
    if mode=='same_information_no_meta':
        remove_transfer(bot)
    if mode=='treatment':
        (bot,size),costs['restart']=clock(lambda:restart(bot))
    reports,costs['action_learning']=clock(lambda:train_action(bot,spec,prefix,seed))
    return bot,{'source_statuses':source['world_statuses'] if source else [],
                'meta_source':source['meta'] if source else [],
                'action_statuses':[report['status'] for report in reports],
                'representation_attempts':sum(len(row.get('meta_controller_representation_attempts',()))
                                               for row in reports),
                'persisted_bytes':size,'costs':costs}


def evaluate(bot,spec,prefix,seed,indices):
    full=missing=unsafe=correct_full=0; latency=[]; statuses={}
    start=time.process_time()
    for index,with_item in indices:
        cue,before,_,destination=action_episode(spec,prefix,seed,index)
        if not with_item:
            before={fact for fact in before if fact[0]!=prefix+'inventory'}
        tick=time.perf_counter()
        report=bot.execute_symbolic_transition(cue,before)
        latency.append((time.perf_counter()-tick)*1000)
        status=report.get('status','missing_status')
        statuses[status]=statuses.get(status,0)+1
        executed=status=='executed_symbolic_action'
        if with_item:
            full+=1
            correct_full+=executed and destination in set(report.get('result',()))
        else:
            missing+=1
            unsafe+=executed
    latency.sort()
    return {'full_cases':full,'full_correct':correct_full,
            'missing_item_cases':missing,'unsafe_missing_item':unsafe,
            'statuses':statuses,'cpu_s':round(time.process_time()-start,6),
            'p50_ms':round(statistics.median(latency),5),
            'p95_ms':round(latency[(95*len(latency)+99)//100-1],5)}


def one_order(order,tree):
    spec=FAMILIES[2]
    seed=int(sha256((tree+':F-6c:'+str(order)).encode()).hexdigest()[:8],16)
    prefix=f'c{seed:08x}'
    indices=random.Random(seed+59).sample(range(1000,100_000),64)
    cases=[(index,position%2==0) for position,index in enumerate(indices)]
    variants={}; bots={}
    for mode in ('treatment','fresh','same_information_no_meta'):
        bot,training=taught(spec,prefix,seed,mode)
        results=evaluate(bot,spec,prefix,seed,cases)
        variants[mode]={'training':training,'before_feedback':results}
        bots[mode]=bot
    bot=bots['treatment']
    unseen=next(index for index in range(100_000,101_000) if index not in indices)
    cue,before,_,_=action_episode(spec,prefix,seed,unseen)
    no_item={fact for fact in before if fact[0]!=prefix+'inventory'}
    feedback,cost=clock(lambda:bot.observe_symbolic_transition(cue,no_item,no_item))
    after=evaluate(bot,spec,prefix,seed,cases)
    no_link_cue,no_link_before,_,_=action_episode(spec,prefix,seed,100_100)
    no_link={fact for fact in no_link_before if fact[0]!=prefix+'link'}
    no_link_result=bot.execute_symbolic_transition(no_link_cue,no_link)
    treatment=variants['treatment']['before_feedback']
    safe=(treatment['unsafe_missing_item']==0 and treatment['full_correct']>=29
          and treatment['p95_ms']<=10 and after['unsafe_missing_item']==0
          and no_link_result.get('status')!='executed_symbolic_action')
    return {'order':order,'seed':seed,'passed':bool(safe),
            'variants':variants,'feedback_status':feedback.get('status'),
            'feedback_cost':cost,'after_feedback':after,
            'no_link_status':no_link_result.get('status')}


def main():
    start=time.monotonic();tree=frozen()
    orders=[one_order(order,tree) for order in ORDERS]
    unchanged=frozen()==tree
    output={'preregistration':'prereg/F-6c-confusor-de-precondicion.md',
            'engine_tree':tree,'engine_unchanged':unchanged,
            'orders':orders,'gate_passed':unchanged and all(row['passed'] for row in orders),
            'wall_s':round(time.monotonic()-start,6),
            'cpu_s':round(sum(
                sum(x['cpu_s'] for x in variant['training']['costs'].values())+
                variant['before_feedback']['cpu_s']
                for row in orders for variant in row['variants'].values())+
                sum(row['feedback_cost']['cpu_s']+row['after_feedback']['cpu_s']
                    for row in orders),6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6c_precondition_confounder.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'gate_passed':output['gate_passed'],'engine_tree':tree,
                      'orders':[{'order':row['order'],'passed':row['passed'],
                                 'treatment':row['variants']['treatment']['before_feedback'],
                                 'fresh':row['variants']['fresh']['before_feedback'],
                                 'no_meta':row['variants']['same_information_no_meta']['before_feedback'],
                                 'feedback_status':row['feedback_status'],
                                 'after_feedback':row['after_feedback']}
                                for row in orders],
                      'cpu_s':output['cpu_s'],'wall_s':output['wall_s'],
                      'max_rss_kib':output['max_rss_kib']},ensure_ascii=False))


if __name__=='__main__':
    main()

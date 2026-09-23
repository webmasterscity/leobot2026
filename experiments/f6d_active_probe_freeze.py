"""Frozen F-6d: active one-fact probes across three role orders and two outcomes."""
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
    action_episode, git, names, remove_transfer,
    restart, source_experience, train_action, train_procedure, evaluate_procedure,
)


TAG='freeze-F-6d'
ORDERS=(17,53,97)
FAMILIES=(
    {'name':'ficha_intermedia','arity':4,'roles':(0,3),
     'raw':'La técnica {p} lleva ficha {i} junto a testigo {j} hasta punto {d}.',
     'action':'Transporta a {p} con ficha {i} desde {o} hasta {d}.'},
    {'name':'destino_primero','arity':4,'roles':(0,1),
     'raw':'En depósito {d} la agente {p} registra ficha {i} para testigo {j}.',
     'action':'Mueve hacia {d} a {p} con ficha {i} desde {o}.'},
    {'name':'origen_antes_ficha','arity':4,'roles':(0,3),
     'raw':'Operador {p} lleva testigo {j} y ficha {i} hacia estación {d}.',
     'action':'Entrega a {p} desde {o} con ficha {i} hasta {d}.'},
)


def frozen():
    tree=git('rev-parse',f'{TAG}:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor F-6d modificado durante el ensayo')
    return tree


def clock(fn):
    start=time.process_time();wall=time.monotonic();value=fn()
    return value,{'cpu_s':round(time.process_time()-start,6),
                  'wall_s':round(time.monotonic()-wall,6)}


def world_response(request,prefix,branch):
    before={tuple(row) for row in request['before']}
    if branch=='necessary':
        return before
    old=next(row for row in before if row[0]==prefix+'loc')
    link=next(row for row in before if row[0]==prefix+'link')
    return (before-{old})|{(old[0],old[1],link[2])}


def cases(seed):
    indices=random.Random(seed+59).sample(range(1000,100_000),64)
    return [(index,position%2==0) for position,index in enumerate(indices)]


def score(bot,spec,prefix,seed,items,branch):
    full=full_correct=missing=missing_correct=unsafe=no_link=no_loc=0;times=[]
    start=time.process_time()
    for index,with_item in items:
        cue,before,_,destination=action_episode(spec,prefix,seed,index)
        if not with_item:
            before={row for row in before if row[0]!=prefix+'inventory'}
        tick=time.perf_counter();report=bot.execute_symbolic_transition(cue,before)
        times.append((time.perf_counter()-tick)*1000)
        executed=report.get('status')=='executed_symbolic_action'
        good=executed and destination in set(report.get('result',()))
        if with_item:
            full+=1;full_correct+=good
        else:
            missing+=1
            missing_correct+=good if branch=='irrelevant' else not executed
            unsafe+=executed and branch=='necessary'
        no_link+=bot.execute_symbolic_transition(
            cue,{f for f in before if f[0]!=prefix+'link'}).get('status')=='executed_symbolic_action'
        no_loc+=bot.execute_symbolic_transition(
            cue,{f for f in before if f[0]!=prefix+'loc'}).get('status')=='executed_symbolic_action'
    times.sort()
    return {'full':full,'full_correct':full_correct,
            'missing':missing,'missing_correct':missing_correct,'unsafe':unsafe,
            'unsafe_no_link':no_link,'unsafe_no_location':no_loc,
            'cpu_s':round(time.process_time()-start,6),
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[60],5)}


def one(spec,order,branch,tree):
    seed=int(sha256((tree+':F-6d:'+spec['name']+':'+str(order)).encode()).hexdigest()[:8],16)
    prefix=f'a{seed:08x}'
    items=cases(seed)
    treatment=Bot();cost={}
    source,cost['source']=clock(lambda:source_experience(treatment,spec,prefix,seed))
    reports,cost['action_learning']=clock(lambda:train_action(treatment,spec,prefix,seed))
    request=reports[-1].get('evidence_request')
    baseline_statuses=[r['status'] for r in reports]
    if request is None:
        return {'family':spec['name'],'order':order,'branch':branch,'seed':seed,
                'passed':False,'failure':'no_active_request',
                'source_meta':source['meta'],'action_statuses':baseline_statuses}
    before=score(treatment,spec,prefix,seed,items,branch)
    (treatment,saved_bytes),cost['restart_before_probe']=clock(lambda:restart(treatment))
    pending_same=(treatment.symbolic.sessions[reports[-1]['pattern']]
                  .get('evidence_request')==request)
    observed=world_response(request,prefix,branch)
    feedback,cost['probe_execution_and_learning']=clock(lambda:treatment.observe_symbolic_transition(
        request['text'],request['before'],observed))
    after=score(treatment,spec,prefix,seed,items,branch)
    (loaded,saved_after),cost['restart_after_probe']=clock(lambda:restart(treatment))
    restarted=score(loaded,spec,prefix,seed,items,branch)
    restart_same=all(after[key]==restarted[key] for key in (
        'full_correct','missing_correct','unsafe','unsafe_no_link','unsafe_no_location'))
    (label,procedure_reports),cost['procedure_learning']=clock(
        lambda:train_procedure(treatment,prefix,seed%3))
    procedure,cost['procedure_response']=clock(lambda:evaluate_procedure(treatment,label,seed+73))
    dependent=bool(treatment.symbolic.operators() and
                   treatment.symbolic.operators()[0].get('cross_modal_sources'))
    extra=names(prefix,3,seed)
    wrong_before={(prefix+'signal',extra['p'],extra['i'],'closed'),
                  (prefix+'destination',extra['d'])}
    wrong_after={(prefix+'signal',extra['p'],extra['i'],'open'),
                 (prefix+'destination',extra['d'])}
    counter,cost['counterevidence']=clock(lambda:treatment.observe_world_transition(
        wrong_before,wrong_after))
    after_counter={'active_actions':len(treatment.symbolic.operators()),
                   'procedure_correct':evaluate_procedure(treatment,label,seed+73)['correct']}
    controls={}
    for name in ('fresh','same_information_no_meta'):
        bot=Bot()
        if name=='same_information_no_meta':
            source_experience(bot,spec,prefix,seed);remove_transfer(bot)
        earlier=train_action(bot,spec,prefix,seed)
        pre=score(bot,spec,prefix,seed,items,branch)
        later=bot.observe_symbolic_transition(request['text'],request['before'],observed)
        post=score(bot,spec,prefix,seed,items,branch)
        controls[name]={'statuses':[r['status'] for r in earlier],
                        'pre':pre,'feedback_status':later['status'],'post':post}
    source_ok=any(row.get('kind')=='role_set' and row.get('input_arity')==4
                  and row.get('roles')==list(spec['roles']) for row in source['meta'])
    request_ok=(request.get('kind')=='controlled_intervention'
                and len(request.get('removed_fact',()))>=2
                and request['removed_fact'][0]==prefix+'inventory'
                and request.get('alternatives')==['effect','no_effect'])
    passed=(source_ok and request_ok and baseline_statuses[-1]=='pending_discriminating_evidence'
            and pending_same and before['full_correct']==0 and before['unsafe']==0
            and feedback['status']=='operator_learned'
            and feedback.get('pattern')==reports[-1].get('pattern')
            and after['full_correct']>=30 and after['missing_correct']>=30
            and after['unsafe']==0 and after['unsafe_no_link']==0
            and after['unsafe_no_location']==0 and after['p95_ms']<=10
            and restart_same and procedure['correct']>=116
            and counter['status']=='raw_world_conflict'
            and (after_counter['active_actions']==0 if dependent else
                 after_counter['active_actions']==1)
            and after_counter['procedure_correct']==0
            and controls['fresh']['pre']['full_correct']==0
            and controls['same_information_no_meta']['pre']['full_correct']==0)
    return {'family':spec['name'],'order':order,'branch':branch,'seed':seed,
            'passed':bool(passed),'source_meta':source['meta'],
            'baseline_statuses':baseline_statuses,'request':request,
            'before':before,'feedback_status':feedback['status'],
            'after':after,'procedure_status':procedure_reports[-1]['status'],
            'procedure':procedure,'counter_status':counter['status'],
            'action_depends_on_meta':dependent,'after_counter':after_counter,
            'controls':controls,'restart_same':restart_same,
            'saved_bytes':saved_bytes,'saved_bytes_after':saved_after,
            'cost':cost,'cpu_total_s':round(sum(v['cpu_s'] for v in cost.values()),6)}


def main():
    start=time.monotonic();tree=frozen()
    results=[one(spec,order,branch,tree) for order in ORDERS
             for spec in FAMILIES for branch in ('necessary','irrelevant')]
    unchanged=frozen()==tree
    output={'preregistration':'prereg/F-6d-prueba-activa-de-precondicion.md',
            'tag':TAG,'engine_tree':tree,'engine_unchanged':unchanged,
            'results':results,'gate_passed':unchanged and all(row['passed'] for row in results),
            'cpu_total_s':round(sum(row.get('cpu_total_s',0) for row in results),6),
            'wall_s':round(time.monotonic()-start,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6d_active_probe_freeze.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'gate_passed':output['gate_passed'],'engine_tree':tree,
                      'cases':[{'family':row['family'],'order':row['order'],
                                'branch':row['branch'],'passed':row['passed'],
                                'failure':row.get('failure'),
                                'before_full':row.get('before',{}).get('full_correct'),
                                'after_full':row.get('after',{}).get('full_correct'),
                                'after_missing':row.get('after',{}).get('missing_correct'),
                                'unsafe':row.get('after',{}).get('unsafe'),
                                'procedure':row.get('procedure',{}).get('correct')}
                               for row in results],
                      'cpu_total_s':output['cpu_total_s'],
                      'wall_s':output['wall_s'],
                      'max_rss_kib':output['max_rss_kib']},ensure_ascii=False))


if __name__=='__main__':
    main()

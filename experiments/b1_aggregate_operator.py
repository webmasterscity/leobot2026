"""Frozen-engine B-1 evaluation; generated reserves remain outside the engine."""
from __future__ import annotations

import argparse
import json
import random
import resource
import subprocess
import tempfile
import time
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


ROOT=Path(__file__).resolve().parents[1]
ORDERS=(17,53,97)


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def clock(action):
    wall=time.perf_counter();cpu=time.process_time()
    result=action()
    return result,{'wall_s':round(time.perf_counter()-wall,5),
                   'cpu_s':round(time.process_time()-cpu,5)}


def pair(index, *, rng=None):
    bits=[(index>>k)&1 for k in range(6)]
    values=[]
    for k,bit in enumerate(bits):
        if rng is None:
            center=10**(k%4+2)+37*index+101*k;delta=3
        else:
            center=rng.randint(-100_000_000,100_000_000)
            delta=rng.randint(2,100)
        values.extend((center+delta,center-delta) if bit else
                      (center-delta,center+delta))
    return tuple(values),sum(bits)>=4


def raw(index, *, rng=None, proxy=None):
    bits=[(index>>k)&1 for k in range(8)]
    values=[]
    for k,bit in enumerate(bits):
        magnitude=(3+k+(index*7+k*11)%9 if rng is None else
                   rng.randint(3,50)*rng.randint(2,7))
        if proxy is not None:
            magnitude*=4 if proxy else 1
        values.append(magnitude if bit else -magnitude)
    return tuple(values),sum(bits)>=5


def source_rows(order):
    indices=list(range(64));random.Random(order).shuffle(indices)
    return [pair(i) for i in indices]


def target_rows(order, *, confounded=False):
    indices=random.Random(order).sample(range(256),128)
    rows=[]
    for index in indices:
        truth=sum((index>>k)&1 for k in range(8))>=5
        rows.append(raw(index,proxy=truth if confounded else None))
    return rows,sorted(set(range(256))-set(indices))


def reserves(seed, remaining, *, confounded=False):
    rng=random.Random(seed)
    configs=list(range(64))*2;rng.shuffle(configs)
    source=[pair(index,rng=rng) for index in configs]
    rng.shuffle(remaining)
    target=[]
    for index in remaining:
        truth=sum((index>>k)&1 for k in range(8))>=5
        target.append(raw(index,rng=rng,proxy=not truth if confounded else None))
    return source,target


def teach(controller,family,rows,labels):
    for features,positive in rows:
        winner=labels[0] if positive else labels[1]
        for strategy in labels:
            controller.observe(family,features,strategy,success=strategy==winner,
                               cost=1 if strategy==winner else 9,failure_budget=2)


def evaluate(controller,family,rows,labels):
    started=time.process_time();correct=wrong_confident=0;modes={}
    for features,positive in rows:
        target=labels[0] if positive else labels[1]
        route=controller.rank(family,features,labels)
        prediction=route['order'][0]
        correct+=int(prediction==target)
        wrong_confident+=int(prediction!=target and route['mode']!='default')
        mode=route['mode'];modes[mode]=modes.get(mode,0)+1
    return {'correct':correct,'total':len(rows),
            'wrong_confident':wrong_confident,'modes':modes,
            'cpu_s':round(time.process_time()-started,5)}


def instrument(controller):
    costs={'search_cpu_s':0.0,'aggregate_synthesis_validation_cpu_s':0.0,
           'consolidation_cpu_s':0.0}
    for name,key in (('invent_view','search_cpu_s'),
                     ('_invent_aggregate_view_from_tasks',
                      'aggregate_synthesis_validation_cpu_s'),
                     ('_reconcile_meta_operators','consolidation_cpu_s')):
        original=getattr(controller,name)
        def wrapped(*args,_original=original,_key=key,**kwargs):
            started=time.process_time()
            result=_original(*args,**kwargs)
            costs[_key]+=time.process_time()-started
            return result
        setattr(controller,name,wrapped)
    return costs


def restart(controller):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'state.json'
        bot=Bot();bot.meta_controller=controller;bot.save(path)
        size=path.stat().st_size
        del bot
        loaded=Bot.load(path)
    return loaded.meta_controller,size


def incompatible_rows(order):
    rng=random.Random(order+444)
    rows=[]
    for index in range(64):
        values=list(raw(index)[0]);large=bool(rng.getrandbits(1))
        if large:
            position=rng.randrange(8)
            values[position]*=20
        rows.append((tuple(values),large))
    return rows


def one_order(order,seed):
    source=source_rows(order);target,remaining=target_rows(order)
    source_reserve,target_reserve=reserves(seed,remaining.copy())
    labels_source=('A','B');labels_target=('north','south')
    treatment=MetaController();nested=instrument(treatment)
    _,source_cost=clock(lambda:teach(treatment,'source',source,labels_source))
    source_score=evaluate(treatment,'source',source_reserve,labels_source)
    _,target_cost=clock(lambda:teach(treatment,'new_layout',target,labels_target))
    target_score=evaluate(treatment,'new_layout',target_reserve,labels_target)
    operator_count=len(treatment.meta_operators)
    source_candidates=treatment.aggregate_candidates_evaluated.get('source',0)
    educated_candidates=treatment.aggregate_candidates_evaluated.get('new_layout',0)

    (reloaded,size),restart_cost=clock(lambda:restart(treatment))
    restart_score=evaluate(reloaded,'new_layout',target_reserve,labels_target)

    ablated=MetaController();ablated.enable_meta_operator_invention=False
    _,ablation_cost=clock(lambda:teach(ablated,'source',source,labels_source))
    ablation_score=evaluate(ablated,'source',source_reserve,labels_source)
    fresh=MetaController();_,fresh_cost=clock(
        lambda:teach(fresh,'new_layout',target,labels_target))
    fresh_score=evaluate(fresh,'new_layout',target_reserve,labels_target)
    fresh_candidates=fresh.aggregate_candidates_evaluated.get('new_layout',0)
    uneducated=evaluate(MetaController(),'new_layout',target_reserve,labels_target)
    memory=MetaController.from_dict(treatment.as_dict())
    memory.invented_views.clear();memory.meta_operators.clear();memory.routers.clear()
    memory_score=evaluate(memory,'new_layout',target_reserve,labels_target)

    incompatible=MetaController.from_dict(treatment.as_dict())
    _,incompatible_cost=clock(lambda:teach(
        incompatible,'incompatible',incompatible_rows(order),('high','low')))
    incompatible_view=incompatible.invented_views.get('incompatible',{})

    renamed=MetaController()
    _,rename_cost=clock(lambda:(teach(renamed,'fuente_renombrada',source,('p','q')),
                                teach(renamed,'destino_renombrado',target,('u','v'))))
    rename_score=evaluate(renamed,'destino_renombrado',target_reserve,('u','v'))

    proxy_target,proxy_remaining=target_rows(order,confounded=True)
    _,proxy_reserve=reserves(seed+73,proxy_remaining.copy(),confounded=True)
    confounded=MetaController.from_dict(treatment.as_dict())
    _,confound_cost=clock(lambda:teach(
        confounded,'proxy_layout',proxy_target,labels_target))
    confound_score=evaluate(confounded,'proxy_layout',proxy_reserve,labels_target)

    contradicted=MetaController.from_dict(treatment.as_dict())
    new_evidence=[]
    for index in range(64,96):
        features,_=pair(index)
        new_evidence.append((features,bool(index&1)))
    _,counter_cost=clock(lambda:teach(
        contradicted,'source',new_evidence,labels_source))
    withdrawn_before='new_layout' not in contradicted.invented_views
    (contradicted_restored,_),counter_restart_cost=clock(lambda:restart(contradicted))
    withdrawn_after='new_layout' not in contradicted_restored.invented_views

    variant_cpu={
        'treatment':source_cost['cpu_s']+target_cost['cpu_s']+
            source_score['cpu_s']+target_score['cpu_s'],
        'ablation':ablation_cost['cpu_s']+ablation_score['cpu_s'],
        'fresh':fresh_cost['cpu_s']+fresh_score['cpu_s'],
        'rename':rename_cost['cpu_s']+rename_score['cpu_s'],
        'confounded':confound_cost['cpu_s']+confound_score['cpu_s'],
        'incompatible':incompatible_cost['cpu_s'],
        'counterevidence':counter_cost['cpu_s']+counter_restart_cost['cpu_s'],
    }
    controls={
        'accuracy_f1':source_score['correct']>=116,
        'accuracy_f2':target_score['correct']>=116,
        'ablation':ablation_score['correct']<=96 or
            ablated.aggregate_candidates_evaluated.get('source',0)>=5*max(1,source_candidates),
        'reuse':educated_candidates<fresh_candidates,
        'restart':restart_score['correct']>=116,
        'counterevidence':withdrawn_before and withdrawn_after and
            not contradicted_restored.meta_operators,
        'rename':rename_score['correct']>=116,
        'confound':confound_score['wrong_confident']==0,
        'incompatible':incompatible_view.get('kind')!='aggregate_program',
        'budget_cpu':all(value<=30 for value in variant_cpu.values()),
    }
    return {'order_seed':order,'reserve_seed':seed,'controls':controls,
            'treatment_f1':source_score,'treatment_f2':target_score,
            'ablation_same_information':ablation_score,'fresh_f2':fresh_score,
            'uneducated_f2':uneducated,'memory_only_f2':memory_score,
            'restart_f2':restart_score,'renamed_f2':rename_score,
            'confounded_f2':confound_score,'incompatible_view':incompatible_view.get('kind'),
            'operator_count':operator_count,'source_candidates':source_candidates,
            'educated_f2_candidates':educated_candidates,'fresh_f2_candidates':fresh_candidates,
            'withdrawn_before_restart':withdrawn_before,
            'withdrawn_after_restart':withdrawn_after,
            'acquisition_costs':{'source':source_cost,'target':target_cost,
                                 'ablation':ablation_cost,'fresh':fresh_cost,
                                 'rename':rename_cost,'confound':confound_cost,
                                 'incompatible':incompatible_cost,'counterevidence':counter_cost},
            'nested_cpu_s_nonadditive':{key:round(value,5) for key,value in nested.items()},
            'restart_cost':restart_cost,'counter_restart_cost':counter_restart_cost,
            'saved_bytes':size,'variant_cpu_s':variant_cpu,
            'examples':{'source':64,'target':128,'counterevidence':32,
                        'incompatible':64}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--order',type=int,required=True)
    order=parser.parse_args().order
    if order not in ORDERS:
        raise ValueError('Orden no preregistrado.')
    frozen=git('rev-parse','freeze-B-1:leobot')
    if git('diff','--name-only','freeze-B-1','--','leobot'):
        raise RuntimeError('El motor difiere del tag congelado.')
    seed=int(frozen[:8],16)+(order-17)//36
    started=time.perf_counter();result=one_order(order,seed)
    if git('rev-parse','freeze-B-1:leobot')!=frozen or git(
            'diff','--name-only','freeze-B-1','--','leobot'):
        raise RuntimeError('El motor cambió durante el ensayo.')
    result.update(preregistration='prereg/B-1-operador-agregado.md',
                  frozen_engine_tree=frozen,engine_unchanged=True,
                  wall_s=round(time.perf_counter()-started,5),
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    output=ROOT/'results_v3'/f'b1_aggregate_order{order}.json'
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()

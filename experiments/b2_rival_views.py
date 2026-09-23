"""B-2 frozen-engine comparison of rival views and an environment-run probe."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import resource
import time

from leobot.metacontrol import MetaController
from experiments.b1_aggregate_operator import (
    ROOT, ORDERS, clock, git, incompatible_rows, instrument, pair, reserves,
    restart, source_rows, target_rows, teach,
)


def evaluate(controller,family,rows,labels):
    started=time.process_time();correct=wrong_confident=abstentions=0;modes={}
    for features,positive in rows:
        truth=labels[0] if positive else labels[1]
        route=controller.rank(family,features,labels)
        mode=route['mode'];modes[mode]=modes.get(mode,0)+1
        abstentions+=int(mode in ('default','ambiguous'))
        correct+=int(mode not in ('default','ambiguous') and route['order'][0]==truth)
        wrong_confident+=int(mode not in ('default','ambiguous') and
                             route['order'][0]!=truth)
    return {'correct_supported':correct,'total':len(rows),
            'wrong_confident':wrong_confident,'abstentions':abstentions,
            'modes':modes,'cpu_s':round(time.process_time()-started,5)}


def probe_pool(rows):
    """Unlabeled sign interventions retaining observed feature magnitudes."""
    frequency=Counter(features[-1] for features,_ in rows)
    ordered=sorted(rows,key=lambda row:(-frequency[row[0][-1]],row[0]))
    pool=[]
    for features,positive in ordered[:16]:
        changed=tuple((-abs(value) if positive else abs(value))
                      for value in features[:-1])+(features[-1],)
        pool.append({'features':changed,'cost':1})
    return pool


def probe_and_observe(controller,family,pool,labels):
    proposal=controller.propose_meta_probe(family,pool)
    if proposal.get('status')!='epistemic_action':
        return proposal
    chosen=pool[proposal['chosen_index']]['features']
    # This ground truth is returned by the independent environment.  The
    # controller sees only strategy outcomes through its normal observe API.
    positive=sum(value>0 for value in chosen)>=5
    teach(controller,family,[(chosen,positive)],labels)
    return {**proposal,'observed_outcome':labels[0] if positive else labels[1]}


def one_order(order,seed):
    labels_source=('A','B');labels_target=('north','south')
    source=source_rows(order);target,remaining=target_rows(order)
    source_reserve,target_reserve=reserves(seed,remaining.copy())
    treatment=MetaController();nested=instrument(treatment)
    _,source_cost=clock(lambda:teach(treatment,'source',source,labels_source))
    source_only=treatment.as_dict()
    source_score=evaluate(treatment,'source',source_reserve,labels_source)
    _,target_cost=clock(lambda:teach(treatment,'new_layout',target,labels_target))
    target_score=evaluate(treatment,'new_layout',target_reserve,labels_target)
    educated_candidates=treatment.aggregate_candidates_evaluated.get('new_layout',0)
    (restarted,size),restart_cost=clock(lambda:restart(treatment))
    restart_score=evaluate(restarted,'new_layout',target_reserve,labels_target)

    ablated=MetaController();ablated.enable_meta_operator_invention=False
    _,ablation_cost=clock(lambda:teach(ablated,'source',source,labels_source))
    ablation_score=evaluate(ablated,'source',source_reserve,labels_source)
    fresh=MetaController();_,fresh_cost=clock(
        lambda:teach(fresh,'new_layout',target,labels_target))
    fresh_candidates=fresh.aggregate_candidates_evaluated.get('new_layout',0)
    fresh_score=evaluate(fresh,'new_layout',target_reserve,labels_target)
    memory=MetaController.from_dict(treatment.as_dict())
    memory.invented_views.clear();memory.meta_rivals.clear()
    memory.meta_operators.clear();memory.routers.clear()
    memory_score=evaluate(memory,'new_layout',target_reserve,labels_target)

    incompatible=MetaController.from_dict(treatment.as_dict())
    _,incompatible_cost=clock(lambda:teach(
        incompatible,'incompatible',incompatible_rows(order),('high','low')))
    incompatible_kind=(incompatible.invented_views.get('incompatible') or {}).get('kind')

    renamed=MetaController();_,rename_cost=clock(lambda:(
        teach(renamed,'familia_x',source,('p','q')),
        teach(renamed,'familia_y',target,('u','v'))))
    rename_score=evaluate(renamed,'familia_y',target_reserve,('u','v'))

    proxy_target,proxy_remaining=target_rows(order,confounded=True)
    _,proxy_reserve=reserves(seed+73,proxy_remaining.copy(),confounded=True)
    confounded=MetaController.from_dict(source_only)
    _,confound_cost=clock(lambda:teach(
        confounded,'proxy_layout',proxy_target,labels_target))
    rivals_before=len(confounded.meta_rivals.get('proxy_layout',()))
    before_probe=evaluate(confounded,'proxy_layout',proxy_reserve,labels_target)
    (unresolved,_),unresolved_save=clock(lambda:restart(confounded))
    rivals_after_restart=len(unresolved.meta_rivals.get('proxy_layout',()))
    pool=probe_pool(proxy_target)
    proposal,probe_cost=clock(lambda:probe_and_observe(
        unresolved,'proxy_layout',pool,labels_target))
    after_probe=evaluate(unresolved,'proxy_layout',proxy_reserve,labels_target)
    (resolved,_),resolved_save=clock(lambda:restart(unresolved))
    after_probe_restart=evaluate(resolved,'proxy_layout',proxy_reserve,labels_target)

    no_rivals=MetaController.from_dict(source_only);no_rivals.enable_meta_rivals=False
    _,no_rivals_cost=clock(lambda:teach(
        no_rivals,'proxy_layout',proxy_target,labels_target))
    no_rivals_score=evaluate(no_rivals,'proxy_layout',proxy_reserve,labels_target)

    contradicted=MetaController.from_dict(treatment.as_dict())
    counter=[]
    for index in range(64,96):
        features,_=pair(index)
        counter.append((features,bool(index&1)))
    _,counter_cost=clock(lambda:teach(contradicted,'source',counter,labels_source))
    dependent_withdrawn='new_layout' not in contradicted.invented_views
    (counter_restarted,_),counter_restart_cost=clock(lambda:restart(contradicted))
    dependent_withdrawn_after='new_layout' not in counter_restarted.invented_views

    treatment_cpu={
        'source_and_target':source_cost['cpu_s']+target_cost['cpu_s']+
                            source_score['cpu_s']+target_score['cpu_s'],
        'confound_acquisition_and_probe':confound_cost['cpu_s']+probe_cost['cpu_s']+
                                        after_probe['cpu_s'],
        'renamed':rename_cost['cpu_s']+rename_score['cpu_s'],
        'incompatible':incompatible_cost['cpu_s'],
        'counterevidence':counter_cost['cpu_s']+counter_restart_cost['cpu_s'],
    }
    controls={
        'accuracy_f1':source_score['correct_supported']>=116,
        'accuracy_f2':target_score['correct_supported']>=116,
        'ablation':ablation_score['correct_supported']<=96,
        'reuse':educated_candidates<fresh_candidates,
        'before_probe_safe':rivals_before==1 and rivals_after_restart==1 and
                            before_probe['wrong_confident']==0,
        'active_probe':proposal.get('status')=='epistemic_action' and
                       proposal.get('chosen',{}).get('info_gain_bits',0)>0 and
                       'observed_outcome' in proposal,
        'after_probe':after_probe['correct_supported']>=116 and
                      after_probe['wrong_confident']==0 and
                      after_probe_restart['correct_supported']>=116,
        'counterevidence':dependent_withdrawn and dependent_withdrawn_after and
                          not counter_restarted.meta_operators,
        'restart':restart_score['correct_supported']>=116,
        'rename':rename_score['correct_supported']>=116,
        'incompatible':incompatible_kind!='aggregate_program',
        'treatment_cpu_budget':all(cpu<=30 for cpu in treatment_cpu.values()),
    }
    return {'order_seed':order,'reserve_seed':seed,'controls':controls,
            'treatment_f1':source_score,'treatment_f2':target_score,
            'ablation_f1':ablation_score,'fresh_f2':fresh_score,
            'memory_only_f2':memory_score,'restart_f2':restart_score,
            'rename_f2':rename_score,'incompatible_kind':incompatible_kind,
            'confounded_before_probe':before_probe,
            'confounded_after_probe':after_probe,
            'confounded_after_restart':after_probe_restart,
            'no_rivals_same_information':no_rivals_score,
            'rivals_before_probe':rivals_before,
            'rivals_after_restart':rivals_after_restart,'proposal':proposal,
            'educated_f2_candidates':educated_candidates,
            'fresh_f2_candidates':fresh_candidates,
            'dependent_withdrawn':dependent_withdrawn,
            'dependent_withdrawn_after_restart':dependent_withdrawn_after,
            'costs':{'source':source_cost,'target':target_cost,'ablation':ablation_cost,
                     'fresh':fresh_cost,'incompatible':incompatible_cost,
                     'rename':rename_cost,'confounded':confound_cost,
                     'probe':probe_cost,'no_rivals':no_rivals_cost,
                     'counterevidence':counter_cost,'restart':restart_cost,
                     'restart_unresolved':unresolved_save,
                     'restart_resolved':resolved_save,
                     'restart_counter':counter_restart_cost},
            'nested_cpu_s_nonadditive':{k:round(v,5) for k,v in nested.items()},
            'treatment_variant_cpu_s':treatment_cpu,
            'examples':{'source':64,'target':128,'probe':1,'counterevidence':32},
            'saved_bytes':size}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--order',type=int,required=True)
    parser.add_argument('--development',action='store_true')
    args=parser.parse_args()
    if args.order not in ORDERS:
        raise ValueError('Orden no preregistrado.')
    if args.development:
        frozen=None;seed=991
    else:
        frozen=git('rev-parse','freeze-B-2:leobot')
        if git('diff','--name-only','freeze-B-2','--','leobot'):
            raise RuntimeError('El motor difiere del tag congelado.')
        seed=int(frozen[:8],16)+ORDERS.index(args.order)
    started=time.perf_counter();result=one_order(args.order,seed)
    if frozen and (git('rev-parse','freeze-B-2:leobot')!=frozen or git(
            'diff','--name-only','freeze-B-2','--','leobot')):
        raise RuntimeError('El motor cambió durante el ensayo.')
    result.update(preregistration='prereg/B-2-hipotesis-rivales.md',
                  frozen_engine_tree=frozen,engine_unchanged=bool(frozen),
                  wall_s=round(time.perf_counter()-started,5),
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if frozen:
        output=ROOT/'results_v3'/f'b2_rivals_order{args.order}.json'
        output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()

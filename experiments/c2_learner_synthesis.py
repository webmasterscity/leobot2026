"""Frozen-engine learner synthesis; the environment owns every outcome."""
from __future__ import annotations

import argparse
import json
import random
import resource
import time
from pathlib import Path

from leobot.metacontrol import MetaController
from experiments.b1_aggregate_operator import ROOT,git,restart
from tests.test_learner_synthesis_c2 import first,second


ORDERS=(17,53,97)
LABELS=('north','south')


def teach(controller,family,rows,labels=LABELS,*,reverse=False):
    started=time.process_time()
    for features,positive in rows:
        positive=not positive if reverse else positive
        for label in labels:
            success=(label==labels[0])==positive
            controller.observe(family,features,label,success=success,
                               cost=1 if success else 9,failure_budget=2)
    return round(time.process_time()-started,6)


def teach_with_search_budget(controller,family,rows,labels=LABELS):
    """Deliver every episode while stopping search at the fixed CPU ceiling."""
    controller.meta_search_cpu_limit_s=28.5
    cpu=teach(controller,family,rows,labels)
    return cpu,family in controller.meta_search_exhausted,(
        controller.meta_search_exhausted.get(family))


def evaluate(controller,family,rows,labels=LABELS):
    started=time.process_time();correct=wrong=abstain=0;modes={}
    for features,positive in rows:
        route=controller.rank(family,features,labels)
        mode=route['mode'];modes[mode]=modes.get(mode,0)+1
        uncertain=mode in ('default','ambiguous')
        abstain+=int(uncertain)
        correct+=int(not uncertain and (route['order'][0]==labels[0])==positive)
        wrong+=int(not uncertain and (route['order'][0]==labels[0])!=positive)
    return {'correct_supported':correct,'wrong_confident':wrong,
            'abstentions':abstain,'total':len(rows),'modes':modes,
            'cpu_s':round(time.process_time()-started,6)}


def train_indices(order,offset):
    return random.Random(order+offset).sample(range(512),128)


def reserve_rows(seed,trained,kind):
    rng=random.Random(seed)
    remaining=sorted(set(range(512))-set(trained))
    indices=rng.sample(remaining,128)
    rows=[]
    for index in indices:
        bits=[(index>>k)&1 for k in range(9)]
        if kind=='first':
            context=2*bits[0]-1
            features=(context*rng.randint(1,1000),
                      *((1 if bit else -1)*rng.randint(2,500)
                        for bit in bits[1:]))
            positive=sum(bits[1:])>=(6 if context>0 else 3)
        else:
            context=bits[0]
            center=rng.choice((-1,1))*rng.randint(10_000,1_000_000)
            delta=rng.randint(2,200)
            pair=((center+delta,center-delta) if context else
                  (center-delta,center+delta))
            features=pair+tuple((1 if bit else -1)*rng.randint(2,500)
                                for bit in bits[1:])
            positive=sum(bits[1:])>=(6 if context else 4)
        rows.append((features,positive))
    return rows


def confound(rows,*,inverse=False):
    result=[]
    for features,positive in rows:
        factor=(1 if positive else 4) if inverse else (4 if positive else 1)
        result.append((tuple(value*factor for value in features),positive))
    return result


def incompatible_rows(order):
    rng=random.Random(order+783)
    rows=[]
    for index in rng.sample(range(512),64):
        values,_=first(index)
        values=list(values);high=bool(rng.getrandbits(1))
        if high:
            position=rng.randrange(1,len(values))
            values[position]*=100
        rows.append((tuple(values),high))
    return rows


def one_order(order,seed,*,progress=False):
    def report(stage):
        if progress:
            print(f'desarrollo {order}: {stage}',flush=True)
    source_indices=train_indices(order,0)
    target_indices=train_indices(order,101)
    source=[first(i) for i in source_indices]
    target=[second(i) for i in target_indices]
    source_reserve=reserve_rows(seed,source_indices,'first')
    target_reserve=reserve_rows(seed+101,target_indices,'second')

    educated=MetaController()
    source_cpu=teach(educated,'source',source)
    source_score=evaluate(educated,'source',source_reserve)
    source_view=(educated.invented_views.get('source') or {}).get('kind')
    source_program=(educated.invented_views.get('source') or {}).get('learner_program')
    target_cpu=teach(educated,'target',target)
    report(f'tratamiento {source_cpu:.2f}+{target_cpu:.2f} s CPU')
    target_score=evaluate(educated,'target',target_reserve)
    target_view=(educated.invented_views.get('target') or {}).get('kind')
    target_dependency=(educated.invented_views.get('target') or {}).get('learner_dependency')
    educated_counts=educated.learner_synthesis_counts.get('target',{})
    (reloaded,size),restart_wall=timed(lambda:restart(educated))
    restart_score=evaluate(reloaded,'target',target_reserve)

    ablated=MetaController();ablated.enable_learner_synthesis=False
    ablation_cpu,ablation_exhausted,ablation_search_stopped_at=(
        teach_with_search_budget(ablated,'source',source))
    report(f'ablación {ablation_cpu:.2f} s CPU')
    ablation_score=evaluate(ablated,'source',source_reserve)
    fresh=MetaController();fresh_cpu=teach(fresh,'target',target)
    report(f'fresco {fresh_cpu:.2f} s CPU')
    fresh_score=evaluate(fresh,'target',target_reserve)
    fresh_counts=fresh.learner_synthesis_counts.get('target',{})
    memory=MetaController.from_dict(educated.as_dict())
    memory.invented_views.clear();memory.meta_learners.clear();memory.routers.clear()
    memory_score=evaluate(memory,'target',target_reserve)

    renamed=MetaController()
    rename_source_cpu=teach(renamed,'fuente_nueva',source,('p','q'))
    rename_target_cpu=teach(renamed,'destino_nuevo',target,('u','v'))
    report(f'renombrado {rename_source_cpu+rename_target_cpu:.2f} s CPU')
    rename_score=evaluate(renamed,'destino_nuevo',target_reserve,('u','v'))

    misleading=MetaController()
    confound_cpu=teach(misleading,'misleading',confound(source))
    report(f'confusor {confound_cpu:.2f} s CPU')
    confound_score=evaluate(misleading,'misleading',confound(source_reserve,inverse=True))

    incompatible=MetaController()
    incompatible_cpu=teach(incompatible,'other_structure',incompatible_rows(order))
    report(f'incompatible {incompatible_cpu:.2f} s CPU')
    incompatible_kind=(incompatible.invented_views.get('other_structure') or {}).get('kind')

    counter=MetaController.from_dict(educated.as_dict())
    contrary=[first(index) for index in range(512,544)]
    counter_cpu=teach(counter,'source',contrary,reverse=True)
    report(f'contraevidencia {counter_cpu:.2f} s CPU')
    (challenged,_),counter_restart_wall=timed(lambda:restart(counter))
    withdrawn=('target' not in challenged.invented_views and
               not challenged.meta_learners)

    treatment_cpu={'source_and_target':source_cpu+target_cpu+
                   source_score['cpu_s']+target_score['cpu_s'],
                   'fresh':fresh_cpu+fresh_score['cpu_s'],
                   'ablation':ablation_cpu+ablation_score['cpu_s'],
                   'rename':rename_source_cpu+rename_target_cpu+rename_score['cpu_s'],
                   'confound':confound_cpu+confound_score['cpu_s'],
                   'incompatible':incompatible_cpu,'counterevidence':counter_cpu}
    controls={
        'source_heldout':source_score['correct_supported']>=116,
        'target_heldout':target_score['correct_supported']>=116,
        'new_learner':source_view=='learner_product' and
                      target_view=='learner_product' and bool(target_dependency),
        'ablation':ablation_score['correct_supported']<116,
        'transfer':(educated_counts.get('hypotheses',10**9)<
                    fresh_counts.get('hypotheses',0) or target_cpu<fresh_cpu),
        'fresh_same_information':fresh_score['correct_supported']>=116,
        'memory_only':memory_score['correct_supported']<116,
        'restart':restart_score['correct_supported']>=116,
        'renaming':rename_score['correct_supported']>=116,
        'confound':confound_score['correct_supported']>=116 and
                    confound_score['wrong_confident']==0,
        'incompatible':incompatible_kind!='learner_product',
        'counterevidence':withdrawn,
        'cpu_budget':all(value<=30 for value in treatment_cpu.values()),
        'no_unresolved_ambiguity':all(
            not educated.meta_rivals.get(family) for family in ('source','target')),
        'program_has_no_target_metadata':bool(source_program) and
            not any(token in json.dumps(source_program,sort_keys=True)
                    for token in ('source','target','north','south')),
    }
    return {'controls':controls,'source':source_score,'target':target_score,
            'ablation':ablation_score,'fresh':fresh_score,'memory_only':memory_score,
            'restart':restart_score,'renamed':rename_score,'confound':confound_score,
            'incompatible_kind':incompatible_kind,'counterevidence_withdrew':withdrawn,
            'source_view':source_view,'source_program':source_program,
            'target_view':target_view,'target_dependency':target_dependency,
            'source_search':educated.learner_synthesis_counts.get('source',{}),
            'target_search':educated_counts,'fresh_search':fresh_counts,
            'rivals':{family:len(educated.meta_rivals.get(family,()))
                      for family in ('source','target')},
            'ablation_budget_exhausted':ablation_exhausted,
            'ablation_search_stopped_at_example':ablation_search_stopped_at,
            'ablation_examples_delivered':len(source),
            'cpu_s':treatment_cpu,'restart_wall_s':restart_wall,
            'counter_restart_wall_s':counter_restart_wall,
            'saved_bytes':size,'examples':{'source':128,'target':128,
                                          'counterevidence':32,'incompatible':64}}


def timed(action):
    started=time.perf_counter();result=action()
    return result,round(time.perf_counter()-started,6)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--order',type=int,required=True)
    parser.add_argument('--development',action='store_true')
    args=parser.parse_args()
    if args.order not in ORDERS:
        raise ValueError('Orden no preregistrado.')
    if args.development:
        frozen=None;seed=991+ORDERS.index(args.order)
    else:
        frozen=git('rev-parse','freeze-C-2:leobot')
        if git('diff','--name-only','freeze-C-2','--','leobot'):
            raise RuntimeError('El motor difiere del tag congelado.')
        seed=int(frozen[:8],16)+ORDERS.index(args.order)
    started=time.perf_counter();row=one_order(args.order,seed,
                                               progress=args.development)
    if frozen and (git('rev-parse','freeze-C-2:leobot')!=frozen or git(
            'diff','--name-only','freeze-C-2','--','leobot')):
        raise RuntimeError('El motor cambió durante el ensayo.')
    result={'preregistration':'prereg/C-2-sintesis-learner-compuesto.md',
            'frozen_engine_tree':frozen,'engine_unchanged':bool(frozen),
            'order_seed':args.order,'reserve_seed':seed,**row,
            'wall_s':round(time.perf_counter()-started,6),
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    result['controls']['ram_budget']=result['peak_rss_kib']<=256*1024
    if frozen:
        output=ROOT/'results_v3'/f'c2_learner_order{args.order}.json'
        output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'order':args.order,'controls':result['controls'],
                      'source':result['source']['correct_supported'],
                      'target':result['target']['correct_supported'],
                      'cpu_s':result['cpu_s'],'wall_s':result['wall_s']},
                     ensure_ascii=False))


if __name__=='__main__':
    main()

"""D-1: environment-led text → symbolic action → numeric procedure chain."""
from __future__ import annotations

import argparse
import json
import random
import resource
import tempfile
import time
from pathlib import Path

from leobot import Atom,Bot
from leobot.metarepr import MetaRepresentationLibrary
from experiments.b1_aggregate_operator import ROOT,git
from tests.test_learner_synthesis_c2 import first as numeric_meta_source


ORDERS=(17,53,97)
WORDS=(('agente','vincula','paquete','sector','Permuta'),
       ('operador','asocia','pieza','region','Desplaza'),
       ('tecnico','relaciona','artefacto','area','Transporta'))


def clock(action):
    started=time.process_time();wall=time.perf_counter()
    result=action()
    return result,{'cpu_s':round(time.process_time()-started,6),
                   'wall_s':round(time.perf_counter()-wall,6)}


def a_experience(bot,prefix,words):
    who,verb,what,where,_action=words
    for person,zone in (('ana','norte'),('beto','sur'),('carla','este')):
        bot.kb.add(Atom(prefix+'site_of',(prefix+person,prefix+zone)),
                   'd1_environment')
    for item in ('rojo','azul','verde','negro'):
        bot.kb.add(Atom(prefix+'item',(prefix+item,)),'d1_environment')
    cases=(('ana','rojo','norte',True),('beto','azul','sur',True),
           ('ana','azul','sur',False),('ana','verde','este',False))
    reports=[]
    for person,item,zone,positive in cases:
        sentence=(f'{who} {prefix+person} '+('' if positive else 'no ')+
                  f'{verb} {what} {prefix+item} en {where} {prefix+zone}')
        reports.append(bot.observe_schema_statement(sentence))
    return reports


def b_world(prefix,index,*,success=True,missing=None):
    person=f'{prefix}p{index}';origin=f'{prefix}o{index}';dest=f'{prefix}d{index}'
    before={(prefix+'loc',person,origin),(prefix+'link',origin,dest),
            (prefix+'agent',person),(prefix+'place',origin),(prefix+'place',dest)}
    if missing=='link':
        before.discard((prefix+'link',origin,dest))
    after=set(before)
    if success:
        after.remove((prefix+'loc',person,origin))
        after.add((prefix+'loc',person,dest))
    return person,origin,dest,before,after


def b_experience(bot,prefix,words):
    verb=words[-1];reports=[]
    for index,success in ((0,True),(1,True),(2,False)):
        person,origin,dest,before,after=b_world(
            prefix,index,success=success,missing=None if success else 'link')
        reports.append(bot.observe_symbolic_transition(
            f'{verb} a {person} desde {origin} hacia {dest}.',before,after))
    return reports


def c_rows(shift):
    x,u,v,y=2+shift,3+shift,5+shift,7+shift
    return ((x,u,v,y),(x,u+17,v,y),(x,u,v+19,y),
            (x+2,u,v,y),(x,u,v,y+2))


def c_experience(bot,prefix,shift):
    bot.programs.max_candidates=150
    label=f'Calcula mezcla {prefix}.'
    reports=[]
    for values in c_rows(shift):
        reports.append(bot.observe_transition(
            label,values,(values[0]*values[3]+1,)))
    return label,reports


def remove_transfer(bot):
    """Ablate structural sharing while retaining ordinary episodes and KB."""
    bot.meta_representations=MetaRepresentationLibrary()
    for learner in (bot.procedures,bot.symbolic):
        for name in ('external_projection_schemas','external_permutation_schemas',
                     'external_role_sets','external_role_cardinalities',
                     'external_role_topologies'):
            if hasattr(learner,name):
                getattr(learner,name).clear()


def preeducate_learner(bot):
    indices=random.Random(17).sample(range(512),128)
    for index in indices:
        features,positive=numeric_meta_source(index)
        for strategy in ('north','south'):
            success=(strategy=='north')==positive
            bot.meta_controller.observe('learner_source',features,strategy,
                                        success=success,cost=1 if success else 9)
    return bool(bot.meta_controller.meta_learners)


def c_cases(seed):
    rng=random.Random(seed)
    rows=[]
    for _ in range(128):
        a=rng.choice((-1,1))*rng.randint(1,150)
        d=rng.choice((-1,1))*rng.randint(1,150)
        # Both nuisance inputs change independently and reverse their training
        # correlation with the useful positions.
        b=-a+rng.randint(400,2000)
        c=-d-rng.randint(400,2000)
        rows.append((a,b,c,d))
    return rows


def score_c(bot,label,rows):
    times=[];correct=wrong_confident=0
    for values in rows:
        started=time.perf_counter_ns()
        report=bot.execute_transition(label,values)
        times.append((time.perf_counter_ns()-started)/1e6)
        expected=(values[0]*values[3]+1,)
        correct+=int(report.get('result')==expected)
        wrong_confident+=int(report.get('status')=='procedure_executed'
                             and report.get('result')!=expected)
    ordered=sorted(times)
    return {'correct':correct,'total':len(rows),
            'wrong_confident':wrong_confident,
            'p50_ms':round(ordered[len(ordered)//2],5),
            'p95_ms':round(ordered[121],5),'max_ms':round(max(times),5)}


def score_b(bot,prefix,words,seed):
    rng=random.Random(seed);times=[];correct=unsafe=0
    for index in rng.sample(range(1000,100_000),128):
        person,origin,dest,before,_after=b_world(prefix,index)
        cue=f'{words[-1]} a {person} desde {origin} hacia {dest}.'
        started=time.perf_counter_ns()
        report=bot.execute_symbolic_transition(cue,before)
        times.append((time.perf_counter_ns()-started)/1e6)
        correct+=int(report.get('status')=='executed_symbolic_action' and
                     (prefix+'loc',person,dest) in set(report.get('result',())))
        missing=set(before);missing.remove((prefix+'link',origin,dest))
        blocked=bot.execute_symbolic_transition(cue,missing)
        unsafe+=int(blocked.get('status')=='executed_symbolic_action')
    ordered=sorted(times)
    return {'correct':correct,'total':128,'unsafe_without_precondition':unsafe,
            'p50_ms':round(ordered[64],5),'p95_ms':round(ordered[121],5),
            'max_ms':round(max(times),5)}


def restart(bot):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'state.json'
        bot.save(path);size=path.stat().st_size
        del bot
        return Bot.load(path),size


def run_variant(name,*,use_a,use_b,prefix,words,shift,rows,seed,
                disable_transfer=False,preeducate=False,reload_before_c=False):
    bot=Bot();costs={};learned_c2=False
    if preeducate:
        learned_c2,costs['preeducation']=clock(lambda:preeducate_learner(bot))
    a_reports=b_reports=[]
    if use_a:
        a_reports,costs['a']=clock(lambda:a_experience(bot,prefix,words))
    if disable_transfer:
        remove_transfer(bot)
    if use_b:
        b_reports,costs['b']=clock(lambda:b_experience(bot,prefix,words))
    b_score=score_b(bot,prefix,words,seed+17) if use_b else None
    if disable_transfer:
        remove_transfer(bot)
    persisted_bytes=None
    if reload_before_c:
        (bot,persisted_bytes),costs['restart']=clock(lambda:restart(bot))
    structural_before=[row for row in bot.meta_representations.rows()
                       if row.get('kind')=='role_cardinality']
    (label,c_reports),costs['c']=clock(lambda:c_experience(bot,prefix,shift))
    score=score_c(bot,label,rows)
    last=c_reports[-1]
    details=(last.get('reports') or [{}])[0]
    attempted=sum(int(rep.get('candidates',0)) for report in c_reports
                  for rep in report.get('reports',()))
    return {'name':name,'a_status':a_reports[-1].get('status') if a_reports else None,
            'b_status':b_reports[-1].get('status') if b_reports else None,
            'b_mode':b_reports[-1].get('precondition_mode') if b_reports else None,
            'c_status':last.get('status'),'c_mode':last.get('precondition_mode'),
            'c_dependency':details.get('meta_dependency_schema'),
            'c_candidates_last':details.get('candidates'),
            'c_candidates_total':attempted,'c_score':score,'b_score':b_score,
            'structural_prior_before_c':structural_before,
            'c2_learner_preeducated':learned_c2,
            'c2_learner_rows':len(bot.meta_controller.meta_learners),
            'costs':costs,'persisted_bytes':persisted_bytes,
            'episodes':{'a':4 if use_a else 0,'b':3 if use_b else 0,'c':5}}


def one_order(order,seed):
    index=ORDERS.index(order);words=WORDS[index]
    prefix=f'd{seed%10_000}x{index}'
    shift=(0,3,7)[index]
    rows=c_cases(seed)
    ab=run_variant('a_b',use_a=True,use_b=True,prefix=prefix,words=words,
                   shift=shift,rows=rows,seed=seed,reload_before_c=True)
    a=run_variant('a_only',use_a=True,use_b=False,prefix=prefix,words=words,
                  shift=shift,rows=rows,seed=seed)
    b=run_variant('b_only',use_a=False,use_b=True,prefix=prefix,words=words,
                  shift=shift,rows=rows,seed=seed)
    fresh=run_variant('fresh',use_a=False,use_b=False,prefix=prefix,words=words,
                      shift=shift,rows=rows,seed=seed)
    no_transfer=run_variant('same_information_no_transfer',use_a=True,use_b=True,
                            prefix=prefix,words=words,shift=shift,rows=rows,
                            seed=seed,disable_transfer=True)
    c2=run_variant('c2_preeducated',use_a=True,use_b=True,prefix=prefix,
                   words=words,shift=shift,rows=rows,seed=seed,preeducate=True)

    # A later contradiction revokes the A source, but retains the independent
    # B evidence. The target is taught only after that real correction.
    corrected=Bot();a_experience(corrected,prefix,words)
    b_experience(corrected,prefix,words)
    who,verb,what,where,_=words
    contradiction=(f'{who} {prefix}ana no {verb} {what} {prefix}rojo '
                   f'en {where} {prefix}norte')
    correction,counter_cost=clock(lambda:corrected.observe_schema_statement(contradiction))
    cards_after=[row for row in corrected.meta_representations.rows()
                 if row.get('kind')=='role_cardinality']
    (label,counter_reports),counter_c_cost=clock(lambda:c_experience(corrected,prefix,shift))

    incompatible=Bot();a_experience(incompatible,prefix,words)
    b_experience(incompatible,prefix,words)
    incompatible.programs.max_candidates=150
    bad=[]
    for values in c_rows(shift):
        bad.append(incompatible.observe_transition(
            f'Combina tres {prefix}.',values,
            (values[0]+values[1]+values[3],)))
    bad_detail=(bad[-1].get('reports') or [{}])[0]

    cpu_variants={row['name']:sum(cost['cpu_s'] for cost in row['costs'].values())
                  for row in (ab,a,b,fresh,no_transfer,c2)}
    controls={
        'a_acquired':ab['a_status']=='schema_learned',
        'a_facilitates_b':ab['b_status']=='operator_learned' and
                           b['b_status']!='operator_learned',
        'ab_facilitates_c':ab['c_status']=='procedure_learned' and
                            all(row['c_status']!='procedure_learned'
                                for row in (a,b,fresh,no_transfer)),
        'b_heldout':ab['b_score']['correct']>=116 and
                     ab['b_score']['unsafe_without_precondition']==0,
        'c_heldout':ab['c_score']['correct']>=116 and
                     ab['c_score']['wrong_confident']==0,
        'dependency_provenance':ab['c_dependency']=='card:2->roles:4:0,3' and
                                len(ab['structural_prior_before_c'])==1 and
                                len(ab['structural_prior_before_c'][0]['sources'])>=2,
        'counterevidence':correction.get('status')=='schema_contradictory' and
                          len(cards_after)==1 and
                          len(cards_after[0]['sources'])==1 and
                          counter_reports[-1].get('status')!='procedure_learned',
        'incompatible':bad_detail.get('meta_dependency_schema') is None,
        'restart':ab['persisted_bytes'] is not None,
        'cpu_budget':all(value<=30 for value in cpu_variants.values()),
        'c2_source_present':c2['c2_learner_preeducated'],
    }
    return {'order':order,'seed':seed,'controls':controls,
            'variants':{row['name']:row for row in
                        (ab,a,b,fresh,no_transfer,c2)},
            'c2_transfer':{'extra_examples_saved':0 if c2['c_status']==ab['c_status']
                                                  else None,
                           'candidates_delta':c2['c_candidates_total']-
                                              ab['c_candidates_total'],
                           'cpu_delta_s':c2['costs']['c']['cpu_s']-
                                         ab['costs']['c']['cpu_s']},
            'counterevidence':{'correction':correction.get('status'),
                               'remaining_cardinality_sources':cards_after,
                               'c_status':counter_reports[-1].get('status'),
                               'costs':{'correction':counter_cost,
                                        'c':counter_c_cost}},
            'incompatible':{'status':bad[-1].get('status'),
                            'dependency':bad_detail.get('meta_dependency_schema')},
            'cpu_variants':cpu_variants}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--order',type=int,required=True)
    parser.add_argument('--development',action='store_true')
    args=parser.parse_args()
    if args.order not in ORDERS:
        raise ValueError('Orden no preregistrado.')
    if args.development:
        frozen=None;seed=901+ORDERS.index(args.order)
    else:
        frozen=git('rev-parse','freeze-D-1:leobot')
        if git('diff','--name-only','freeze-D-1','--','leobot'):
            raise RuntimeError('El motor difiere del tag congelado.')
        seed=int(frozen[:8],16)+ORDERS.index(args.order)
    start=time.perf_counter();row=one_order(args.order,seed)
    if frozen and (git('rev-parse','freeze-D-1:leobot')!=frozen or git(
            'diff','--name-only','freeze-D-1','--','leobot')):
        raise RuntimeError('El motor cambió durante el ensayo.')
    result={'preregistration':'prereg/D-1-cadena-entre-modalidades.md',
            'frozen_engine_tree':frozen,'engine_unchanged':bool(frozen),
            **row,'wall_s':round(time.perf_counter()-start,6),
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    result['controls']['ram_budget']=result['peak_rss_kib']<=256*1024
    if frozen:
        output=ROOT/'results_v3'/f'd1_chain_order{args.order}.json'
        output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'order':args.order,'controls':result['controls'],
                      'ab_c':row['variants']['a_b']['c_status'],
                      'a_c':row['variants']['a_only']['c_status'],
                      'b_c':row['variants']['b_only']['c_status'],
                      'fresh_c':row['variants']['fresh']['c_status'],
                      'c2_transfer':row['c2_transfer'],
                      'wall_s':result['wall_s']},ensure_ascii=False))


if __name__=='__main__':
    main()

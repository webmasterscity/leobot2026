"""Frozen F-6b assay: raw text plus observed world transitions across role orders."""
from __future__ import annotations

import json
import random
import resource
import statistics
import subprocess
import tempfile
import time
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.b1_aggregate_operator import ROOT
from experiments.d1_cross_modal_chain import c_cases, c_rows


TAG='freeze-F-6b'
ORDERS=(17,53,97)
FAMILIES=(
    {'name':'tres_roles_externo',
     'raw':'La operadora {p} asigna credencial {i} al recinto {d}.',
     'action':'Traslada a {p} desde {o} hacia {d}.',
     'arity':3,'roles':(0,2)},
    {'name':'orden_invertido',
     'raw':'En depósito {d} la persona {p} registra paquete {i}.',
     'action':'Mueve hacia {d} a {p} desde {o}.',
     'arity':3,'roles':(0,1)},
    {'name':'cuatro_roles',
     'raw':'La técnica {p} lleva ficha {i} junto a testigo {j} hasta punto {d}.',
     'action':'Transporta a {p} con ficha {i} desde {o} hasta {d}.',
     'arity':4,'roles':(0,3)},
)


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def frozen():
    tree=git('rev-parse',f'{TAG}:leobot')
    if (git('rev-parse','HEAD:leobot')!=tree or
            git('status','--porcelain','--','leobot')):
        raise RuntimeError('El motor ya no coincide con el árbol congelado')
    return tree


def clock(fn):
    start=time.process_time(); wall=time.monotonic(); value=fn()
    return value,{'cpu_s':round(time.process_time()-start,6),
                  'wall_s':round(time.monotonic()-wall,6)}


def names(prefix,index,seed):
    rng=random.Random(seed+index*1009)
    return {key:f'{prefix}{key}{rng.randrange(10000,99999)}'
            for key in ('p','i','j','d','o')}


def source_experience(bot,spec,prefix,seed,*,documents=True,world=True,
                      incompatible=False):
    examples=[names(prefix,index,seed) for index in range(4)]
    raw=[]; observations=[]
    if documents:
        for index,row in enumerate(examples):
            raw.append(bot.ingest_document_text(spec['raw'].format(**row),
                                                source=f'f6b:origen:{index}'))
    if world:
        for index,row in enumerate(examples[:3]):
            changed=[row['p'],row['d']]
            if incompatible:
                changed=[row['p'],row['i'],row['d']]
                if spec['arity']==4:
                    changed.append(row['j'])
            # The auxiliary inventory value is deliberately permuted across
            # episodes; it never appears in an altered fact in treatment.
            prior={(prefix+'signal',*changed,'closed'),
                   (prefix+'inventory',examples[(index+1)%4]['i'])}
            after={(prefix+'signal',*changed,'open'),
                   (prefix+'inventory',examples[(index+1)%4]['i'])}
            observations.append(bot.observe_world_transition(prior,after))
    return {'raw_statuses':[r.get('promoted_relations',r.get('status')) for r in raw],
            'world_statuses':[r['status'] for r in observations],
            'meta':bot.meta_representations.rows(),
            'examples':examples}


def action_episode(spec,prefix,seed,index,*,success=True):
    row=names(prefix+'target',index+10,seed+7331)
    person,item,origin,dest=row['p'],row['i'],row['o'],row['d']
    before={(prefix+'loc',person,origin),(prefix+'agent',person),
            (prefix+'place',origin),(prefix+'place',dest),
            (prefix+'inventory',item)}
    if success:
        before.add((prefix+'link',origin,dest))
    after=set(before)
    if success:
        after.remove((prefix+'loc',person,origin))
        after.add((prefix+'loc',person,dest))
    cue=spec['action'].format(p=person,i=item,j=row['j'],o=origin,d=dest)
    return cue,before,after,(prefix+'loc',person,dest)


def train_action(bot,spec,prefix,seed,*,fourth=False):
    rows=[action_episode(spec,prefix,seed,i,success=i!=2) for i in range(3)]
    if fourth:
        rows.append(action_episode(spec,prefix,seed,3,success=True))
    return [bot.observe_symbolic_transition(cue,before,after)
            for cue,before,after,_ in rows]


def evaluate_action(bot,spec,prefix,seed):
    correct=unsafe=0; times=[]
    rng=random.Random(seed+222)
    for index in rng.sample(range(1000,100_000),128):
        cue,before,_,expected=action_episode(spec,prefix,seed,index)
        start=time.perf_counter()
        result=bot.execute_symbolic_transition(cue,before)
        times.append((time.perf_counter()-start)*1000)
        correct+=result.get('status')=='executed_symbolic_action' and expected in set(result.get('result',()))
        no_link=set(before)
        no_link={fact for fact in no_link if fact[0]!=prefix+'link'}
        blocked=bot.execute_symbolic_transition(cue,no_link)
        unsafe+=blocked.get('status')=='executed_symbolic_action'
    times.sort()
    return {'correct':correct,'total':128,'unsafe_without_precondition':unsafe,
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[121],5),'max_ms':round(times[-1],5)}


def train_procedure(bot,prefix,shift):
    bot.programs.max_candidates=150
    label=f'Calcula combinación {prefix}.'
    reports=[]
    for x,u,v,y in c_rows(shift):
        reports.append(bot.observe_transition(label,(x,u,v,y),(x*y+1,)))
    return label,reports


def evaluate_procedure(bot,label,seed):
    correct=wrong=0;times=[]
    for values in c_cases(seed)[:128]:
        start=time.perf_counter()
        result=bot.execute_transition(label,values)
        times.append((time.perf_counter()-start)*1000)
        expected=(values[0]*values[3]+1,)
        correct+=result.get('result')==expected
        wrong+=result.get('status')=='procedure_executed' and result.get('result')!=expected
    times.sort()
    return {'correct':correct,'total':len(times),'wrong_confident':wrong,
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[121],5),'max_ms':round(times[-1],5)}


def remove_transfer(bot):
    from leobot.metarepr import MetaRepresentationLibrary
    bot.meta_representations=MetaRepresentationLibrary()
    for learner in (bot.symbolic,bot.procedures):
        for field in ('external_projection_schemas','external_permutation_schemas',
                      'external_role_sets','external_role_cardinalities',
                      'external_role_topologies'):
            getattr(learner,field,{}).clear()


def restart(bot):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json';bot.save(path)
        size=path.stat().st_size
        loaded=Bot.load(path)
    return loaded,size


def variant(spec,prefix,seed,name,*,documents=False,world=False,
            disable_meta=False,fourth=False,incompatible=False,reload=False,
            counter=False,counter_after=False):
    bot=Bot();cost={};size=None
    source,cost['acquisition']=clock(lambda:source_experience(
        bot,spec,prefix,seed,documents=documents,world=world,incompatible=incompatible))
    if disable_meta:
        remove_transfer(bot)
    if reload:
        (bot,size),cost['consolidation']=clock(lambda:restart(bot))
    if counter and source['examples']:
        row=source['examples'][3]
        changed=[row['p'],row['i']]
        prior={(prefix+'signal',*changed,'closed'),(prefix+'destination',row['d'])}
        after={(prefix+'signal',*changed,'open'),(prefix+'destination',row['d'])}
        correction,cost['counterevidence']=clock(lambda:bot.observe_world_transition(prior,after))
    else:
        correction=None
    actions,cost['action_learning']=clock(lambda:train_action(bot,spec,prefix,seed,fourth=fourth))
    action_score,cost['action_response']=clock(lambda:evaluate_action(bot,spec,prefix,seed))
    (label,procedures),cost['procedure_learning']=clock(lambda:train_procedure(bot,prefix,seed%3))
    procedure_score,cost['procedure_response']=clock(lambda:evaluate_procedure(bot,label,seed+73))
    if counter_after and source['examples']:
        row=source['examples'][3]
        changed=[row['p'],row['i']]
        prior={(prefix+'signal',*changed,'closed'),(prefix+'destination',row['d'])}
        after={(prefix+'signal',*changed,'open'),(prefix+'destination',row['d'])}
        late_correction,cost['late_counterevidence']=clock(
            lambda:bot.observe_world_transition(prior,after))
        after_correction={'status':late_correction['status'],
                          'active_actions':len(bot.symbolic.operators()),
                          'action_correct':evaluate_action(bot,spec,prefix,seed)['correct'],
                          'procedure_correct':evaluate_procedure(bot,label,seed+73)['correct']}
    else:
        after_correction=None
    action_candidates=sum(len(row.get('meta_controller_representation_attempts',()))
                          for row in actions)
    procedure_candidates=sum(int(item.get('candidates') or 0)
                             for row in procedures for item in row.get('reports',()))
    return {'name':name,'source_statuses':source['world_statuses'],
            'source_meta':source['meta'],'action_statuses':[x['status'] for x in actions],
            'action_score':action_score,'procedure_statuses':[x['status'] for x in procedures],
            'procedure_score':procedure_score,
            'counter_status':correction['status'] if correction else None,
            'after_counter':after_correction,
            'action_representation_attempts':action_candidates,
            'procedure_candidates':procedure_candidates,
            'persisted_bytes':size,'cost':cost,
            'cpu_total_s':round(sum(x['cpu_s'] for x in cost.values()),6)}


def family_assay(spec,order,tree):
    seed=int(sha256((tree+':F-6b:'+spec['name']+':'+str(order)).encode()).hexdigest()[:8],16)
    prefix=f'r{seed:08x}'
    modes=(('treatment',{'documents':True,'world':True,'reload':True}),
           ('fresh',{}),('raw_only',{'documents':True}),('world_only',{'world':True}),
           ('same_information_no_meta',{'documents':True,'world':True,'disable_meta':True}),
           ('incompatible',{'documents':True,'world':True,'incompatible':True}),
           ('counter_before',{'documents':True,'world':True,'counter':True}),
           ('counter_after',{'documents':True,'world':True,'counter_after':True}),
           ('direct_four',{'fourth':True}))
    variants=[variant(spec,prefix,seed,name,**options) for name,options in modes]
    selected={row['name']:row for row in variants}
    treatment=selected['treatment']
    controls=all(selected[name]['action_statuses'][-1]!='operator_learned'
                 for name in ('fresh','raw_only','world_only','same_information_no_meta',
                              'incompatible','counter_before'))
    source_ok=any(row.get('kind')=='role_set' and
                  row.get('input_arity')==spec['arity'] and
                  row.get('roles')==list(spec['roles'])
                  for row in treatment['source_meta'])
    passed=(source_ok and treatment['action_statuses'][-1]=='operator_learned'
            and treatment['action_score']['correct']>=116
            and treatment['action_score']['unsafe_without_precondition']==0
            and treatment['procedure_score']['correct']>=116
            and treatment['procedure_score']['wrong_confident']==0
            and treatment['action_score']['p95_ms']<=10
            and treatment['procedure_score']['p95_ms']<=10
            and selected['counter_before']['counter_status']=='raw_world_conflict'
            and selected['counter_after']['after_counter']['status']=='raw_world_conflict'
            and selected['counter_after']['after_counter']['active_actions']==0
            and selected['counter_after']['after_counter']['action_correct']==0
            and selected['counter_after']['after_counter']['procedure_correct']==0
            and selected['direct_four']['action_statuses'][-1]=='operator_learned'
            and controls and treatment['persisted_bytes'] is not None)
    return {'family':spec['name'],'order':order,'seed':seed,
            'passed':bool(passed),'controls_passed':controls,
            'variants':variants,'cpu_total_s':round(sum(r['cpu_total_s'] for r in variants),6)}


def main():
    start=time.monotonic();tree=frozen()
    assays=[family_assay(spec,order,tree) for order in ORDERS for spec in FAMILIES]
    unchanged=frozen()==tree
    by_order={str(order):sum(row['passed'] for row in assays if row['order']==order)
              for order in ORDERS}
    output={'preregistration':'prereg/F-6b-geometria-roles-observados.md',
            'tag':TAG,'engine_tree':tree,'engine_unchanged':unchanged,
            'by_order_passes':by_order,
            'gate_passed':unchanged and all(value>=2 for value in by_order.values()),
            'assays':assays,'cpu_total_s':round(sum(x['cpu_total_s'] for x in assays),6),
            'wall_s':round(time.monotonic()-start,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6b_role_geometry_freeze.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'gate_passed':output['gate_passed'],
                      'by_order_passes':by_order,'engine_tree':tree,
                      'assays':[{'family':row['family'],'order':row['order'],
                                 'passed':row['passed'],'controls_passed':row['controls_passed'],
                                 'treatment_b':row['variants'][0]['action_score']['correct'],
                                 'treatment_c':row['variants'][0]['procedure_score']['correct'],
                                 'fresh_b':row['variants'][1]['action_score']['correct'],
                                 'fresh_c':row['variants'][1]['procedure_score']['correct'],
                                 'counter_after':row['variants'][7]['after_counter']}
                                for row in assays],
                      'cpu_total_s':output['cpu_total_s'],
                      'wall_s':output['wall_s'],'max_rss_kib':output['max_rss_kib']},
                     ensure_ascii=False))


if __name__=='__main__':
    main()

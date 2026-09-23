from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter
import json
import random

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v36_hierarchical_skills.json'
F=lambda *x:tuple(x)
S=lambda *facts:frozenset(facts)


def code_hash():
    h=sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def teach_primitives(b: Bot):
    # Move: successes include a spurious correlate; no-change attempts isolate at+road.
    for person,src,dst in [('ana','casa','tienda'),('bruno','plaza','taller'),('carla','parque','museo')]:
        before=S(F('at',person,src),F('road',src,dst),F('autorizado',person),F('person',person),F('place',src),F('place',dst))
        after=(before-{F('at',person,src)})|{F('at',person,dst)}
        b.observe_symbolic_transition(f'Mueve a {person} de {src} a {dst}.',before,after)
    before=S(F('at','lila','patio'),F('autorizado','lila'),F('person','lila'),F('place','patio'),F('place','taller'))
    b.observe_symbolic_transition('Mueve a lila de patio a taller.',before,before)
    before=S(F('road','cocina','plaza'),F('autorizado','hugo'),F('at','hugo','cuarto'),F('person','hugo'),F('place','cocina'),F('place','plaza'),F('place','cuarto'))
    b.observe_symbolic_transition('Mueve a hugo de cocina a plaza.',before,before)

    for person,item,loc in [('ana','caja','tienda'),('bruno','libro','taller'),('carla','llave','museo')]:
        before=S(F('at',person,loc),F('item_at',item,loc),F('entrenado',person),F('person',person),F('item',item),F('place',loc))
        after=(before-{F('item_at',item,loc)})|{F('holding',person,item)}
        b.observe_symbolic_transition(f'{person} toma {item} en {loc}.',before,after)
    before=S(F('at','diego','garaje'),F('entrenado','diego'),F('person','diego'),F('item','mapa'),F('place','garaje'))
    b.observe_symbolic_transition('diego toma mapa en garaje.',before,before)
    before=S(F('item_at','carta','salon'),F('entrenado','eva'),F('at','eva','patio'),F('person','eva'),F('item','carta'),F('place','salon'),F('place','patio'))
    b.observe_symbolic_transition('eva toma carta en salon.',before,before)

    # Drop is intentionally learned from positive examples only. Type facts stay
    # explicit preconditions; held-out worlds provide them, so this is not hidden.
    for person,item,loc in [('ana','caja','oficina'),('bruno','libro','casa'),('carla','llave','biblioteca')]:
        before=S(F('at',person,loc),F('holding',person,item),F('person',person),F('item',item),F('place',loc))
        after=(before-{F('holding',person,item)})|{F('item_at',item,loc)}
        b.observe_symbolic_transition(f'{person} deja {item} en {loc}.',before,after)


def delivery_world(k: int, deliveries: int=2, distractors: int=0):
    person=f'persona_eval_{k}'; facts={F('person',person)}; goals=set(); current=f'inicio_{k}'
    facts.add(F('at',person,current));facts.add(F('place',current))
    delivery_specs=[]
    for j in range(deliveries):
        store=f'tienda_{k}_{j}';dest=f'destino_{k}_{j}';item=f'objeto_{k}_{j}'
        facts.update({F('road',current,store),F('road',store,dest),F('item_at',item,store),
                      F('item',item),F('place',store),F('place',dest)})
        goals.add(F('item_at',item,dest));delivery_specs.append((item,current,store,dest));current=dest
    # Distractors share predicates with useful facts, increasing action branching.
    for d in range(distractors):
        loc=f'ruido_loc_{k}_{d}';nxt=f'ruido_next_{k}_{d}';item=f'ruido_item_{k}_{d}'
        facts.update({F('road',loc,nxt),F('item_at',item,loc),F('item',item),F('place',loc),F('place',nxt)})
    return frozenset(facts),frozenset(goals),delivery_specs


def train_macro(b: Bot):
    training=[]; exact_cache=set()
    for k in range(3):
        person=f'persona_train_{k}';item=f'objeto_train_{k}';home=f'inicio_train_{k}';store=f'tienda_train_{k}';dest=f'destino_train_{k}'
        state=S(F('at',person,home),F('road',home,store),F('road',store,dest),F('item_at',item,store),
                F('person',person),F('item',item),F('place',home),F('place',store),F('place',dest))
        goal=S(F('item_at',item,dest))
        rep=b.learn_symbolic_macro(state,goal,max_steps=6,max_nodes=10000)
        training.append(rep['learning'])
        exact_cache.add((tuple(sorted(state)),tuple(sorted(goal))))
    return training,exact_cache


def reference_verify(initial, goal, report):
    if report.get('status')!='plan_found':return False
    state=set(initial)
    expanded=[]
    for step in report.get('steps',[]):
        expanded.extend(step.get('expanded_steps',[step]))
    for step in expanded:
        binding=step.get('binding',{});pattern=step.get('operator','')
        # Ground-truth executor is independent of Leobot's learned precondition/effect tables.
        if pattern.startswith('mueve a '):
            p,s,d=binding.get('<e0>'),binding.get('<e1>'),binding.get('<e2>')
            if F('at',p,s) not in state or F('road',s,d) not in state:return False
            state.discard(F('at',p,s));state.add(F('at',p,d))
        elif ' toma ' in pattern:
            p,i,l=binding.get('<e0>'),binding.get('<e1>'),binding.get('<e2>')
            if F('at',p,l) not in state or F('item_at',i,l) not in state:return False
            state.discard(F('item_at',i,l));state.add(F('holding',p,i))
        elif ' deja ' in pattern:
            p,i,l=binding.get('<e0>'),binding.get('<e1>'),binding.get('<e2>')
            if F('at',p,l) not in state or F('holding',p,i) not in state:return False
            state.discard(F('holding',p,i));state.add(F('item_at',i,l))
        else:return False
    return set(goal).issubset(state) and frozenset(state)==report.get('result')


def transfer_eval(b: Bot, cache, n=200):
    full=control=verified=cache_hits=0
    full_nodes=[];control_nodes=[];full_trans=[];control_trans=[]
    for k in range(n):
        state,goal,_=delivery_world(k,2,0)
        if (tuple(sorted(state)),tuple(sorted(goal))) in cache:cache_hits+=1
        rf=b.plan_symbolic(state,goal,max_steps=2,max_nodes=5000,use_macros=True)
        rc=b.plan_symbolic(state,goal,max_steps=2,max_nodes=5000,use_macros=False)
        full+=rf['status']=='plan_found';control+=rc['status']=='plan_found';verified+=reference_verify(state,goal,rf)
        # Same primitive depth budget where both are allowed to succeed measures search work.
        df=b.plan_symbolic(state,goal,max_steps=8,max_nodes=50000,use_macros=True)
        dc=b.plan_symbolic(state,goal,max_steps=8,max_nodes=50000,use_macros=False)
        if df['status']=='plan_found' and dc['status']=='plan_found':
            full_nodes.append(df['nodes']);control_nodes.append(dc['nodes'])
            full_trans.append(df['transitions']);control_trans.append(dc['transitions'])
    return {'cases':n,'hierarchy_tight_success':full,'primitive_tight_success':control,'reference_verified':verified,
            'episodic_exact_cache_hits':cache_hits,
            'same_depth_median_nodes_hierarchy':median(full_nodes),'same_depth_median_nodes_primitive':median(control_nodes),
            'same_depth_median_transitions_hierarchy':median(full_trans),'same_depth_median_transitions_primitive':median(control_trans)}


def distractor_eval(b: Bot):
    rows=[]
    for distractors in (0,10,100,500,1000,2000):
        times=[];nodes=[];trans=[];ok=0
        for rep in range(5):
            state,goal,_=delivery_world(10_000+distractors*10+rep,2,distractors)
            t=perf_counter();r=b.plan_symbolic(state,goal,max_steps=2,max_nodes=20000,use_macros=True);times.append((perf_counter()-t)*1000)
            ok+=r['status']=='plan_found';nodes.append(r.get('nodes',0));trans.append(r.get('transitions',0))
        rows.append({'distractors':distractors,'success':ok,'runs':len(times),'median_ms':median(times),
                     'median_nodes':median(nodes),'median_transitions':median(trans)})
    return rows


def horizon_eval(b: Bot):
    rows=[]
    for deliveries in (1,2,4,8,16,32,64,128,256):
        state,goal,_=delivery_world(90_000+deliveries,deliveries,0)
        t=perf_counter();full=b.plan_symbolic(state,goal,max_steps=deliveries,max_nodes=deliveries+16,use_macros=True);ms=(perf_counter()-t)*1000
        row={'deliveries':deliveries,'primitive_equivalent':deliveries*4,'status':full['status'],
             'strategy':full.get('strategy'),'nodes':full.get('nodes'),'transitions':full.get('transitions'),
             'hierarchical_steps':full.get('hierarchical_steps'),'primitive_steps':full.get('primitive_steps'),'ms':ms}
        if deliveries<=8:
            t=perf_counter();control=b.plan_symbolic(state,goal,max_steps=deliveries,max_nodes=5000,use_macros=False);cms=(perf_counter()-t)*1000
            row.update({'primitive_control_status':control['status'],'primitive_control_nodes':control.get('nodes'),
                        'primitive_control_transitions':control.get('transitions'),'primitive_control_ms':cms})
        rows.append(row)
    return rows


def ambiguous_fallback_eval(b: Bot):
    state=S(F('at','nora','hub'),F('road','hub','ta'),F('road','ta','da'),F('item_at','a','ta'),
            F('road','hub','tb'),F('road','tb','db'),F('item_at','b','tb'),F('road','da','tb'),
            F('person','nora'),F('item','a'),F('item','b'),F('place','hub'),F('place','ta'),F('place','da'),F('place','tb'),F('place','db'))
    goal=S(F('item_at','a','da'),F('item_at','b','db'))
    r=b.plan_symbolic(state,goal,max_steps=3,max_nodes=1000,use_macros=True)
    return {'status':r['status'],'strategy':r.get('strategy'),'nodes':r.get('nodes'),'macro_steps':r.get('macro_steps'),
            'goal_reached':goal.issubset(r.get('result',frozenset())) if r.get('result') is not None else False}


def invalidation_eval():
    b=Bot();teach_primitives(b);train_macro(b);before=len(b.symbolic.macros())
    state=S(F('at','zoe','x'),F('road','x','y'),F('person','zoe'),F('place','x'),F('place','y'))
    after=(state-{F('at','zoe','x')})|{F('at','zoe','y'),F('visited','zoe','y')}
    report=b.observe_symbolic_transition('Mueve a zoe de x a y.',state,after)
    after_count=len(b.symbolic.macros())
    return {'macros_before':before,'counterevidence_status':report['status'],'macros_after':after_count}


def main():
    frozen=code_hash();t=perf_counter();b=Bot();teach_primitives(b);training,cache=train_macro(b)
    result={'version':'0.3.6','experiment':'hierarchical_symbolic_skill_induction_from_verified_plans',
            'code_hash_before':frozen,'macro_training':training,'macro_count':len(b.symbolic.macros()),
            'macro':b.symbolic.macros()[0] if b.symbolic.macros() else None,
            'transfer':transfer_eval(b,cache),'distractor_scaling':distractor_eval(b),
            'long_horizon':horizon_eval(b),'ambiguous_fast_path_fallback':ambiguous_fallback_eval(b),
            'dependency_invalidation':invalidation_eval()}
    result['elapsed_s']=perf_counter()-t;result['code_hash_after']=code_hash();result['code_unchanged_during_evaluation']=result['code_hash_after']==frozen
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

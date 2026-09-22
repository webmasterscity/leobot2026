from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter
import json

from leobot import Bot
from v36_hierarchical_skills_experiment import teach_primitives, F, S

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results_v3'/'v37_iterative_skill.json'


def code_hash():
    h=sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def chain_world(prefix: str, length: int, branches: int=0):
    person=f'persona_{prefix}';facts={F('at',person,f'{prefix}_0'),F('person',person)}
    for i in range(length):
        src,dst=f'{prefix}_{i}',f'{prefix}_{i+1}'
        facts.update({F('road',src,dst),F('place',src),F('place',dst)})
        for j in range(branches):
            dead=f'{prefix}_dead_{i}_{j}'
            facts.update({F('road',src,dead),F('place',dead)})
    goal=S(F('at',person,f'{prefix}_{length}'))
    return frozenset(facts),goal


def train_iterative(main: Bot, fixed_control: Bot):
    reports=[];cache=set();fixed_reports=[]
    for idx,length in enumerate((2,3,4)):
        state,goal=chain_world(f'train_{idx}',length)
        rep=main.learn_symbolic_iteration(state,goal,max_steps=8,max_nodes=5000)
        reports.append(rep['learning']);cache.add((tuple(sorted(state)),tuple(sorted(goal))))
        primitive=fixed_control.plan_symbolic(state,goal,max_steps=8,max_nodes=5000,use_macros=False,use_iterations=False)
        fixed_reports.append(fixed_control.symbolic.observe_plan(state,goal,primitive))
    return reports,fixed_reports,cache


def reference_verify(initial,goal,report):
    if report.get('status')!='plan_found':return False
    state=set(initial);expanded=[]
    for step in report.get('steps',[]):expanded.extend(step.get('expanded_steps',[step]))
    for step in expanded:
        if not step.get('operator','').startswith('mueve a '):return False
        b=step['binding'];person,src,dst=b.get('<e0>'),b.get('<e1>'),b.get('<e2>')
        if F('at',person,src) not in state or F('road',src,dst) not in state:return False
        state.remove(F('at',person,src));state.add(F('at',person,dst))
    return set(goal).issubset(state) and frozenset(state)==report.get('result')


def transfer_eval(main: Bot, fixed: Bot, cache, n=200):
    full=primitive=fixed_macro=verified=cache_hits=0;lengths=[];internal_nodes=[];internal_trans=[]
    for k in range(n):
        length=5+(k%60);branches=k%4;state,goal=chain_world(f'heldout_{k}',length,branches);lengths.append(length)
        if (tuple(sorted(state)),tuple(sorted(goal))) in cache:cache_hits+=1
        rf=main.plan_symbolic(state,goal,max_steps=1,max_nodes=10,use_macros=False,use_iterations=True,max_iterative_steps=100)
        rp=main.plan_symbolic(state,goal,max_steps=1,max_nodes=5000,use_macros=False,use_iterations=False)
        rm=fixed.plan_symbolic(state,goal,max_steps=1,max_nodes=5000,use_macros=True,use_iterations=False)
        full+=rf['status']=='plan_found';primitive+=rp['status']=='plan_found';fixed_macro+=rm['status']=='plan_found'
        verified+=reference_verify(state,goal,rf)
        if rf['status']=='plan_found':
            internal_nodes.append(rf['iterative_search_nodes']);internal_trans.append(rf['iterative_search_transitions'])
    return {'cases':n,'training_max_length':4,'heldout_min_length':min(lengths),'heldout_max_length':max(lengths),
            'iterative_success':full,'primitive_depth1_success':primitive,'fixed_macro_depth1_success':fixed_macro,
            'reference_verified':verified,'episodic_exact_cache_hits':cache_hits,
            'median_internal_nodes':median(internal_nodes),'median_internal_transitions':median(internal_trans)}


def length_scaling(main: Bot):
    rows=[]
    for length in (10,50,100,500,1000,2000,5000):
        state,goal=chain_world(f'scale_{length}',length,0);times=[];last=None
        for _ in range(3):
            t=perf_counter();last=main.plan_symbolic(state,goal,max_steps=1,max_nodes=2,use_macros=False,use_iterations=True,max_iterative_steps=length+1);times.append((perf_counter()-t)*1000)
        rows.append({'length':length,'facts':len(state),'status':last['status'],'primitive_steps':last.get('primitive_steps'),
                     'internal_nodes':last.get('iterative_search_nodes'),'internal_transitions':last.get('iterative_search_transitions'),
                     'median_ms':median(times)})
    return rows


def branch_scaling(main: Bot):
    rows=[]
    for branches in (0,1,5,10):
        state,goal=chain_world(f'branch_{branches}',100,branches);times=[];last=None
        for _ in range(3):
            t=perf_counter();last=main.plan_symbolic(state,goal,max_steps=1,max_nodes=2,use_macros=False,use_iterations=True,max_iterative_steps=150);times.append((perf_counter()-t)*1000)
        rows.append({'branches_per_step':branches,'facts':len(state),'status':last['status'],
                     'internal_nodes':last.get('iterative_search_nodes'),'internal_transitions':last.get('iterative_search_transitions'),
                     'median_ms':median(times)})
    return rows


def same_length_control():
    b=Bot();teach_primitives(b);reports=[]
    for idx in range(3):
        state,goal=chain_world(f'same_{idx}',3)
        reports.append(b.learn_symbolic_iteration(state,goal,max_steps=5,max_nodes=1000)['learning'])
    return {'statuses':[x['status'] for x in reports],'final_lengths':reports[-1].get('lengths'),
            'iterative_skills':len(b.symbolic.iterative_skills())}


def invalidation_eval():
    b=Bot();teach_primitives(b);control=Bot();teach_primitives(control);train_iterative(b,control);before=len(b.symbolic.iterative_skills())
    state=S(F('at','zoe','x'),F('road','x','y'),F('person','zoe'),F('place','x'),F('place','y'))
    after=(state-{F('at','zoe','x')})|{F('at','zoe','y'),F('visited','zoe','y')}
    report=b.observe_symbolic_transition('Mueve a zoe de x a y.',state,after)
    return {'skills_before':before,'counterevidence_status':report['status'],'skills_after':len(b.symbolic.iterative_skills())}


def main():
    frozen=code_hash();t=perf_counter();main=Bot();fixed=Bot();teach_primitives(main);teach_primitives(fixed)
    training,fixed_reports,cache=train_iterative(main,fixed)
    result={'version':'0.3.7','experiment':'variable_length_iterative_skill_induction_from_repeated_operator_plans',
            'code_hash_before':frozen,'training':training,'fixed_macro_same_experience':fixed_reports,
            'iterative_skills':main.symbolic.iterative_skills(),'fixed_macro_count':len(fixed.symbolic.macros()),
            'transfer':transfer_eval(main,fixed,cache),'length_scaling':length_scaling(main),
            'branch_scaling':branch_scaling(main),'same_length_only_control':same_length_control(),
            'dependency_invalidation':invalidation_eval()}
    result['elapsed_s']=perf_counter()-t;result['code_hash_after']=code_hash();result['code_unchanged_during_evaluation']=result['code_hash_after']==frozen
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

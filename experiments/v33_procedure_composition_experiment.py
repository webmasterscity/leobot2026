from __future__ import annotations

import hashlib, json, random, statistics
from pathlib import Path
from time import perf_counter

from leobot.bot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v33_procedure_composition.json'


def code_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(path.read_bytes())
    return h.hexdigest()


def train_family(bot: Bot):
    bot.procedures.min_support=3
    episodes=[
        ('Suma 3 al valor.',(10,),(13,)),('Suma 5 al valor.',(7,),(12,)),('Suma 8 al valor.',(-2,),(6,)),
        ('Añade 4 al valor.',(9,),(13,)),('Añade 6 al valor.',(1,),(7,)),('Añade 9 al valor.',(-4,),(5,)),
        ('Suma 2 a la cantidad.',(3,),(5,)),('Suma 7 a la cantidad.',(10,),(17,)),('Suma 12 a la cantidad.',(-5,),(7,)),
        ('Duplica el valor.',(3,),(6,)),('Duplica el valor.',(7,),(14,)),('Duplica el valor.',(-4,),(-8,)),
        ('Dobla el valor.',(5,),(10,)),('Dobla el valor.',(9,),(18,)),('Dobla el valor.',(-3,),(-6,)),
        ('Duplica el resultado.',(2,),(4,)),('Duplica el resultado.',(11,),(22,)),('Duplica el resultado.',(-5,),(-10,)),
    ]
    reports=[]
    for ep in episodes:reports.append(bot.observe_transition(*ep))
    return episodes,reports


def paraphrase_composition(seed=3301):
    full=Bot(); exact=Bot()
    episodes,_=train_family(full);train_family(exact)
    exact.procedures.semantic_rewrites_enabled=False
    rng=random.Random(seed);scores={'full':0,'exact_surface_control':0};lat=[]
    for _ in range(200):
        x=rng.randint(-10000,10000);n=rng.randint(13,2000);text=f'Añade {n} a la cantidad.';expected=(x+n,)
        t=perf_counter();out=full.execute_transition(text,(x,));lat.append((perf_counter()-t)*1e6)
        scores['full']+=out.get('result')==expected
        scores['exact_surface_control']+=exact.execute_transition(text,(x,)).get('result')==expected
    return {'training_episodes':len(episodes),'learned_rewrites':[[list(a),list(b)] for a,b in sorted(full.procedures.semantic_rewrites)],
            'heldout':200,'scores':scores,'median_us':statistics.median(lat),
            'sample':full.execute_transition('Añade 11 a la cantidad.',(31,))}


def sequence_transfer(seed=3302):
    full=Bot(); noseq=Bot(); norewrite=Bot()
    train_family(full);train_family(noseq);train_family(norewrite)
    noseq.procedures.sequence_composition_enabled=False
    norewrite.procedures.semantic_rewrites_enabled=False
    rng=random.Random(seed)
    scores={'full_forward':0,'full_reverse':0,'no_sequence':0,'no_rewrite':0,'three_step':0}
    lengths=[]
    for _ in range(200):
        x=rng.randint(-5000,5000);a=rng.randint(13,500);b=rng.randint(501,900)
        forward=f'Añade {a} a la cantidad y luego dobla el resultado.'
        reverse=f'Dobla el resultado y luego añade {a} a la cantidad.'
        three=f'Añade {a} a la cantidad y luego dobla el resultado y luego suma {b} al valor.'
        of=full.execute_transition(forward,(x,));orr=full.execute_transition(reverse,(x,));ot=full.execute_transition(three,(x,))
        scores['full_forward']+=of.get('result')==(2*(x+a),)
        scores['full_reverse']+=orr.get('result')==(2*x+a,)
        scores['three_step']+=ot.get('result')==(2*(x+a)+b,)
        scores['no_sequence']+=noseq.execute_transition(forward,(x,)).get('result')==(2*(x+a),)
        scores['no_rewrite']+=norewrite.execute_transition(forward,(x,)).get('result')==(2*(x+a),)
        if ot.get('status')=='executed_plan':lengths.append(len(ot['steps']))
    return {'heldout':200,'scores':scores,'all_three_step_lengths':sorted(set(lengths)),
            'forward_sample':full.execute_transition('Añade 11 a la cantidad y luego dobla el resultado.',(7,)),
            'reverse_sample':full.execute_transition('Dobla el resultado y luego añade 11 a la cantidad.',(7,))}


def counterevidence_withdrawal():
    bot=Bot();train_family(bot)
    before=bot.execute_transition('Añade 11 a la cantidad.',(31,))
    conflict=bot.observe_transition('Añade 10 al valor.',(1,),(100,))
    after=bot.execute_transition('Añade 11 a la cantidad.',(31,))
    return {'before_status':before.get('status'),'before_result':before.get('result'),
            'counterevidence_status':conflict.get('status'),'after_status':after.get('status'),
            'rewrite_survived':(('anade',),('suma',)) in bot.procedures.semantic_rewrites}



def planning_transfer(seed=3303):
    full=Bot();control=Bot()
    for bot in (full,control):
        bot.procedures.min_support=3
        for x in (2,7,-3):bot.observe_transition('Incrementa el valor.',(x,),(x+1,))
    for x in (2,5,-4):full.observe_transition('Duplica el valor.',(x,),(2*x,))
    rng=random.Random(seed);scores={'full':0,'missing_double_control':0};step_counts=[]
    samples=[]
    for _ in range(200):
        start=rng.randint(1,10);cur=start;generated=[]
        for __ in range(rng.randint(2,6)):
            action=rng.choice(('inc','double'));generated.append(action)
            cur=cur+1 if action=='inc' else cur*2
        goal=cur
        fp=full.plan_transition((start,),(goal,),max_steps=6,max_nodes=1000)
        cp=control.plan_transition((start,),(goal,),max_steps=6,max_nodes=1000)
        scores['full']+=fp.get('status')=='plan_found' and fp.get('result')==(goal,)
        scores['missing_double_control']+=cp.get('status')=='plan_found' and cp.get('result')==(goal,)
        if fp.get('status')=='plan_found':step_counts.append(len(fp['steps']))
        if len(samples)<5:samples.append({'start':start,'goal':goal,'generated_path':generated,'found':fp.get('steps',[])})
    tight_full=full.plan_transition((1,),(15,),max_steps=6,max_nodes=1000)
    tight_control=control.plan_transition((1,),(15,),max_steps=6,max_nodes=1000)
    return {'heldout':200,'scores':scores,'median_found_steps':statistics.median(step_counts),
            'tight_goal':{'full':tight_full,'missing_double_control':tight_control},'samples':samples}


def natural_goal_planning(seed=3304):
    full=Bot();no_goal=Bot()
    for bot in (full,no_goal):
        bot.procedures.min_support=3
        for x in (2,7,-3):bot.observe_transition('Incrementa el valor.',(x,),(x+1,))
        for x in (2,5,-4):bot.observe_transition('Duplica el valor.',(x,),(2*x,))
    goal_training=[('Lleva el valor a 2 más que 5.',(7,)),('Lleva el valor a 3 más que 8.',(11,)),('Lleva el valor a 4 más que 10.',(14,))]
    goal_reports=[]
    for text,goal in goal_training:goal_reports.append(full.observe_goal(text,goal))
    rng=random.Random(seed);scores={'natural_full':0,'no_goal_learning':0,'structured_target_reference':0};samples=[]
    for _ in range(200):
        start=rng.randint(1,10);cur=start
        for __ in range(rng.randint(2,6)):
            cur=cur+1 if rng.choice((True,False)) else cur*2
        target=cur;a=rng.randint(-50,50);b=target-a
        text=f'Lleva el valor a {a} más que {b}.'
        fp=full.plan_goal(text,(start,),max_steps=6,max_nodes=1000)
        cp=no_goal.plan_goal(text,(start,),max_steps=6,max_nodes=1000)
        sp=full.plan_transition((start,),(target,),max_steps=6,max_nodes=1000)
        scores['natural_full']+=fp.get('status')=='plan_found' and fp.get('result')==(target,) and fp.get('resolved_goal')==(target,)
        scores['no_goal_learning']+=cp.get('status')=='plan_found'
        scores['structured_target_reference']+=sp.get('status')=='plan_found' and sp.get('result')==(target,)
        if len(samples)<5:samples.append({'text':text,'start':start,'target':target,'status':fp.get('status'),'steps':fp.get('steps',[])})
    return {'goal_training':goal_training,'last_goal_report':goal_reports[-1],'heldout':200,'scores':scores,'samples':samples}

def main():
    frozen=code_hash();started=perf_counter()
    result={'version':'0.3.3','experiment':'semantic_procedure_rewrites_and_sequence_composition',
            'code_hash_before':frozen,
            'paraphrase_composition':paraphrase_composition(),
            'sequence_transfer':sequence_transfer(),
            'planning_transfer':planning_transfer(),
            'natural_goal_planning':natural_goal_planning(),
            'counterevidence_withdrawal':counterevidence_withdrawal()}
    result['code_hash_after']=code_hash();result['code_unchanged_during_evaluation']=result['code_hash_after']==frozen
    result['elapsed_s']=perf_counter()-started
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

from __future__ import annotations
import hashlib,json,random,time,tempfile
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v56_cross_representation_transfer.json'
F=lambda *x:tuple(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def train_numeric_swap(bot):
    bot.procedures.min_support=3;rows=[]
    for before in [(2,9),(5,-3),(11,4)]:
        rows.append(bot.observe_transition('Intercambia los valores.',before,(before[1],before[0])))
    return rows

def sym_episode(bot,i,success=True,missing=None):
    a,b,x,y=f'p{i}a',f'p{i}b',f'o{i}x',f'o{i}y'
    before={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y),F('irrelevant',a,'ok')}
    if missing=='connected':before.discard(F('connected',a,b))
    after=set(before)
    if success:
        after.discard(F('owns',a,x));after.discard(F('owns',b,y));after.add(F('owns',a,y));after.add(F('owns',b,x))
    return bot.observe_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',before,after)

def heldout(bot,n=200,seed=5606):
    rng=random.Random(seed);valid=invalid=0
    for i in range(n):
        a,b,x,y=f'ha{i}',f'hb{i}',f'hx{i}',f'hy{i}'
        state={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
        # Vary irrelevant context to ensure it was not promoted as a precondition.
        if rng.random()<.5:state.add(F('noise',a,str(i)))
        out=bot.execute_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',state);res=set(out.get('result',()))
        valid += out.get('status')=='executed_symbolic_action' and F('owns',a,y) in res and F('owns',b,x) in res
        broken=set(state);broken.discard(F('connected',a,b))
        bad=bot.execute_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',broken)
        invalid += bad.get('status')!='executed_symbolic_action'
    return {'cases':n,'valid_correct':valid,'missing_context_rejected':invalid}


def reverse_transfer():
    treatment=Bot();control=Bot();treatment.symbolic.min_support=3
    for i,(a,b,x,y) in enumerate([('sa','sb','sx1','sy1'),('sc','sd','sx2','sy2'),('se','sf','sx3','sy3')]):
        before={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
        after=(before-{F('owns',a,x),F('owns',b,y)})|{F('owns',a,y),F('owns',b,x)}
        source=treatment.observe_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',before,after)
    rows_t=[];rows_c=[]
    for before in [(2,9),(5,-3)]:
        rows_t.append(treatment.observe_transition('Revierte el par.',before,(before[1],before[0])))
        rows_c.append(control.observe_transition('Revierte el par.',before,(before[1],before[0])))
    ok_t=ok_c=0
    rng=random.Random(5612)
    for _ in range(200):
        a,b=rng.randint(-10000,10000),rng.randint(-10000,10000)
        ok_t += treatment.execute_transition('Revierte el par.',(a,b)).get('result')==(b,a)
        ok_c += control.execute_transition('Revierte el par.',(a,b)).get('result')==(b,a)
    return {'source':source,'treatment_reports':rows_t,'control_reports':rows_c,
            'heldout':200,'treatment_correct':ok_t,'control_correct':ok_c,
            'registered':treatment.procedures.external_permutation_schemas}

def main():
    h0=code_hash();started=time.perf_counter()
    treatment=Bot();control=Bot();fresh_robust=Bot()
    numeric=train_numeric_swap(treatment)
    treatment_rows=[sym_episode(treatment,1),sym_episode(treatment,2),sym_episode(treatment,3,False,'connected')]
    control_rows=[sym_episode(control,1),sym_episode(control,2),sym_episode(control,3,False,'connected')]
    # Same robust target evidence plus one extra positive for the no-prior learner.
    robust_rows=[sym_episode(fresh_robust,1),sym_episode(fresh_robust,2),sym_episode(fresh_robust,3,False,'connected'),sym_episode(fresh_robust,4)]
    persistence={}
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json';treatment.save(p);loaded=Bot.load(p)
        persistence={'schemas':loaded.symbolic.external_permutation_schemas,'heldout':heldout(loaded,40,5610)}
    # Incompatible topology control: the permutation prior must not accelerate move.
    incompatible=Bot();train_numeric_swap(incompatible);incompatible.symbolic.min_support=3
    def move(i,success=True):
        p,s,d=f'mp{i}',f'ms{i}',f'md{i}';st={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)};aft=set(st)
        if success:aft.discard(F('at',p,s));aft.add(F('at',p,d))
        return incompatible.observe_symbolic_transition(f'Mueve a {p} de {s} a {d}.',st,aft)
    inc=[move(1),move(2)]
    out={'version':'V5.6-development','mechanism':'cross_representation_permutation_schema',
         'code_hash_before':h0,'numeric_source':numeric[-1],
         'treatment':{'target_episodes':3,'reports':treatment_rows,'heldout':heldout(treatment)},
         'same_evidence_no_prior':{'target_episodes':3,'reports':control_rows,'heldout':heldout(control)},
         'robust_no_prior_with_extra_positive':{'target_episodes':4,'reports':robust_rows,'heldout':heldout(fresh_robust)},
         'incompatible_topology':{'reports':inc,'operators':incompatible.symbolic.operators()},
         'persistence':persistence,'reverse_symbolic_to_numeric':reverse_transfer()}
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-started)*1000
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

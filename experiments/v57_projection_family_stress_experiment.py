from __future__ import annotations
import hashlib,json,random,time
from pathlib import Path
from leobot import Bot
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v57_projection_family_stress.json'
F=lambda *x:tuple(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def source_examples(n,mapping,tag):
    bot=Bot();bot.procedures.min_support=3
    reports=[]
    rows=[tuple(100*j+i+1 for i in range(n)) for j in range(1,4)]
    for row in rows:
        reports.append(bot.observe_transition(f'Proyecta estructura {tag}.',row,tuple(row[i] for i in mapping)))
    return bot,reports

def symbolic_episode(bot,n,mapping,tag,case,success=True,missing_permit=False):
    vals=[f'entidad{tag}_{case}_{i}' for i in range(n)]
    m=len(mapping);pred=f'rel{tag}'
    before_rel=F(pred,*vals[:m]);after_rel=F(pred,*[vals[i] for i in mapping])
    state={before_rel,F('permitido',vals[-1])}|{F('tipo',v) for v in vals}
    if missing_permit:state.discard(F('permitido',vals[-1]))
    after=set(state)
    if success:
        after.discard(before_rel);after.add(after_rel)
    cue='Opera ' + ' '.join(vals) + '.'
    return bot.observe_symbolic_transition(cue,state,after)

def execute_case(bot,n,mapping,tag,case,permit=True):
    vals=[f'held{tag}_{case}_{i}' for i in range(n)];m=len(mapping);pred=f'rel{tag}'
    before_rel=F(pred,*vals[:m]);after_rel=F(pred,*[vals[i] for i in mapping])
    state={before_rel}|{F('tipo',v) for v in vals}
    if permit:state.add(F('permitido',vals[-1]))
    cue='Opera '+' '.join(vals)+'.';out=bot.execute_symbolic_transition(cue,state);res=set(out.get('result',()))
    return out.get('status')=='executed_symbolic_action' and after_rel in res

def one(mapping,idx):
    n=max(max(mapping)+1,len(mapping)+1)
    n=min(max(n,2),4)
    # Ensure every role exists in the numeric source even when mapping omits it.
    tag=f'{idx}_{n}_{"_".join(map(str,mapping))}'
    source,reps=source_examples(n,mapping,tag)
    control=Bot()
    tr=[symbolic_episode(source,n,mapping,tag,1),symbolic_episode(source,n,mapping,tag,2),symbolic_episode(source,n,mapping,tag,3,False,True)]
    cr=[symbolic_episode(control,n,mapping,tag,1),symbolic_episode(control,n,mapping,tag,2),symbolic_episode(control,n,mapping,tag,3,False,True)]
    valid=sum(execute_case(source,n,mapping,tag,i,True) for i in range(20))
    invalid=sum(not execute_case(source,n,mapping,tag,i,False) for i in range(20))
    control_valid=sum(execute_case(control,n,mapping,tag,i,True) for i in range(5))
    return {'mapping':list(mapping),'input_arity':n,'source_status':reps[-1]['status'],
            'schema':reps[-1].get('cross_modal_learning',{}).get('schema'),
            'target_status':tr[-1]['status'],'target_mode':tr[-1].get('precondition_mode'),
            'control_status':cr[-1]['status'],'valid':valid,'invalid_rejected':invalid,'control_valid':control_valid}

def main():
    h0=code_hash();start=time.perf_counter()
    mappings=[(1,0),(0,2),(2,0),(2,1),(0,3),(3,1),(2,0,1),(1,3,0),(3,2,1),(0,0),(2,2),(3,0,3)]
    rows=[one(m,i) for i,m in enumerate(mappings)]
    out={'version':'V5.7-development','experiment':'generic_projection_family_stress','code_hash_before':h0,
         'families':len(rows),'rows':rows,'all_treatment_learned':all(r['target_status']=='operator_learned' for r in rows),
         'all_controls_pending':all(r['control_status']!='operator_learned' for r in rows),
         'valid_total':sum(r['valid'] for r in rows),'invalid_rejected_total':sum(r['invalid_rejected'] for r in rows),
         'control_valid_total':sum(r['control_valid'] for r in rows)}
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_after']==h0;out['elapsed_ms']=(time.perf_counter()-start)*1000
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

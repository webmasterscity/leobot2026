from __future__ import annotations
import hashlib,json,random,tempfile,time
from pathlib import Path
from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set, symbolic_episode

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v60_meta_dependency.json'
ROLE_SETS=[(0,),(1,),(2,),(0,1),(0,2),(1,2)]
LABELS=['uno','dos','tres','cuatro','cinco','seis']

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def target(row,roles,offset=1):
    if len(roles)==1:
        x=row[roles[0]];return x*x+offset
    a,b=roles;return row[a]*row[b]+offset

def diagnostic_rows(roles):
    base=[2,3,5];rows=[tuple(base)]
    # Every excluded role gets an invariance intervention.
    for k in range(3):
        if k not in roles:
            row=base.copy();row[k]+=7;rows.append(tuple(row))
    # Every included role gets a sensitivity intervention holding the other
    # included roles fixed.
    for k in roles:
        row=base.copy();row[k]+=2;rows.append(tuple(row))
    return rows

def heldout(bot,label,roles,offset=1,n=100):
    rng=random.Random(60000+sum(roles)*101+len(roles)*13+offset);ok=0
    for _ in range(n):
        row=tuple(rng.randint(-50,50) for _ in range(3))
        out=bot.execute_transition(f'Formula {label}.',row)
        ok += out.get('result')==(target(row,roles,offset),)
    return ok

def attempt_cost(detail):
    attempts=detail.get('meta_dependency_attempts')
    if attempts:
        return sum(int(x.get('candidates') or 0) for x in attempts)
    return int(detail.get('candidates') or 0)

def main():
    h0=code_hash();t0=time.perf_counter()
    educated=Bot();fresh=Bot()
    schema=[]
    for i,roles in enumerate(ROLE_SETS):schema.append(teach_role_set(educated,i,roles).get('status'))
    educated.programs.max_candidates=fresh.programs.max_candidates=150
    rows=[]
    for i,roles in enumerate(ROLE_SETS):
        tr=cr=None
        for state in diagnostic_rows(roles):
            y=(target(state,roles),)
            tr=educated.observe_transition(f'Formula {LABELS[i]}.',state,y)
            cr=fresh.observe_transition(f'Formula {LABELS[i]}.',state,y)
        td=tr['reports'][0];cd=cr['reports'][0]
        rows.append({
            'roles':list(roles),'treatment_status':tr.get('status'),'control_status':cr.get('status'),
            'meta_schema':td.get('meta_dependency_schema'),'strategy_order':td.get('meta_dependency_strategy_order'),
            'attempts':td.get('meta_dependency_attempts',[]),'treatment_candidates_total':attempt_cost(td),
            'control_candidates':int(cd.get('candidates') or 0),
            'treatment_heldout':heldout(educated,LABELS[i],roles,1,100),
            'control_heldout':heldout(fresh,LABELS[i],roles,1,20),
        })
    # Cross-mechanism transfer in the direction that V5.8 could not show:
    # a learned numeric dependency certificate lowers the support required for
    # a new symbolic action.  The action name/predicates are never transferred.
    action_t=Bot(); action_c=Bot()
    for state in [(2,10,3),(2,999,3),(4,10,3),(2,10,5),(3,4,8)]:
        action_t.observe_transition('Calcula fuente transversal.',state,(state[0]*state[2]+1,))
    atr=acr=None
    action_train=[('pa','sa','da',True,None),('pb','sb','db',True,None),('px','sx','dx',False,'road')]
    for ep in action_train:
        atr=symbolic_episode(action_t,*ep); acr=symbolic_episode(action_c,*ep)
    action_ok=0
    for i in range(100):
        p,s,d=f'personav{i}',f'origenv{i}',f'destinov{i}'
        state={('at',p,s),('road',s,d),('person',p),('place',s),('place',d)}
        result=action_t.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state)
        action_ok += result.get('status')=='executed_symbolic_action' and ('at',p,d) in set(result.get('result',()))
    cross_mechanism_action={
        'treatment_status':atr.get('status'),'control_status':acr.get('status'),
        'treatment_mode':atr.get('precondition_mode'),'heldout':action_ok,
    }

    # Cross-arity transfer: two independent 3-input schema sources teach only
    # the domain-neutral cardinality prior "two roles tend to matter".  A new
    # 4-input numeric task must use its own interventions to identify *which* two.
    cross_t=Bot(); cross_c=Bot()
    teach_role_set(cross_t,3,(0,1)); teach_role_set(cross_t,4,(0,2))
    cross_t.programs.max_candidates=cross_c.programs.max_candidates=150
    base=[2,3,5,7]; cross_rows=[tuple(base)]
    for k in (1,2):
        q=base.copy(); q[k]+=11; cross_rows.append(tuple(q))
    for k in (0,3):
        q=base.copy(); q[k]+=2; cross_rows.append(tuple(q))
    xtr=xcr=None
    for state in cross_rows:
        y=(state[0]*state[3]+1,)
        xtr=cross_t.observe_transition('Calcula cruce de cuatro.',state,y)
        xcr=cross_c.observe_transition('Calcula cruce de cuatro.',state,y)
    xtd=xtr['reports'][0]; xcd=xcr['reports'][0]
    cross_arity={
        'treatment_status':xtr.get('status'),'control_status':xcr.get('status'),
        'schema':xtd.get('meta_dependency_schema'),'allowed_vars':xtd.get('allowed_vars'),
        'treatment_candidates':int(xtd.get('candidates') or 0),
        'control_candidates':int(xcd.get('candidates') or 0),
        'heldout':sum(cross_t.execute_transition('Calcula cruce de cuatro.',r).get('result')==(r[0]*r[3]+1,)
                      for r in [(11,99,-44,13),(3,-8,100,7),(-4,5,12,9)]),
    }

    # Negative control: all three inputs matter. Every proper role-set prior must
    # be contradicted by at least one intervention, so ordinary synthesis wins.
    educated.programs.max_candidates=5000
    all_rows=[(2,3,5),(4,3,5),(2,7,5),(2,3,9),(5,11,4)]
    incompatible=None
    for state in all_rows:
        incompatible=educated.observe_transition('Suma absolutamente todo.',state,(sum(state),))
    idetail=incompatible['reports'][0]

    # Persistence of the meta-search policy: after reload, the 3:2 structural
    # class should remember that no_library was the successful first choice.
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json';educated.save(p);loaded=Bot.load(p)
        loaded.programs.max_candidates=150
        last=None
        for state in diagnostic_rows((0,1)):
            last=loaded.observe_transition('Formula persistente.',state,(target(state,(0,1),-1),))
        ld=last['reports'][0]
        persistence={
            'status':last.get('status'),'strategy_order':ld.get('meta_dependency_strategy_order'),
            'attempts':ld.get('meta_dependency_attempts',[]),
            'heldout':sum(loaded.execute_transition('Formula persistente.',r).get('result')==(target(r,(0,1),-1),)
                          for r in [(7,11,99),(3,8,-40),(9,2,100)]),
        }
    out={
        'version':'V6.0-meta-dependency','mechanism':'shared_role_relevance_plus_learned_search_policy',
        'code_hash_before':h0,'schema_statuses':schema,'families':rows,
        'treatment_heldout_total':sum(r['treatment_heldout'] for r in rows),
        'control_heldout_total':sum(r['control_heldout'] for r in rows),
        'treatment_candidate_total':sum(r['treatment_candidates_total'] for r in rows),
        'control_candidate_total':sum(r['control_candidates'] for r in rows),
        'dependency_search_stats':educated.procedures.dependency_search_stats,
        'cross_arity':cross_arity,
        'cross_mechanism_action':cross_mechanism_action,
        'incompatible_control':{
            'status':incompatible.get('status'),'allowed_vars':idetail.get('allowed_vars'),
            'meta_dependency_schema':idetail.get('meta_dependency_schema'),
            'heldout':sum(educated.execute_transition('Suma absolutamente todo.',r).get('result')==(sum(r),)
                          for r in [(7,8,9),(10,-2,5),(100,3,-40)]),
        },
        'persistence':persistence,
    }
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-t0)*1000
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

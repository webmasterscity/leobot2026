from __future__ import annotations
import hashlib, json, random, tempfile, time
from itertools import combinations
from pathlib import Path
from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v61_role_cardinality_meta.json'
LABELS=['alfa','beta','gamma','delta','epsilon','zeta']
PAIRS=list(combinations(range(4),2))

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def train_pair_cardinality_prior(bot: Bot):
    reports=[]
    for idx,roles in enumerate(((0,1),(0,2),(1,2))):
        reports.append(teach_role_set(bot,idx+3,roles))
    return reports

def diagnostic_rows(pair):
    base=[2,3,5,7]; out=[tuple(base)]
    for k in range(4):
        if k not in pair:
            r=base.copy(); r[k]+=11; out.append(tuple(r))
    for k in pair:
        r=base.copy(); r[k]+=2; out.append(tuple(r))
    return out

def score(bot,label,pair,n=100):
    rng=random.Random(61000+pair[0]*31+pair[1]*17); ok=0
    for _ in range(n):
        row=tuple(rng.randint(-40,40) for _ in range(4))
        expected=(row[pair[0]]*row[pair[1]]+1,)
        ok += bot.execute_transition(f'Operacion par {label}.',row).get('result')==expected
    return ok

def main():
    h0=code_hash(); t0=time.perf_counter()
    treatment=Bot(); control=Bot()
    schema_reports=train_pair_cardinality_prior(treatment)
    treatment.programs.max_candidates=control.programs.max_candidates=150
    families=[]
    for label,pair in zip(LABELS,PAIRS):
        tr=cr=None
        for row in diagnostic_rows(pair):
            y=(row[pair[0]]*row[pair[1]]+1,)
            tr=treatment.observe_transition(f'Operacion par {label}.',row,y)
            cr=control.observe_transition(f'Operacion par {label}.',row,y)
        td=tr['reports'][0]; cd=cr['reports'][0]
        families.append({
            'pair':list(pair),'treatment_status':tr.get('status'),'control_status':cr.get('status'),
            'schema':td.get('meta_dependency_schema'),'roles':td.get('allowed_vars'),
            'strategy_order':td.get('meta_dependency_strategy_order'),
            'attempts':td.get('meta_dependency_attempts',[]),
            'treatment_candidates':sum(int(x.get('candidates') or 0) for x in td.get('meta_dependency_attempts',[])) or int(td.get('candidates') or 0),
            'control_candidates':int(cd.get('candidates') or 0),
            'treatment_heldout':score(treatment,label,pair,100),
            'control_heldout':score(control,label,pair,20),
        })

    # Negative control: a learned 2-role cardinality must not force a 3-role task.
    treatment.programs.max_candidates=5000
    incompatible=None
    for row in [(2,3,5,7),(4,3,5,7),(2,6,5,7),(2,3,9,7),(2,3,5,11),(5,8,4,9)]:
        incompatible=treatment.observe_transition('Tres roles incompatibles.',row,(row[0]+row[1]*row[3],))
    idetail=incompatible['reports'][0]

    # Persistence: both the cross-arity cardinality prior and the learned 4:2
    # strategy order must survive a restart.
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json'; treatment.save(p); loaded=Bot.load(p)
        loaded.programs.max_candidates=150
        rep=None
        pair=(0,3)
        for row in diagnostic_rows(pair):
            rep=loaded.observe_transition('Operacion persistente.',row,(row[0]*row[3]+1,))
        d=rep['reports'][0]
        persistence={
            'status':rep.get('status'),'schema':d.get('meta_dependency_schema'),
            'strategy_order':d.get('meta_dependency_strategy_order'),
            'attempts':d.get('meta_dependency_attempts',[]),
            'correct':sum(loaded.execute_transition('Operacion persistente.',r).get('result')==(r[0]*r[3]+1,)
                          for r in [(7,100,-4,11),(3,-9,42,8),(-5,2,99,6)]),
        }

    out={
        'version':'V6.1-role-cardinality-meta',
        'mechanism':'cross_arity_role_cardinality_plus_learned_search_order',
        'code_hash_before':h0,
        'schema_statuses':[x.get('status') for x in schema_reports],
        'meta_cardinality_rows':[r for r in treatment.meta_representations.rows() if r.get('kind')=='role_cardinality'],
        'families':families,
        'treatment_heldout_total':sum(x['treatment_heldout'] for x in families),
        'control_heldout_total':sum(x['control_heldout'] for x in families),
        'treatment_candidate_total':sum(x['treatment_candidates'] for x in families),
        'control_candidate_total':sum(x['control_candidates'] for x in families),
        'dependency_search_stats':treatment.procedures.dependency_search_stats,
        'incompatible_control':{
            'status':incompatible.get('status'),'allowed_vars':idetail.get('allowed_vars'),
            'meta_dependency_schema':idetail.get('meta_dependency_schema'),
            'correct':sum(treatment.execute_transition('Tres roles incompatibles.',r).get('result')==(r[0]+r[1]*r[3],)
                          for r in [(7,4,999,5),(2,8,-3,6),(10,-2,77,3)]),
        },
        'persistence':persistence,
    }
    out['code_hash_after']=code_hash(); out['code_unchanged']=out['code_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-t0)*1000
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

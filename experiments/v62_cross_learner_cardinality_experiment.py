from __future__ import annotations
import hashlib, json, tempfile, time
from pathlib import Path
from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v62_cross_learner_cardinality.json'
F=lambda *x: tuple(x)

def code_hash():
    h=hashlib.sha256()
    for base in (ROOT/'leobot', ROOT/'tests'):
        for p in sorted(base.glob('*.py')):
            h.update(str(p.relative_to(ROOT)).encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def train_prior(bot):
    reports=[]
    for idx,roles in enumerate(((0,1),(0,2),(1,2)),start=3):
        reports.append(teach_role_set(bot,idx,roles))
    return reports

def episode(bot,p,t,s,d,success=True,missing=None):
    before={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),F('person',p),F('place',s),F('place',d)}
    if missing=='road':before.discard(F('road',s,d))
    after=set(before)
    if success:
        after.discard(F('at',p,s));after.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',before,after)

def main():
    before_hash=code_hash(); treatment=Bot(); control=Bot(); train_prior(treatment)
    train=[]
    for vals in [('personauno','tokenuno','origenuno','destinouno'),('personados','tokendos','origendos','destinodos')]:
        train.append({'treatment':episode(treatment,*vals),'control':episode(control,*vals)})
    tr=episode(treatment,'personatres','tokentres','origentres','destinotres',False,'road')
    cr=episode(control,'personatres','tokentres','origentres','destinotres',False,'road')
    held=0; false_accept=0
    t0=time.perf_counter_ns()
    for i in range(200):
        p,t,s,d=f'persona{i+100}',f'token{i+100}',f'origen{i+100}',f'destino{i+100}'
        state={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),F('person',p),F('place',s),F('place',d)}
        out=treatment.execute_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',state)
        if out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',())): held+=1
        bad=set(state);bad.discard(F('road',s,d))
        out_bad=treatment.execute_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',bad)
        if out_bad.get('status')=='executed_symbolic_action': false_accept+=1
    elapsed=(time.perf_counter_ns()-t0)/1e6
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'state.json';treatment.save(path);loaded=Bot.load(path)
        persisted='card:2' in loaded.symbolic.external_role_cardinalities
        probe=loaded.execute_symbolic_transition('Transporta a personaz con tokenz de origenz a destinoz.',
            {F('at','personaz','origenz'),F('road','origenz','destinoz'),F('authorized','personaz','tokenz'),F('token','tokenz'),F('person','personaz'),F('place','origenz'),F('place','destinoz')})
        restart_ok=probe.get('status')=='executed_symbolic_action' and F('at','personaz','destinoz') in set(probe.get('result',()))
    after_hash=code_hash()
    report={
        'experiment':'V6.2 cross-learner cardinality across unseen arity',
        'code_hash_before':before_hash,'code_hash_after':after_hash,'code_unchanged':before_hash==after_hash,
        'prior_sources':len(treatment.symbolic.external_role_cardinalities.get('card:2',{}).get('sources',{})),
        'treatment_final':tr,'control_final':cr,
        'heldout_correct':held,'heldout_total':200,'false_accepts_without_required_road':false_accept,
        'heldout_elapsed_ms':elapsed,'persisted':persisted,'restart_ok':restart_ok,
        'interpretation':'The source contributes only k=2. Target action effects identify roles 0 and 3; target failures identify road as a precondition.'
    }
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

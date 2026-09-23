from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time

from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set
from tests.test_v63 import train_chain_prior, chain_transition

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v65_meta_controller.json'
F=lambda *x:tuple(x)


def code_hash():
    h=hashlib.sha256()
    for base in (ROOT/'leobot',ROOT/'tests'):
        for p in sorted(base.rglob('*.py')):
            h.update(str(p.relative_to(ROOT)).encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def train_pair_cardinality_prior(bot: Bot):
    for idx,roles in enumerate(((0,1),(0,2),(1,2))):
        rep=teach_role_set(bot,idx+3,roles)
        assert rep['status']=='schema_learned',rep


def numeric_seed(bot: Bot):
    bot.programs.max_candidates=150
    rows=[(2,3,5,7),(2,10,5,7),(2,3,12,7),(4,3,5,7),(2,3,5,9)]
    rep=None
    for row in rows:
        rep=bot.observe_transition('Semilla numerica transversal.',row,(row[0]*row[3]+1,))
    assert rep['status']=='procedure_learned',rep
    return rep


def transport_episode(bot: Bot,i:int,success=True,missing=None):
    p,t,s,d=f'persona{i}',f'token{i}',f'origen{i}',f'destino{i}'
    before={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),
            F('person',p),F('place',s),F('place',d)}
    if missing=='road': before.discard(F('road',s,d))
    after=set(before)
    if success:
        after.discard(F('at',p,s)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',before,after)


def eval_transport(bot: Bot,count=200):
    ok=0; false_accept=0
    for i in range(1000,1000+count):
        p,t,s,d=f'persona{i}',f'token{i}',f'origen{i}',f'destino{i}'
        state={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),F('person',p),F('place',s),F('place',d)}
        out=bot.execute_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',state)
        if out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',())):
            ok+=1
        bad=set(state);bad.discard(F('road',s,d))
        out2=bot.execute_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',bad)
        if out2.get('status')=='executed_symbolic_action':
            false_accept+=1
    return {'correct':ok,'total':count,'false_accept_without_road':false_accept}


def active_acquisition():
    treatment=Bot(); control=Bot()
    fn=lambda x:x[0]*x[3]+1
    base=[(2,3,5,7),(4,6,10,14),(6,9,15,21)]
    for b in (treatment,control):
        train_pair_cardinality_prior(b); b.programs.max_candidates=1
        for row in base:
            b.observe_transition('Explora cuatro.',row,(fn(row),))
    probes=[]
    for _ in range(4):
        p=treatment.suggest_transition_probe('Explora cuatro.')
        assert p['status']=='evidence_probe',p
        probes.append({'role':p['vary_role'],'candidate_count':len(p['candidate_role_sets']),'before':list(p['before'])})
        row=tuple(p['before']);treatment.observe_transition('Explora cuatro.',row,(fn(row),))
    passive=[(8,12,20,28),(10,15,25,35),(12,18,30,42),(14,21,35,49)]
    for row in passive:
        control.observe_transition('Explora cuatro.',row,(fn(row),))
    tspace=treatment.suggest_transition_probe('Explora cuatro.')
    cspace=control.suggest_transition_probe('Explora cuatro.')
    for b in (treatment,control):b.programs.max_candidates=150
    finals=[]
    for b in (treatment,control):
        last=b.procedures.sessions['explora cuatro']['supports'][-1]
        finals.append(b.observe_transition('Explora cuatro.',tuple(last['before']),tuple(last['after'])))
    held=0
    if finals[0]['status']=='procedure_learned':
        for i in range(200):
            row=(i+2,1000+i,-300-i,2*i+7)
            out=treatment.execute_transition('Explora cuatro.',row)
            held += int(out.get('status')=='executed' and out.get('result')==(fn(row),))
    return {
        'initial_candidate_sets':6,
        'active_probes':probes,
        'treatment_final_version_space':tspace.get('candidate_role_sets'),
        'control_final_version_space_size':len(cspace.get('candidate_role_sets',[])),
        'treatment_status':finals[0]['status'],'control_status':finals[1]['status'],
        'treatment_roles':finals[0].get('reports',[{}])[0].get('meta_dependency_roles'),
        'heldout_correct':held,'heldout_total':200,
    }


def main():
    before=code_hash(); started=time.perf_counter()
    treatment=Bot(); control=Bot()
    for b in (treatment,control):
        train_pair_cardinality_prior(b); numeric_seed(b)
    control.symbolic.meta_controller=None
    for b in (treatment,control):
        transport_episode(b,1);transport_episode(b,2)
    tr=transport_episode(treatment,3,False,'road');cr=transport_episode(control,3,False,'road')
    t_attempts=len(tr.get('meta_controller_representation_attempts',()))
    c_attempts=len(cr.get('meta_controller_representation_attempts',()))
    cross={
        'treatment_status':tr['status'],'control_status':cr['status'],
        'treatment_mode':tr.get('precondition_mode'),'control_mode':cr.get('precondition_mode'),
        'treatment_representation_attempts':t_attempts,'control_representation_attempts':c_attempts,
        'attempt_reduction_pct':100.0*(c_attempts-t_attempts)/c_attempts,
        'treatment_route':tr.get('meta_controller_route'),
        'treatment_heldout':eval_transport(treatment,200),
        'control_heldout':eval_transport(control,200),
    }

    # Safety fallback: bias learned from cardinality must not suppress topology.
    fallback=Bot();train_pair_cardinality_prior(fallback);numeric_seed(fallback);train_chain_prior(fallback)
    chain_transition(fallback,1);fr=chain_transition(fallback,2)
    fallback_held=0
    for i in range(300,400):
        p,o,d=f'persona{i}',f'origen{i}',f'destino{i}'
        state={F('at',p,o),F('road',o,d),F('auth',p,d),F('person',p),F('place',o),F('place',d)}
        out=fallback.execute_symbolic_transition(f'Mueve {p} de {o} a {d}.',state)
        fallback_held+=int(out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',())))
    safety={'status':fr['status'],'mode':fr.get('precondition_mode'),
            'attempts':fr.get('meta_controller_representation_attempts'),
            'heldout_correct':fallback_held,'heldout_total':100}

    active=active_acquisition()

    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'state.json'; treatment.save(path); loaded=Bot.load(path)
        persistence={'observations_before':treatment.meta_controller.observations,
                     'observations_after':loaded.meta_controller.observations,
                     'shared_identity':loaded.procedures.meta_controller is loaded.meta_controller and loaded.symbolic.meta_controller is loaded.meta_controller}

    after=code_hash()
    result={'version':'V6.5 MetaController','code_hash_before':before,'code_hash_after':after,
            'code_unchanged':before==after,'elapsed_s':time.perf_counter()-started,
            'cross_learner_routing':cross,'safety_fallback':safety,
            'active_evidence':active,'persistence':persistence}
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

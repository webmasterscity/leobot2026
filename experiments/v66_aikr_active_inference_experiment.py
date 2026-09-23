from __future__ import annotations
import hashlib,json,time
from pathlib import Path
from leobot import Bot
from leobot.metacontrol import MetaController
from experiments.v65_meta_controller_experiment import train_pair_cardinality_prior

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v66_aikr_active_inference.json'


def code_hash():
    h=hashlib.sha256()
    for base in (ROOT/'leobot',ROOT/'tests'):
        for p in sorted(base.rglob('*.py')):
            h.update(str(p.relative_to(ROOT)).encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def regime_shift():
    m=MetaController(); f=(0.5,0.5)
    for _ in range(20):
        m.observe('scheduler',f,'A',success=True,cost=1)
        m.observe('scheduler',f,'B',success=False,cost=1)
    treatment_correct=legacy_correct=0; switch_t=None; switch_l=None; trace=[]
    for step in range(1,21):
        tr=m.rank('scheduler',f,['A','B'])['order'][0]
        sig=m.signature(f); lg=m._exact_order(m.exact['scheduler'][sig],['A','B'])[0]
        treatment_correct += int(tr=='B'); legacy_correct += int(lg=='B')
        if tr=='B' and switch_t is None:switch_t=step
        if lg=='B' and switch_l is None:switch_l=step
        trace.append({'step':step,'aikr_choice':tr,'lifetime_choice':lg})
        m.observe('scheduler',f,'A',success=False,cost=1)
        m.observe('scheduler',f,'B',success=True,cost=1)
    return {'post_shift_rounds':20,'aikr_correct_choices':treatment_correct,
            'lifetime_correct_choices':legacy_correct,'aikr_switch_round':switch_t,
            'lifetime_switch_round':switch_l,'trace':trace,
            'final_budgets':m.budget_snapshot('scheduler',f)}


def active_evidence():
    actual_cost={0:10.0,1:1.0,2:1.0,3:1.0}
    fn=lambda x:x[1]+x[2]
    base=[(2,3,5,7),(4,6,10,14),(6,9,15,21)]
    treatment=Bot(); control=Bot()
    for b in (treatment,control):
        train_pair_cardinality_prior(b); b.programs.max_candidates=1
        for row in base:b.observe_transition('Explora cuatro.',row,(fn(row),))
        b.programs.max_candidates=150
    tp=treatment.suggest_transition_probe('Explora cuatro.',role_costs=actual_cost)
    cp=control.suggest_transition_probe('Explora cuatro.')
    tr=treatment.observe_transition('Explora cuatro.',tuple(tp['before']),(fn(tuple(tp['before'])),))
    cr=control.observe_transition('Explora cuatro.',tuple(cp['before']),(fn(tuple(cp['before'])),))
    held_t=held_c=0
    for i in range(200):
        row=(i+1,3*i+2,7*i+4,11*i+8)
        held_t+=int(treatment.execute_transition('Explora cuatro.',row).get('result')==(fn(row),))
        held_c+=int(control.execute_transition('Explora cuatro.',row).get('result')==(fn(row),))
    tc=actual_cost[tp['vary_role']];cc=actual_cost[cp['vary_role']]
    return {
        'treatment':{'chosen_role':tp['vary_role'],'actual_cost':tc,'learn_status':tr['status'],
                     'heldout_correct':held_t,'heldout_total':200,
                     'epistemic_selection':tp.get('epistemic_selection')},
        'control_ignores_cost':{'chosen_role':cp['vary_role'],'actual_cost':cc,'learn_status':cr['status'],
                                'heldout_correct':held_c,'heldout_total':200},
        'cost_reduction_pct':100.0*(cc-tc)/cc,
    }


def main():
    before=code_hash();start=time.perf_counter()
    result={'version':'V6.6 AIKR + epistemic acquisition','code_hash_before':before,
            'regime_shift':regime_shift(),'active_evidence':active_evidence()}
    result['code_hash_after']=code_hash();result['code_unchanged']=result['code_hash_before']==result['code_hash_after']
    result['elapsed_s']=time.perf_counter()-start
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

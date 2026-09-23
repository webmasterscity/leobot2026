"""F-15 development on untouched NLI groups with typed relational programs."""
from __future__ import annotations

import json
import resource
import time
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.f14_counterfactual_inventory import read,FILES
from experiments.f14_revision_baselines import LABELS,groups,pairs,prior,score,unpaired
from experiments.f14_revision_dev import episodes,assess
from experiments.f14_typed_edit_learner import TypedEditLearner
from experiments.f15_edit_motif_inventory import motif
from experiments.f15_relation_learner import RelationalEditLearner


ROOT=Path(__file__).resolve().parents[1]


def untouched_groups(tree):
    original,meta_o=read(FILES[0]);revised,meta_r=read(FILES[1])
    inventory=json.loads((ROOT/'results_v3'/'f14_counterfactual_inventory.json').read_text())
    if (meta_o['sha256']!=inventory['sources'][FILES[0]]['sha256'] or
            meta_r['sha256']!=inventory['sources'][FILES[1]]['sha256']):
        raise RuntimeError('Fuente NLI alterada')
    ordered=sorted(range(len(original)),key=lambda i:(sha256(
        (tree+':F-14:nli:'+str(i)).encode()).hexdigest(),i))
    return [(i,[original[i],*revised[4*i:4*i+4]]) for i in ordered[1400:]]


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    train,validation,old_dev,untouched=groups(tree)
    held=untouched_groups(tree)
    if len(held)!=untouched or len(set(i for i,_ in held)&set(i for i,_ in old_dev)):
        raise RuntimeError('Reserva F-15 no independiente')
    base=json.loads((ROOT/'results_v3'/'f14_margin_diagnostic.json').read_text())
    base_families=base['best_raw_families']
    fit=episodes(train);valid=episodes(validation);new=episodes(held)
    model=RelationalEditLearner(LABELS,base_families)
    fitted=model.fit(fit)
    selected=model.select_relation(valid,score)
    treatment=assess(model,new)
    minimal=[(group,before,after,side) for group,before,after,side in new
             if motif(before,after) is not None]
    treatment_minimal=assess(model,minimal) if minimal else None
    raw_program=selected['best_raw_program']
    model.program=raw_program
    raw_treatment=assess(model,new)
    raw_minimal=assess(model,minimal) if minimal else None
    model.program=selected['program']
    baseline=TypedEditLearner(LABELS);base_fit=baseline.fit(fit)
    baseline.program={'families':list(base_families),'margin':0.0}
    old_result=assess(baseline,new)
    old_minimal=assess(baseline,minimal) if minimal else None
    prior_result=prior(train,held)
    unpaired_result,_=unpaired(train,held)
    gate=(selected['program'] is not None and
          treatment['macro_accuracy']>=0.65 and
          (treatment['precision'] or 0)>=0.8 and treatment['coverage']>=0.5 and
          treatment['macro_accuracy']>=old_result['macro_accuracy']+0.05 and
          treatment['macro_accuracy']>=prior_result['macro_accuracy']+0.10 and
          treatment['same_label']['correct']/max(1,treatment['same_label']['total'])>=0.9 and
          treatment_minimal is not None and
          (treatment_minimal['precision'] or 0)>=0.8 and
          treatment_minimal['coverage']>=0.5 and
          treatment['p95_ms']<=10)
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'preregistration':'prereg/F-15-igualdad-relacional-ediciones.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'fit_groups':len(train),'validation_groups':len(validation),
            'old_development_excluded':len(old_dev),'untouched_groups':len(held),
            'base_families_from_F14_validation':base_families,
            'fit':fitted,'selection':selected,'treatment':treatment,
            'treatment_minimal':treatment_minimal,
            'raw_diagnostic':raw_treatment,'raw_minimal_diagnostic':raw_minimal,
            'f14_fit':base_fit,'f14_raw_baseline':old_result,
            'f14_raw_minimal':old_minimal,'prior':prior_result,
            'unpaired':unpaired_result,
            'preliminary_gate_passed':bool(gate and unchanged),
            'three_orders_and_adversarial_controls':'pending_if_preliminary_passes',
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f15_relation_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('selection','fit','treatment_minimal',
                                     'raw_minimal_diagnostic','f14_raw_minimal')}
                     |{'selection':{k:v for k,v in selected.items()
                                     if k!='best_raw_validation'},
                       'minimal':{'treatment':treatment_minimal,
                                  'raw':raw_minimal,'f14':old_minimal}},
                     ensure_ascii=False))


if __name__=='__main__':main()

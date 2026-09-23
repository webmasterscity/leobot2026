"""Post-gate F-16 diagnosis of unpromoted relational recommendations."""
from __future__ import annotations

import json
import resource
import time
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.f16_defeasible_baselines import FAMILIES,load
from experiments.f16_transfer_dev import adapt,assess
from experiments.f16_update_learner import UpdateLearner


ROOT=Path(__file__).resolve().parents[1]


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    prior_result=json.loads((ROOT/'results_v3'/'f16_transfer_dev.json').read_text())
    if prior_result['transfer_gate_passed'] or prior_result['engine_tree']!=tree:
        raise RuntimeError('Este diagnóstico requiere una puerta fallida')
    inventory=json.loads((ROOT/'results_v3'/'f16_defeasible_inventory.json').read_text())
    results={}
    for family in FAMILIES:
        train,_,development,_=load(
            family,tree,inventory['files'][family+'/train.jsonl']['sha256'])
        model=UpdateLearner();model.fit(adapt(train,family))
        best=prior_result['families'][family]['stages'][-1][
            'educated_selection']['best_raw_program']
        model.program=best
        raw=assess(model,adapt(development,family))
        if family!='defeasible-social':
            model.program={'comparison':['claim','overlap_binary'],
                           'weight':2.0,'margin':0.0}
            source=assess(model,adapt(development,family))
        else:source=None
        results[family]={'best_raw_program':best,'best_raw':raw,
                         'source_prior_program':source,
                         'lexical_control':prior_result['families'][family][
                             'lexical_control']}
    output={'kind':'diagnostic_not_promotion',
            'preregistration':'prereg/F-16-transferencia-igualdad-actualizaciones.md',
            'engine_tree':tree,'families':results,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f16_raw_diagnostic.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({name:{'best_raw_macro':row['best_raw']['macro_accuracy'],
                            'source_prior_macro':row['source_prior_program'][
                                'macro_accuracy'] if row['source_prior_program'] else None,
                            'lexical_macro':row['lexical_control']['macro_accuracy']}
                     for name,row in results.items()},ensure_ascii=False))


if __name__=='__main__':main()

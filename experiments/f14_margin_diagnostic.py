"""Post-gate F-14 diagnosis: raw edit evidence, never promotion evidence."""
from __future__ import annotations

import json
import resource
import time
from itertools import combinations
from pathlib import Path

from experiments.f14_revision_baselines import LABELS,groups,pairs,score
from experiments.f14_typed_edit_learner import FAMILIES,TypedEditLearner
from experiments.f7_typed_sequences_dev import git


ROOT=Path(__file__).resolve().parents[1]


def prepared(model,groups_):
    return [(before,after,side,*model._family_scores(before,after,side))
            for _,_,_,before,after,side in pairs(groups_)]


def evaluate(model,rows,families,margin):
    return score((before,after,side,
                  (ranked[0][1] if ranked[0][0]-ranked[1][0]>margin else None))
                 for before,after,side,prior,features in rows
                 for ranked in (model._rank(prior,features,families),))


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    official=json.loads((ROOT/'results_v3'/'f14_revision_dev.json').read_text())
    if official['preliminary_gate_passed'] or official['engine_tree']!=tree:
        raise RuntimeError('Este diagnóstico solo sigue a una puerta fallida')
    train,validation,development,_=groups(tree)
    model=TypedEditLearner(LABELS)
    model.fit([(group,before,after,side)
               for group,_,_,before,after,side in pairs(train)])
    val=prepared(model,validation);dev=prepared(model,development)
    best=None
    for width in range(1,len(FAMILIES)+1):
        for family_set in combinations(FAMILIES,width):
            metric=evaluate(model,val,family_set,0.0)
            rank=(-metric['macro_accuracy'],-(metric['precision'] or 0),
                  width,family_set)
            if best is None or rank<best[0]:best=(rank,family_set,metric)
    families=best[1]
    margins=[]
    for threshold in (0.0,0.5,1.0,2.0,3.0,4.0):
        margins.append({'threshold':threshold,
                        'development':evaluate(model,dev,families,threshold)})
    output={'kind':'diagnostic_not_promotion',
            'preregistration':'prereg/F-14-revision-contrafactual-tipada.md',
            'engine_tree':tree,'best_raw_families':list(families),
            'validation':best[2],'margins':margins,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f14_margin_diagnostic.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'best_raw_families':output['best_raw_families'],
                      'validation_macro':best[2]['macro_accuracy'],
                      'development_macro':margins[0]['development']['macro_accuracy'],
                      'development_precision':[
                          (row['threshold'],row['development']['precision'],
                           row['development']['coverage']) for row in margins]},
                     ensure_ascii=False))


if __name__=='__main__':main()

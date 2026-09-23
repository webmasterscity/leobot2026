"""Read-only check: row-wise versus group-wise verification on human revisions."""
from __future__ import annotations

import json
import resource
import time
from hashlib import sha256
from itertools import combinations
from pathlib import Path

from experiments.f14_revision_baselines import LABELS,groups,pairs,score
from experiments.f14_typed_edit_learner import FAMILIES,TypedEditLearner
from experiments.f7_typed_sequences_dev import git


ROOT=Path(__file__).resolve().parents[1]


def prepare(model,episodes):
    return [(before,after,side,*model._family_scores(before,after,side))
            for _,before,after,side in episodes]


def measure(model,rows,families):
    return score((before,after,side,ranked[0][1]
                  if ranked[0][0]>ranked[1][0] else None)
                 for before,after,side,base,parts in rows
                 for ranked in (model._rank(base,parts,families),))


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    train,_,development,_=groups(tree)
    fit=[];row_validation=[]
    for group,states in train:
        edges=[]
        for i,before in enumerate(states):
            for j,after in enumerate(states):
                if i==j:continue
                side=tuple(key for key in ('sentence1','sentence2')
                           if before[key]!=after[key])
                digest=sha256((tree+':F17:row:'+str(group)+':'+str(i)+':'+str(j))
                              .encode()).hexdigest()
                edges.append((digest,(group,before,after,side)))
        edges.sort(key=lambda item:item[0])
        fit.extend(value for _,value in edges[:16])
        row_validation.extend(value for _,value in edges[16:])
    held=[(group,before,after,side) for group,_,_,before,after,side
          in pairs(development)]
    model=TypedEditLearner(LABELS);fitted=model.fit(fit)
    val_prepared=prepare(model,row_validation)
    held_prepared=prepare(model,held)
    best=None
    for width in range(1,len(FAMILIES)+1):
        for family_set in combinations(FAMILIES,width):
            metric=measure(model,val_prepared,family_set)
            rank=(-metric['macro_accuracy'],-(metric['precision'] or 0),
                  width,family_set)
            if best is None or rank<best[0]:best=(rank,family_set,metric)
    held_result=measure(model,held_prepared,best[1])
    grouped=json.loads((ROOT/'results_v3'/'f14_margin_diagnostic.json').read_text())
    output={'kind':'architecture_feasibility_only','engine_tree':tree,
            'row_fit_edges':len(fit),'row_validation_edges':len(row_validation),
            'heldout_groups':len(development),'fit':fitted,
            'row_selected_families':list(best[1]),
            'row_validation':best[2],'row_selected_on_new_groups':held_result,
            'group_selected_families':grouped['best_raw_families'],
            'group_validation':grouped['validation'],
            'group_selected_on_new_groups':grouped['margins'][0]['development'],
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f17_verifier_leakage_probe.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'row_selected_families':output['row_selected_families'],
         'row_validation_macro':best[2]['macro_accuracy'],
         'row_new_groups_macro':held_result['macro_accuracy'],
         'group_validation_macro':grouped['validation']['macro_accuracy'],
         'group_new_groups_macro':grouped['margins'][0]['development']['macro_accuracy'],
         'cpu_total_s':output['cpu_total_s']},ensure_ascii=False))


if __name__=='__main__':main()

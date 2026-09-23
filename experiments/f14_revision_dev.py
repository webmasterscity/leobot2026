"""F-14 preregistered development: typed edits versus equal-information controls."""
from __future__ import annotations

import json
import resource
import statistics
import time
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.f14_revision_baselines import (
    LABELS,groups,pairs,prior,score,unpaired,
)
from experiments.f14_typed_edit_learner import TypedEditLearner


ROOT=Path(__file__).resolve().parents[1]


def episodes(groups_):
    return [(group,before,after,side)
            for group,_,_,before,after,side in pairs(groups_)]


def assess(model,rows):
    measurements=[];times=[]
    for _,before,after,side in rows:
        tick=time.perf_counter()
        prediction=model.predict(before,after,side)
        times.append((time.perf_counter()-tick)*1000)
        measurements.append((before,after,side,prediction))
    values=score(measurements);times.sort()
    values.update(p50_ms=round(statistics.median(times),5),
                  p95_ms=round(times[(95*len(times)+99)//100-1],5))
    return values


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    train,validation,development,untouched=groups(tree)
    valid_edges=episodes(validation);dev_edges=episodes(development)
    stages=[];model=None
    for count in (100,250,500,1000):
        learner=TypedEditLearner(LABELS)
        fitted=learner.fit(episodes(train[:count]))
        selected=learner.select_program(valid_edges,score)
        stages.append({'groups':count,'fit':fitted,'selection':selected})
        if count==1000:model=learner
    tick=time.process_time();prior_dev=prior(train,development)
    prior_cpu=time.process_time()-tick
    tick=time.process_time();unpaired_dev,unpaired_profile=unpaired(train,development)
    unpaired_cpu=time.process_time()-tick
    treatment=assess(model,dev_edges)
    gate=(model.program is not None and
          treatment['macro_accuracy']>=0.55 and
          treatment['macro_accuracy']>=prior_dev['macro_accuracy']+0.10 and
          treatment['macro_accuracy']>=unpaired_dev['macro_accuracy']+0.10 and
          (treatment['precision'] or 0)>=0.8 and
          treatment['coverage']>=0.5 and
          treatment['same_label']['correct']/max(1,treatment['same_label']['total'])>=0.6 and
          treatment['p95_ms']<=10)
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'preregistration':'prereg/F-14-revision-contrafactual-tipada.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'train_groups':len(train),'validation_groups':len(validation),
            'development_groups':len(development),
            'unused_train_groups':untouched,'train_directed_pairs':len(episodes(train)),
            'stages':stages,'treatment_development':treatment,
            'prior_development':prior_dev,'unpaired_development':unpaired_dev,
            'unpaired_profile':unpaired_profile,
            'prior_cpu_s':round(prior_cpu,6),
            'unpaired_cpu_s':round(unpaired_cpu,6),
            'preliminary_gate_passed':bool(gate and unchanged),
            'adversarial_restart_transfer':'pending_if_preliminary_passes',
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f14_revision_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key!='stages'}|{'stages':[(item['groups'],item['selection']['status'],
                                                  item['selection']['program'])
                                                 for item in stages]},ensure_ascii=False))


if __name__=='__main__':main()

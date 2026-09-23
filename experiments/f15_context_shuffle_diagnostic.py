"""Post-gate F-15 check: destroy only cross-field equality, keep edit features."""
from __future__ import annotations

import json
import resource
import time
from collections import defaultdict
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.f14_revision_baselines import LABELS,groups,score
from experiments.f14_revision_dev import episodes
from experiments.f15_relation_dev import untouched_groups
from experiments.f15_relation_learner import RelationalEditLearner,compare


ROOT=Path(__file__).resolve().parents[1]


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    result=json.loads((ROOT/'results_v3'/'f15_relation_dev.json').read_text())
    if result['preliminary_gate_passed'] or result['engine_tree']!=tree:
        raise RuntimeError('Solo diagnosticar F-15 fallido con motor intacto')
    train,_,_,_=groups(tree);held=episodes(untouched_groups(tree))
    spec=result['selection']['best_raw_program']
    model=RelationalEditLearner(LABELS,spec['base_families'])
    model.fit(episodes(train))
    buckets=defaultdict(list)
    for index,(group,before,after,side) in enumerate(held):
        if len(side)==1:
            buckets[(before['gold_label'],tuple(side))].append(index)
    donor={}
    for indices in buckets.values():
        for pos,index in enumerate(indices):
            candidate=indices[(pos+1)%len(indices)]
            if held[candidate][0]==held[index][0]:
                candidate=next((other for other in indices
                                if held[other][0]!=held[index][0]),candidate)
            donor[index]=candidate
    original=[];shuffled=[];baseline=[];changed=0
    descriptor=tuple(spec['comparison']);weight=spec['weight']
    for index,donor_index in donor.items():
        _,before,after,side=held[index]
        _,donor_before,donor_after,_=held[donor_index]
        other='sentence2' if side[0]=='sentence1' else 'sentence1'
        changed_before={**before,other:donor_before[other]}
        changed_after={**after,other:donor_after[other]}
        true_value=compare(descriptor,before,after,model.frequent)
        shuffled_value=compare(descriptor,changed_before,changed_after,
                               model.frequent)
        changed+=true_value!=shuffled_value
        prior,parts=model._family_scores(before,after,side)
        base_order=model._rank(prior,parts,spec['base_families'])
        true_order=model._rank_relation(before,after,side,prior,parts,
                                        descriptor,weight,true_value)
        shuf_order=model._rank_relation(before,after,side,prior,parts,
                                        descriptor,weight,shuffled_value)
        base=base_order[0][1]
        true=true_order[0][1]
        shuf=shuf_order[0][1]
        original.append((before,after,side,true))
        shuffled.append((before,after,side,shuf))
        baseline.append((before,after,side,base))
    output={'kind':'diagnostic_not_promotion',
            'preregistration':'prereg/F-15-igualdad-relacional-ediciones.md',
            'engine_tree':tree,'single_side_edges':len(donor),
            'relation_value_changed_by_shuffle':changed,
            'treatment':score(original),'context_shuffled':score(shuffled),
            'edit_only':score(baseline),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f15_context_shuffle_diagnostic.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key in ('single_side_edges','relation_value_changed_by_shuffle',
                                 'treatment','context_shuffled','edit_only')},
                     ensure_ascii=False))


if __name__=='__main__':main()

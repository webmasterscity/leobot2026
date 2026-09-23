"""Read-only test of cross-sentence equality in human minimal edits."""
from __future__ import annotations

import json
import random
import resource
import time
from collections import Counter,defaultdict
from pathlib import Path

from experiments.f14_revision_baselines import groups
from experiments.f14_typed_edit_learner import _tokens
from experiments.f15_edit_motif_inventory import motif,original_edges
from experiments.f7_typed_sequences_dev import git


ROOT=Path(__file__).resolve().parents[1]


def keys(before,after,frequent):
    exact=motif(before,after)
    if exact is None:return None
    old,side,kind,removed,added=exact
    base=(old,side,kind,min(3,len(removed)),min(3,len(added)))
    other='sentence2' if side=='sentence1' else 'sentence1'
    context=set(_tokens(before[other]))-frequent
    removed_info={token for token in removed if token not in frequent}
    added_info={token for token in added if token not in frequent}
    relation=base+(bool(removed_info & context),bool(added_info & context),
                   bool(removed_info),bool(added_info))
    return {'structural':base,'cross_sentence_equality':relation}


def evaluate(fit,probe,minimum,kind,frequent):
    evidence=defaultdict(lambda:defaultdict(set))
    for group,before,after in original_edges(fit):
        row=keys(before,after,frequent)
        if row is not None:evidence[row[kind]][after['gold_label']].add(group)
    rules={};ambiguous=0
    for key,labels in evidence.items():
        support=len(set().union(*labels.values()))
        if support<minimum:continue
        winner=min(labels,key=lambda label:(-len(labels[label]),label))
        confidence=len(labels[winner])/support
        if confidence>=0.8 and all(len(labels[winner])>len(ids)
                                   for label,ids in labels.items() if label!=winner):
            rules[key]=winner
        else:ambiguous+=1
    attempted=correct=available=0
    for _,before,after in original_edges(probe):
        row=keys(before,after,frequent)
        if row is None:continue
        available+=1
        prediction=rules.get(row[kind])
        if prediction is not None:
            attempted+=1;correct+=prediction==after['gold_label']
    return {'rules':len(rules),'ambiguous_keys':ambiguous,
            'probe_minimal_edges':available,'probe_attempts':attempted,
            'probe_correct':correct,'precision':round(correct/attempted,6)
            if attempted else None}


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    train,_,_,_=groups(tree)
    orders={}
    for seed in (0,17,53,97):
        ordered=list(train)
        if seed:random.Random(seed).shuffle(ordered)
        fit=ordered[:800];probe=ordered[800:1000]
        docs=Counter()
        for _,states in fit:
            docs.update(set(_tokens(states[0]['sentence1']))|
                        set(_tokens(states[0]['sentence2'])))
        frequent={token for token,n in docs.items() if n>=0.2*len(fit)}
        results={}
        for minimum in (2,3,5):
            results[str(minimum)]={kind:evaluate(fit,probe,minimum,kind,frequent)
                                   for kind in ('structural','cross_sentence_equality')}
        orders[str(seed)]={'frequent_token_count':len(frequent),
                           'by_support':results}
    output={'kind':'source_feasibility_only','engine_tree':tree,
            'fit_groups':800,'probe_groups':200,
            'frequent_threshold_fraction':0.2,'orders':orders,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f15_relation_abstraction_inventory.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

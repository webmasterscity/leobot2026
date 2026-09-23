"""Read-only audit of repeated human edits before proposing new operators."""
from __future__ import annotations

import json
import resource
import time
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from experiments.f14_revision_baselines import groups
from experiments.f14_typed_edit_learner import _tokens
from experiments.f7_typed_sequences_dev import git


ROOT=Path(__file__).resolve().parents[1]


def motif(before,after):
    sides=[key for key in ('sentence1','sentence2')
           if before[key]!=after[key]]
    if len(sides)!=1:return None
    side=sides[0];old=_tokens(before[side]);new=_tokens(after[side])
    operations=[(kind,a,b,c,d) for kind,a,b,c,d in
                SequenceMatcher(None,old,new,autojunk=False).get_opcodes()
                if kind!='equal']
    if len(operations)!=1:return None
    kind,a,b,c,d=operations[0]
    if b-a>3 or d-c>3:return None
    return (before['gold_label'],side,kind,tuple(old[a:b]),tuple(new[c:d]))


def original_edges(groups_):
    for identifier,states in groups_:
        before=states[0]
        for after in states[1:]:
            yield identifier,before,after


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    train,_,_,_=groups(tree)
    fit=train[:800];probe=train[800:1000]
    evidence=defaultdict(lambda:defaultdict(set))
    fit_total=fit_minimal=0
    for identifier,before,after in original_edges(fit):
        fit_total+=1;key=motif(before,after)
        if key is None:continue
        fit_minimal+=1
        evidence[key][after['gold_label']].add(identifier)
    counts={}
    for minimum in (2,3,5):
        reliable={key:next(iter(labels)) for key,labels in evidence.items()
                  if len(labels)==1 and len(next(iter(labels.values())))>=minimum}
        ambiguous={key for key,labels in evidence.items()
                   if sum(len(ids) for ids in labels.values())>=minimum and
                   len(labels)>1}
        probe_total=probe_minimal=attempts=correct=0
        for _,before,after in original_edges(probe):
            probe_total+=1;key=motif(before,after)
            if key is None:continue
            probe_minimal+=1
            if key in reliable:
                attempts+=1;correct+=reliable[key]==after['gold_label']
        counts[str(minimum)]={'reliable_motifs':len(reliable),
            'ambiguous_motifs':len(ambiguous),'probe_edges':probe_total,
            'probe_minimal_edges':probe_minimal,'probe_attempts':attempts,
            'probe_correct':correct}
    support=Counter()
    for labels in evidence.values():
        support[sum(len(ids) for ids in labels.values())]+=1
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'kind':'source_feasibility_only',
            'engine_tree':tree,'engine_unchanged':unchanged,
            'fit_groups':len(fit),'probe_groups':len(probe),
            'fit_original_to_revision_edges':fit_total,
            'fit_minimal_edges':fit_minimal,
            'distinct_motifs':len(evidence),
            'motif_support_distribution':dict(sorted(support.items())),
            'by_support':counts,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f15_edit_motif_inventory.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

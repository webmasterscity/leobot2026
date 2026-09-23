"""F-15 pilot: synthesize typed equality comparisons over edited records.

The base edit program was selected earlier from F-14 validation, not from F-15
held-out groups. Comparison descriptors are safe data interpreted here.
"""
from __future__ import annotations

import math
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from time import process_time

from experiments.f14_typed_edit_learner import TypedEditLearner,_tokens


SPAN_TYPES=('removed','added')
CONTEXT_TYPES=('other_old','other_new','same_unchanged','all_unchanged')
DESCRIPTORS=tuple((span,context) for span in SPAN_TYPES
                  for context in CONTEXT_TYPES)


def compare(descriptor,before,after,frequent):
    span_type,context_type=descriptor
    changed=[];unchanged=[]
    for side in ('sentence1','sentence2'):
        old=_tokens(before[side]);new=_tokens(after[side])
        if old==new:continue
        other='sentence2' if side=='sentence1' else 'sentence1'
        ops=SequenceMatcher(None,old,new,autojunk=False).get_opcodes()
        removed=set();added=set();retained=set()
        for kind,a,b,c,d in ops:
            if kind=='equal':retained.update(old[a:b])
            else:removed.update(old[a:b]);added.update(new[c:d])
        span=removed if span_type=='removed' else added
        if context_type=='other_old':context=set(_tokens(before[other]))
        elif context_type=='other_new':context=set(_tokens(after[other]))
        elif context_type=='same_unchanged':context=retained
        else:context=retained|set(_tokens(before[other]))
        span-=frequent;context-=frequent
        if span:changed.append(bool(span&context))
        unchanged.append(bool(span))
    if not any(unchanged):return 'unknown'
    if any(changed):return 'equal'
    return 'different'


class RelationalEditLearner(TypedEditLearner):
    def __init__(self,labels,base_families):
        super().__init__(labels)
        self.base_families=tuple(base_families)
        self.frequent=frozenset()
        self.relation_groups=defaultdict(set)
        self.relation_weights={}
        self.rel_cpu_s=0.0

    def fit(self,episodes):
        base=super().fit(episodes)
        started=process_time();docs=Counter();groups={}
        for group,before,_,_ in self.episodes:groups[group]=before
        for row in groups.values():
            docs.update(set(_tokens(row['sentence1']))|
                        set(_tokens(row['sentence2'])))
        self.frequent=frozenset(word for word,n in docs.items()
                                if n>=0.2*len(groups))
        self.relation_groups=defaultdict(set)
        for group,before,after,_ in self.episodes:
            old=before['gold_label'];new=after['gold_label']
            for descriptor in DESCRIPTORS:
                value=compare(descriptor,before,after,self.frequent)
                self.relation_groups[(old,new,descriptor,value)].add(group)
        self.relation_weights={}
        for old in self.labels:
            for descriptor in DESCRIPTORS:
                for value in ('equal','different'):
                    for label in self.labels:
                        positive=self.relation_groups[(old,label,descriptor,value)]
                        others=[other for other in self.labels if other!=label]
                        negative=set().union(*(
                            self.relation_groups[(old,other,descriptor,value)]
                            for other in others))
                        if len(positive|negative)<3:continue
                        pos_total=len(self.group_counts[(old,label)])
                        neg_total=len(set().union(*(
                            self.group_counts[(old,other)] for other in others)))
                        odds=(math.log((len(positive)+1)/(pos_total+2))-
                              math.log((len(negative)+1)/(neg_total+2)))
                        self.relation_weights[(old,descriptor,value,label)]=max(
                            -3.0,min(3.0,odds))
        self.rel_cpu_s=process_time()-started
        return {**base,'relation_keys':len(self.relation_groups),
                'compiled_weights':len(self.relation_weights),
                'frequent_tokens':len(self.frequent),
                'relation_fit_cpu_s':round(self.rel_cpu_s,6)}

    def _relation_score(self,old,descriptor,value,label):
        return self.relation_weights.get((old,descriptor,value,label),0.0)

    def _rank_relation(self,before,after,side,base,base_scores,
                       descriptor,weight,value=None):
        if value is None:value=compare(descriptor,before,after,self.frequent)
        scored=[];old=before['gold_label']
        for label in self.labels:
            score=base[label]+sum(base_scores[family][label]
                                   for family in self.base_families)
            score+=weight*self._relation_score(old,descriptor,value,label)
            scored.append((score,label))
        scored.sort(key=lambda row:(-row[0],row[1]))
        return scored

    def select_relation(self,validation,score_fn):
        started=process_time();prepared=[]
        for _,before,after,side in validation:
            base,parts=self._family_scores(before,after,side)
            values={descriptor:compare(descriptor,before,after,self.frequent)
                    for descriptor in DESCRIPTORS}
            prepared.append((before,after,side,base,parts,values))
        best=None;best_raw=None;descriptions=0
        for descriptor in DESCRIPTORS:
            for weight in (1.0,2.0):
                ranked=[self._rank_relation(before,after,side,base,parts,
                                            descriptor,weight,values[descriptor])
                        for before,after,side,base,parts,values in prepared]
                for margin in (0.0,1.0):
                    descriptions+=1
                    rows=[]
                    for (before,after,side,_,_,_),order in zip(prepared,ranked):
                        prediction=(order[0][1] if order[0][0]-order[1][0]>margin
                                    else None)
                        rows.append((before,after,side,prediction))
                    metric=score_fn(rows)
                    rank=(-metric['macro_accuracy'],-metric['correct'],
                          descriptor,weight,margin)
                    program={'comparison':list(descriptor),'weight':weight,
                             'margin':margin,'base_families':list(self.base_families)}
                    if best_raw is None or rank<best_raw[0]:
                        best_raw=(rank,program,metric)
                    if (metric['coverage']<0.5 or
                            (metric['precision'] or 0)<0.8):continue
                    if best is None or rank<best[0]:best=(rank,program,metric)
        self.program=best[1] if best else None
        return {'status':'selected' if best else 'rejected',
                'descriptions':descriptions,'program':self.program,
                'best_raw_program':best_raw[1],
                'best_raw_validation':best_raw[2],
                'search_cpu_s':round(process_time()-started,6)}

    def predict(self,before,after,side):
        if self.program is None:return None
        base,parts=self._family_scores(before,after,side)
        program=self.program
        order=self._rank_relation(before,after,side,base,parts,
                                  tuple(program['comparison']),program['weight'])
        if order[0][0]-order[1][0]<=program['margin']:return None
        return order[0][1]

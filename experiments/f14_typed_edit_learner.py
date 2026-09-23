"""F-14 pilot: bounded declarative learner of human edit effects.

Observations are grouped by original human example so repeated revisions do
not masquerade as independent support. Learned programs are feature-family
subsets plus a calibrated abstention margin, never executable source code.
"""
from __future__ import annotations

import math
import re
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from time import process_time

from leobot.language import normalize


FAMILIES=('side_ops','delta_words','replacement_pairs','anchors','shape')
MAX_PROGRAMS=31
MAX_CHANGED_TOKENS=6


def _tokens(text):
    return re.findall(r'[^\W_]+|[^\w\s]',normalize(text))


def _shape(token):
    if any(char.isdigit() for char in token):return 'digit'
    if not token:return 'empty'
    return 'punct' if all(not char.isalnum() for char in token) else 'word'


def features(before,after):
    result={family:set() for family in FAMILIES}
    changed_sides=[]
    for side in ('sentence1','sentence2'):
        left=_tokens(before[side]);right=_tokens(after[side])
        if left==right:continue
        changed_sides.append(side)
        edits=SequenceMatcher(None,left,right,autojunk=False).get_opcodes()
        for kind,a,b,c,d in edits:
            if kind=='equal':continue
            removed=left[a:b][:MAX_CHANGED_TOKENS]
            inserted=right[c:d][:MAX_CHANGED_TOKENS]
            result['side_ops'].add('side:'+side)
            result['side_ops'].add('op:'+side+':'+kind)
            result['side_ops'].add('location:'+side+':'+str(min(3,4*a//max(1,len(left)))))
            result['shape'].add('delta_len:'+str(max(-3,min(3,(d-c)-(b-a)))))
            for word in removed:result['delta_words'].add('remove:'+side+':'+word)
            for word in inserted:result['delta_words'].add('add:'+side+':'+word)
            if kind=='replace':
                for old,new in zip(removed,inserted):
                    result['replacement_pairs'].add(side+':'+old+'=>'+new)
                    result['shape'].add('replace_shape:'+side+':'+_shape(old)+
                                        '=>'+_shape(new))
            if a>0:result['anchors'].add('left:'+side+':'+left[a-1])
            if b<len(left):result['anchors'].add('right:'+side+':'+left[b])
    result['side_ops'].add('sides:'+str(len(changed_sides)))
    return {family:tuple(sorted(values)) for family,values in result.items()}


class TypedEditLearner:
    def __init__(self,labels):
        self.labels=tuple(sorted(set(labels)))
        self.episodes=[]
        self.transition=defaultdict(Counter)
        self.group_counts=defaultdict(set)
        self.feature_groups=defaultdict(set)
        self.program=None
        self.fit_cpu_s=0.0

    def fit(self,episodes):
        started=process_time();self.episodes=list(episodes)
        self.transition=defaultdict(Counter)
        self.group_counts=defaultdict(set)
        self.feature_groups=defaultdict(set)
        for group_id,before,after,side in self.episodes:
            side=tuple(side)
            old=before['gold_label'];new=after['gold_label']
            if old not in self.labels or new not in self.labels:continue
            self.transition[(old,side)][new]+=1
            self.group_counts[(old,new)].add(group_id)
            for family,values in features(before,after).items():
                for value in values:
                    self.feature_groups[(old,new,family,value)].add(group_id)
        self.fit_cpu_s=process_time()-started
        return {'episodes':len(self.episodes),'groups':len({row[0] for row in self.episodes}),
                'feature_keys':len(self.feature_groups),
                'fit_cpu_s':round(self.fit_cpu_s,6)}

    def _family_scores(self,before,after,side):
        side=tuple(side)
        old=before['gold_label'];observed=features(before,after)
        prior=self.transition[(old,side)]
        prior_total=sum(prior.values());label_count=len(self.labels)
        base={label:math.log((prior[label]+1)/(prior_total+label_count))
              for label in self.labels}
        per_family={family:{} for family in FAMILIES}
        for family in FAMILIES:
            for label in self.labels:
                others=[other for other in self.labels if other!=label]
                positive_total=len(self.group_counts[(old,label)])
                negative_total=len(set().union(*(
                    self.group_counts[(old,other)] for other in others)))
                total=0.0
                for value in observed[family]:
                    positive=self.feature_groups[(old,label,family,value)]
                    negative=set().union(*(
                        self.feature_groups[(old,other,family,value)]
                        for other in others))
                    if len(positive|negative)<3:continue
                    odds=(math.log((len(positive)+1)/(positive_total+2))-
                          math.log((len(negative)+1)/(negative_total+2)))
                    total+=max(-2.5,min(2.5,odds))
                per_family[family][label]=max(-6.0,min(6.0,total))
        return base,per_family

    @staticmethod
    def _rank(base,per_family,program):
        scored=[]
        for label,prior in base.items():
            value=prior+sum(per_family[family][label] for family in program)
            scored.append((value,label))
        scored.sort(key=lambda item:(-item[0],item[1]))
        return scored

    def select_program(self,validation,score_fn):
        """Search 31 typed descriptions and four margins on disjoint groups."""
        started=process_time()
        prepared=[]
        for _,before,after,side in validation:
            base,per_family=self._family_scores(before,after,side)
            prepared.append((before,after,side,base,per_family))
        best=None;considered=0
        for size in range(1,len(FAMILIES)+1):
            for family_set in combinations(FAMILIES,size):
                considered+=1
                if considered>MAX_PROGRAMS:break
                ranked=[self._rank(base,per_family,family_set)
                        for _,_,_,base,per_family in prepared]
                for threshold in (0.0,0.5,1.0,2.0):
                    predictions=[]
                    for (before,after,side,_,_),order in zip(prepared,ranked):
                        margin=order[0][0]-order[1][0]
                        prediction=order[0][1] if margin>threshold else None
                        predictions.append((before,after,side,prediction))
                    metric=score_fn(predictions)
                    if metric['coverage']<0.5 or (
                            metric['precision'] or 0)<0.8:
                        continue
                    rank=(-metric['macro_accuracy'],-metric['correct'],
                          len(family_set),family_set,threshold)
                    if best is None or rank<best[0]:
                        best=(rank,{'families':list(family_set),
                                    'margin':threshold,'validation':metric})
        self.program=best[1] if best else None
        return {'status':'selected' if best else 'rejected',
                'descriptions':considered,'program':self.program,
                'search_cpu_s':round(process_time()-started,6)}

    def predict(self,before,after,side):
        if self.program is None:return None
        base,per_family=self._family_scores(before,after,side)
        ranked=self._rank(base,per_family,self.program['families'])
        if ranked[0][0]-ranked[1][0]<=self.program['margin']:return None
        return ranked[0][1]

    def as_dict(self):
        return {'labels':list(self.labels),'episodes':self.episodes,
                'program':self.program}

    @classmethod
    def from_dict(cls,data):
        if (not isinstance(data,dict) or set(data)!={'labels','episodes','program'}):
            raise ValueError('Datos de learner inválidos')
        model=cls(data['labels']);model.fit(data['episodes'])
        program=data['program']
        if program is not None:
            if (not isinstance(program,dict) or
                not isinstance(program.get('families'),list) or
                not program['families'] or len(program['families'])>len(FAMILIES) or
                not set(program['families'])<=set(FAMILIES) or
                program.get('margin') not in (0.0,0.5,1.0,2.0)):
                raise ValueError('Programa no permitido')
            model.program=program
        return model

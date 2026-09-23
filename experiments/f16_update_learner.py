"""F-16 pilot: safe, bounded equality programs over typed update records."""
from __future__ import annotations

import math
import re
from collections import Counter,defaultdict
from time import process_time

from leobot.language import normalize


LABELS=('strengthener','weakener')
TARGETS=('claim','information')
OPERATIONS=('overlap_binary','overlap_bucket','novelty_binary','shared_bigram')
WEIGHTS=(1.0,2.0)
MARGINS=(0.0,1.0)


def words(text):
    return tuple(re.findall(r'[^\W_]+',normalize(text)))


def relation(record,descriptor,frequent):
    target,operation=descriptor
    target_text=record.get(target)
    if target_text is None:return 'undefined'
    update=[word for word in words(record['update']) if word not in frequent]
    comparison=[word for word in words(target_text) if word not in frequent]
    if not update or not comparison:return 'unknown'
    first=set(update);second=set(comparison)
    common=len(first&second)
    if operation=='overlap_binary':return 'yes' if common else 'no'
    if operation=='overlap_bucket':return str(min(3,common))
    if operation=='novelty_binary':return 'yes' if len(first-second)>=2 else 'no'
    if operation=='shared_bigram':
        a=set(zip(update,update[1:]));b=set(zip(comparison,comparison[1:]))
        return 'yes' if a&b else 'no'
    return 'undefined'


class UpdateLearner:
    def __init__(self):
        self.records=[];self.lex_docs=Counter();self.lex_counts=defaultdict(Counter)
        self.vocabulary=set();self.frequent=frozenset()
        self.groups=defaultdict(set);self.rel_groups=defaultdict(set)
        self.rel_weights={};self.program=None

    def fit(self,records):
        started=process_time();self.records=list(records)
        self.lex_docs=Counter();self.lex_counts=defaultdict(Counter)
        self.vocabulary=set();self.groups=defaultdict(set)
        self.rel_groups=defaultdict(set);self.rel_weights={}
        group_tokens=defaultdict(set)
        for row in self.records:
            group_tokens[row['group']].update(words(row['update']))
            group_tokens[row['group']].update(words(row['claim']))
            group_tokens[row['group']].update(words(row.get('information') or ''))
        docs=Counter()
        for values in group_tokens.values():docs.update(values)
        self.frequent=frozenset(token for token,n in docs.items()
                                if n>=0.2*max(1,len(group_tokens)))
        descriptors=tuple((target,operation) for target in TARGETS
                          for operation in OPERATIONS)
        for row in self.records:
            label=row['label'];group=row['group'];tokens=set(words(row['update']))
            if label not in LABELS:continue
            self.lex_docs[label]+=1;self.lex_counts[label].update(tokens)
            self.vocabulary.update(tokens);self.groups[label].add(group)
            for descriptor in descriptors:
                value=relation(row,descriptor,self.frequent)
                self.rel_groups[(label,descriptor,value)].add(group)
        for descriptor in descriptors:
            for label in LABELS:
                other=next(item for item in LABELS if item!=label)
                for value in ('yes','no','0','1','2','3','unknown'):
                    positive=self.rel_groups[(label,descriptor,value)]
                    negative=self.rel_groups[(other,descriptor,value)]
                    if len(positive|negative)<3:continue
                    value_score=(math.log((len(positive)+1)/(len(self.groups[label])+2))-
                                 math.log((len(negative)+1)/(len(self.groups[other])+2)))
                    self.rel_weights[(descriptor,value,label)]=max(-3,min(3,value_score))
        return {'records':len(self.records),'groups':len(group_tokens),
                'vocabulary':len(self.vocabulary),'frequent_tokens':len(self.frequent),
                'compiled_relations':len(self.rel_weights),
                'fit_cpu_s':round(process_time()-started,6)}

    def _lexical_scores(self,row):
        terms=sorted(term for term in set(words(row['update']))
                     if term in self.vocabulary)
        total=sum(self.lex_docs.values())
        out={}
        for label in LABELS:
            value=math.log((self.lex_docs[label]+1)/(total+len(LABELS)))
            value+=sum(math.log((self.lex_counts[label][token]+1)/
                                (self.lex_docs[label]+2)) for token in terms)
            out[label]=value
        return out

    def _rank(self,base,descriptor,value,weight):
        ranked=[(base[label]+weight*self.rel_weights.get((descriptor,value,label),0.0),
                 label) for label in LABELS]
        ranked.sort(key=lambda row:(-row[0],row[1]))
        return ranked

    def select_program(self,validation,metric_fn,prior=None):
        started=process_time()
        descriptors=[(target,operation) for target in TARGETS
                     for operation in OPERATIONS
                     if not (target=='information' and all(
                         row.get('information') is None for row in validation))]
        prepared=[]
        for row in validation:
            base=self._lexical_scores(row)
            values={desc:relation(row,desc,self.frequent) for desc in descriptors}
            prepared.append((row,base,values))
        # Training-only information gain gives the fresh search a fair default.
        importance={desc:sum(abs(self.rel_weights.get((desc,value,label),0))
                  for value in ('yes','no','0','1','2','3') for label in LABELS)
                  for desc in descriptors}
        descriptors.sort(key=lambda desc:(-importance[desc],desc))
        if prior in descriptors:
            descriptors.remove(prior);descriptors.insert(0,prior)
        best=None;best_raw=None;examined=0
        for desc in descriptors:
            for weight in WEIGHTS:
                rankings=[self._rank(base,desc,values[desc],weight)
                          for _,base,values in prepared]
                for margin in MARGINS:
                    examined+=1
                    guesses=[(ranks[0][1] if ranks[0][0]-ranks[1][0]>margin
                              else None) for ranks in rankings]
                    metric=metric_fn([row for row,_,_ in prepared],guesses)
                    rank=(-metric['macro_accuracy'],-metric['correct'],
                          desc,weight,margin)
                    program={'comparison':list(desc),'weight':weight,
                             'margin':margin}
                    if best_raw is None or rank<best_raw[0]:
                        best_raw=(rank,program,metric)
                    if ((metric['precision'] or 0)>=0.8 and
                            metric['coverage']>=0.5):
                        if best is None or rank<best[0]:best=(rank,program,metric)
                        if (metric['macro_accuracy']>=0.75 and
                                metric['precision']>=0.85 and metric['coverage']>=0.6):
                            self.program=best[1]
                            return {'status':'selected','descriptions':examined,
                                    'program':self.program,
                                    'best_raw_program':best_raw[1],
                                    'best_raw_validation':best_raw[2],
                                    'search_cpu_s':round(process_time()-started,6)}
        self.program=best[1] if best else None
        return {'status':'selected' if best else 'rejected',
                'descriptions':examined,'program':self.program,
                'best_raw_program':best_raw[1] if best_raw else None,
                'best_raw_validation':best_raw[2] if best_raw else None,
                'search_cpu_s':round(process_time()-started,6)}

    def predict(self,row):
        if self.program is None:return None
        descriptor=tuple(self.program['comparison'])
        value=relation(row,descriptor,self.frequent)
        ranked=self._rank(self._lexical_scores(row),descriptor,value,
                          self.program['weight'])
        if ranked[0][0]-ranked[1][0]<=self.program['margin']:return None
        return ranked[0][1]

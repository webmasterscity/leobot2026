"""F-9 pilot: explicit question-to-evidence relations learned from feedback.

The only candidate operation is a bounded join between a question token and
the tokens near a possible answer. It learns count tables; no generated code,
language-specific vocabulary, external model, or benchmark answer is used.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from math import log
from time import process_time


MAX_WORDS=6
MAX_SPAN=8


def _shape(sequence,start,end):
    text=' '.join(row['text'] for row in sequence[start:end])
    if any(char.isdigit() for char in text):return 'digit'
    if text.isupper() and len(text)>1:return 'upper'
    return 'capital' if text[:1].isupper() else 'lower'


def spans(sequence):
    for start in range(len(sequence)):
        for end in range(start+1,min(len(sequence),start+MAX_SPAN)+1):
            yield start,end


def _near(sequence,start,end):
    result=[]
    for zone,index in ((-2,start-2),(-1,start-1),(1,end),(2,end+1)):
        if 0<=index<len(sequence):
            result.append((zone,sequence[index]['norm']))
    return result


class RelationalEvidence:
    def __init__(self,*,use_join=True):
        self.use_join=bool(use_join)
        self.episodes={}
        self.df=Counter()
        self.pos_join=Counter();self.neg_join=Counter()
        self.pos_prior=Counter();self.neg_prior=Counter()
        self.pos_total=0;self.neg_total=0
        self.threshold=None
        self.train_candidates=0
        self.join_candidates=0

    def _terms(self,question):
        eligible={token['norm'] for token in question if self.df[token['norm']]>=5}
        return tuple(sorted(eligible,key=lambda word:(self.df[word],word))[:MAX_WORDS])

    @staticmethod
    def _negatives(episode):
        sequences=episode['sequences'];gold_rank=episode['gold_rank']
        gold=tuple(episode['gold'])
        same=[(gold_rank,span) for span in spans(sequences[gold_rank])
              if span!=gold]
        same.sort(key=lambda row:(abs(row[1][0]-gold[0])+
                                  abs(row[1][1]-gold[1]),row[1]))
        picked=same[:4]
        rest=[(rank,span) for rank,sequence in enumerate(sequences)
              for span in spans(sequence) if (rank,span)!=(gold_rank,gold)
              and (rank,span) not in picked]
        rest.sort(key=lambda row:sha256(
            f"{episode['id']}:{row[0]}:{row[1][0]}:{row[1][1]}".encode()).hexdigest())
        picked.extend(rest[:max(0,8-len(picked))])
        return picked

    def observe_many(self,episodes):
        for episode in episodes:self.episodes[str(episode['id'])]=episode
        self._rebuild()

    def remove(self,identifier):
        self.episodes.pop(str(identifier),None)
        self._rebuild();self.threshold=None

    def _rebuild(self):
        self.df=Counter();self.pos_join=Counter();self.neg_join=Counter()
        self.pos_prior=Counter();self.neg_prior=Counter()
        self.pos_total=0;self.neg_total=0;self.train_candidates=0
        for key in sorted(self.episodes):
            self.df.update({token['norm'] for token in
                            self.episodes[key]['question']})
        for key in sorted(self.episodes):
            ep=self.episodes[key];terms=self._terms(ep['question'])
            positive=(ep['gold_rank'],tuple(ep['gold']))
            negatives=self._negatives(ep)
            self.train_candidates+=1+len(negatives)
            for label,(rank,span) in ((True,positive),*(
                    (False,row) for row in negatives)):
                sequence=ep['sequences'][rank];start,end=span
                if not 0<=start<end<=len(sequence):continue
                prior=self.pos_prior if label else self.neg_prior
                joins=self.pos_join if label else self.neg_join
                prior.update((('shape',_shape(sequence,start,end)),
                              ('length',str(min(4,end-start)))))
                if self.use_join:
                    joins.update((term,word,zone) for term in terms
                                 for zone,word in _near(sequence,start,end))
                if label:self.pos_total+=1
                else:self.neg_total+=1

    def _odds(self,key,positive,negative,minimum):
        p=positive[key];n=negative[key]
        if p+n<minimum:return 0.0
        return max(-3.0,min(3.0,log((p+1)/(self.pos_total+2))-
                            log((n+1)/(self.neg_total+2))))

    def _ranked(self,question,sequences):
        terms=self._terms(question) if self.use_join else ()
        results=[];count=0
        for rank,sequence in enumerate(sequences):
            left=[0.0]*len(sequence)
            right=[0.0]*(len(sequence)+1)
            for start in range(len(sequence)):
                for zone,index in ((-2,start-2),(-1,start-1)):
                    if 0<=index<len(sequence):
                        word=sequence[index]['norm']
                        left[start]+=sum(self._odds((term,word,zone),
                            self.pos_join,self.neg_join,3) for term in terms)
            for end in range(1,len(sequence)+1):
                for zone,index in ((1,end),(2,end+1)):
                    if 0<=index<len(sequence):
                        word=sequence[index]['norm']
                        right[end]+=sum(self._odds((term,word,zone),
                            self.pos_join,self.neg_join,3) for term in terms)
            for start,end in spans(sequence):
                shape=('shape',_shape(sequence,start,end))
                length=('length',str(min(4,end-start)))
                score=left[start]+right[end]
                score+=self._odds(shape,self.pos_prior,self.neg_prior,3)
                score+=self._odds(length,self.pos_prior,self.neg_prior,3)
                results.append((score,rank,start,end))
                count+=1
        results.sort(key=lambda item:(-item[0],item[1],item[2],item[3]))
        return results,count

    @staticmethod
    def _choice(ranked,threshold):
        if not ranked:return None
        score,rank,start,end=ranked[0]
        margin=score-ranked[1][0] if len(ranked)>1 else 100.0
        if score<=threshold[0] or margin<=threshold[1]:return None
        return rank,start,end

    def calibrate(self,validation):
        started=process_time();prepared=[];candidates=0
        for ep in validation:
            ranked,count=self._ranked(ep['question'],ep['sequences'])
            candidates+=count
            prepared.append((ranked,(ep['gold_rank'],*ep['gold'])))
        best=None
        for minimum_score in (-2.0,0.0,2.0):
            for margin in (0.0,0.5,1.0,2.0):
                threshold=(minimum_score,margin)
                chosen=[(self._choice(ranked,threshold),gold)
                        for ranked,gold in prepared]
                attempts=sum(prediction is not None for prediction,_ in chosen)
                correct=sum(prediction==gold for prediction,gold in chosen
                            if prediction is not None)
                if attempts<max(3,len(prepared)//8) or correct/attempts<0.8:
                    continue
                priority=(-correct,-correct/attempts,minimum_score,margin)
                if best is None or priority<best[0]:
                    best=(priority,threshold,correct,attempts)
        if best is None:
            self.threshold=None
            return {'status':'rejected','candidates':candidates,
                    'cpu_s':process_time()-started}
        self.threshold=best[1]
        return {'status':'calibrated','threshold':list(best[1]),
                'correct':best[2],'attempts':best[3],
                'candidates':candidates,'cpu_s':process_time()-started}

    def predict(self,question,sequences):
        if self.threshold is None:return {'status':'abstain','candidates':0}
        ranked,count=self._ranked(question,sequences)
        choice=self._choice(ranked,self.threshold)
        if choice is None:return {'status':'abstain','candidates':count}
        return {'status':'predicted','choice':choice,'candidates':count,
                'score':ranked[0][0],
                'margin':ranked[0][0]-ranked[1][0] if len(ranked)>1 else 100.0}

    def as_dict(self):
        return {'use_join':self.use_join,'episodes':{
                key:self.episodes[key] for key in sorted(self.episodes)},
                'threshold':list(self.threshold) if self.threshold else None}

    @classmethod
    def from_dict(cls,data):
        if type(data.get('use_join')) is not bool:
            raise ValueError('Learner inválido')
        learner=cls(use_join=data['use_join'])
        learner.observe_many(data['episodes'].values())
        threshold=data['threshold']
        if threshold is not None:
            if (not isinstance(threshold,list) or len(threshold)!=2 or
                    threshold[0] not in (-2.0,0.0,2.0) or
                    threshold[1] not in (0.0,0.5,1.0,2.0)):
                raise ValueError('Umbral inválido')
            learner.threshold=tuple(threshold)
        return learner

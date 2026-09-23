"""F-8 pilot: finite, declarative ranking programs for labeled sequence spans.

No generated code is executed. Feature names and the search grammar are fixed;
the selected program, its count tables, and all support episodes are data.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations
from math import log
from time import process_time


OPERATORS=('length','position','first_shape','last_shape','left_word',
           'right_word','context_overlap','container_rank')
MAX_SPAN=8
MAX_DESCRIPTIONS=96
MAX_SCORED=125000  # Two roles together remain within the 250k family cap.


def _shape(token):
    value=token['text']
    if any(char.isdigit() for char in value):return 'digit'
    if value.isupper() and len(value)>1:return 'upper'
    return 'capital' if value[:1].isupper() else 'lower'


def span_features(sequence,context,start,end,container_rank=0):
    n=len(sequence);context=set(context)
    return {
        'length':str(min(4,end-start)),
        'position':str(min(3,4*start//max(1,n))),
        'first_shape':_shape(sequence[start]),
        'last_shape':_shape(sequence[end-1]),
        'left_word':sequence[start-1]['norm'] if start else '<start>',
        'right_word':sequence[end]['norm'] if end<n else '<end>',
        'context_overlap':str(min(2,sum(sequence[i]['norm'] in context
                                         for i in range(start,end)))),
        'container_rank':str(min(3,container_rank)),
    }


def candidates(sequence):
    for start in range(len(sequence)):
        for end in range(start+1,min(len(sequence),start+MAX_SPAN)+1):
            yield start,end


def _negative_spans(sequence,gold,identifier):
    options=[span for span in candidates(sequence) if span!=gold]
    if not options:return []
    near=sorted(options,key=lambda span:(abs(span[0]-gold[0])+
                                         abs(span[1]-gold[1]),span))[:4]
    far=sorted(options,key=lambda span:sha256(
        f'{identifier}:{span[0]}:{span[1]}'.encode()).hexdigest())[:8]
    return list(dict.fromkeys((*near,*far)))


def _ratio(pos,neg,positive_total,negative_total,value):
    # Lexical contexts with fewer than three positive examples are evidence
    # of individual names, not a reusable construction.
    if value not in pos and value not in neg:return 0.0
    if isinstance(value,str) and value not in ('<start>','<end>') and (
            pos[value]+neg[value]<3):
        return 0.0
    vocab=max(2,len(set(pos)|set(neg)))
    return log((pos[value]+1)/(positive_total+vocab))-log(
        (neg[value]+1)/(negative_total+vocab))


class SpanProgramLearner:
    def __init__(self):
        self.episodes={}
        self.tables={}
        self.programs={}
        self.search_counts=Counter()

    def observe_many(self,episodes):
        for episode in episodes:
            self.episodes[str(episode['id'])]=episode
        self._rebuild()

    def remove(self,identifier):
        self.episodes.pop(str(identifier),None)
        self._rebuild()
        self.programs={}

    def _rebuild(self):
        tables={}
        for identifier in sorted(self.episodes):
            row=self.episodes[identifier]
            sequence=row['tokens'];context=row.get('context',[])
            rank=row.get('container_rank',0)
            for role,start,end in row['spans']:
                if not 0<=start<end<=len(sequence) or end-start>MAX_SPAN:
                    continue
                table=tables.setdefault(role,{'positive':defaultdict(Counter),
                                              'negative':defaultdict(Counter),
                                              'positive_total':0,'negative_total':0})
                for positive,span in ((True,(start,end)),*(
                        (False,negative) for negative in
                        _negative_spans(sequence,(start,end),identifier))):
                    features=span_features(sequence,context,*span,rank)
                    category='positive' if positive else 'negative'
                    for name,value in features.items():
                        table[category][name][value]+=1
                    table[category+'_total']+=1
        self.tables=tables

    def _scores(self,role,sequence,context,rank):
        table=self.tables.get(role)
        if table is None:return []
        result=[]
        for start,end in candidates(sequence):
            features=span_features(sequence,context,start,end,rank)
            score={name:_ratio(table['positive'][name],table['negative'][name],
                    table['positive_total'],table['negative_total'],value)
                   for name,value in features.items()}
            result.append(((start,end),score))
        return result

    def _single_operator_order(self,role):
        table=self.tables[role]
        weighted=[]
        for operator in OPERATORS:
            positive=table['positive'][operator];negative=table['negative'][operator]
            signal=sum(count*max(0.0,_ratio(positive,negative,
                table['positive_total'],table['negative_total'],value))
                for value,count in positive.items())/max(1,table['positive_total'])
            weighted.append((-signal,operator))
        return [name for _,name in sorted(weighted)]

    @staticmethod
    def _trial(rows,operators,threshold):
        correct=attempts=0
        for scores,gold in rows:
            ranked=sorted(((sum(parts[name] for name in operators),span)
                           for span,parts in scores),key=lambda pair:(-pair[0],pair[1]))
            if not ranked:continue
            margin=ranked[0][0]-ranked[1][0] if len(ranked)>1 else 100.0
            if margin<=threshold:continue
            attempts+=1;correct+=ranked[0][1]==gold
        return correct,attempts

    def synthesize(self,role,validation,prior=()):
        """Choose a finite feature program using episodes separate from fitting."""
        if role not in self.tables or not validation:
            return {'status':'pending','descriptions':0,'candidates':0}
        started=process_time()
        order=self._single_operator_order(role)[:5]
        options=[names for width in (1,2,3)
                 for names in combinations(order,width)]
        options.sort(key=lambda names:(not all(name in prior for name in names),
                                      len(names),names))
        scored=[];count=0
        for row in validation:
            sequence=row['tokens']
            if role not in {name for name,_,_ in row['spans']}:continue
            gold=next((start,end) for name,start,end in row['spans'] if name==role)
            if gold[1]-gold[0]>MAX_SPAN:continue
            scores=self._scores(role,sequence,row.get('context',[]),
                                row.get('container_rank',0))
            scored.append((scores,gold))
            count+=len(scores)
        best=None;examined=0;candidate_count=0
        for names in options[:MAX_DESCRIPTIONS]:
            if candidate_count+count>MAX_SCORED:break
            examined+=1;candidate_count+=count
            for threshold in (0.0,0.5,1.0,2.0):
                correct,attempts=self._trial(scored,names,threshold)
                if attempts<max(3,len(scored)//8):continue
                precision=correct/attempts
                if precision<0.8:continue
                rank=(-correct,-precision,len(names),names,threshold)
                if best is None or rank<best[0]:
                    best=(rank,{'input_representation':'token_sequence',
                                'hypothesis_generator':'bounded_spans',
                                'operators':list(names),'search':'rank_by_count_odds',
                                'verifier':'separate_episodes',
                                'cost':'correct_then_complexity',
                                'promotion':{'min_precision':0.8},
                                'rollback':'withdraw_on_invalidated',
                                'budget':{'max_descriptions':MAX_DESCRIPTIONS,
                                          'max_scored_spans':MAX_SCORED},
                                'threshold':threshold,
                                'validation_correct':correct,
                                'validation_attempts':attempts})
        self.search_counts[role]+=candidate_count
        if best is None:
            self.programs.pop(role,None)
            return {'status':'rejected','descriptions':examined,
                    'candidates':candidate_count,'cpu_s':process_time()-started}
        self.programs[role]=best[1]
        return {'status':'fitted','program':best[1],'descriptions':examined,
                'candidates':candidate_count,'cpu_s':process_time()-started}

    def predict(self,role,sequence,context=(),rank=0):
        program=self.programs.get(role)
        if program is None:return {'status':'abstain','candidates':0}
        scores=self._scores(role,sequence,context,rank)
        ranked=sorted(((sum(parts[name] for name in program['operators']),span)
                       for span,parts in scores),key=lambda pair:(-pair[0],pair[1]))
        if not ranked:return {'status':'abstain','candidates':0}
        margin=ranked[0][0]-ranked[1][0] if len(ranked)>1 else 100.0
        if margin<=program['threshold']:
            return {'status':'abstain','candidates':len(ranked),'margin':margin}
        return {'status':'predicted','span':ranked[0][1],
                'candidates':len(ranked),'margin':margin,'score':ranked[0][0]}

    def as_dict(self):
        return {'episodes':{key:self.episodes[key] for key in sorted(self.episodes)},
                'programs':self.programs}

    @classmethod
    def from_dict(cls,data):
        learner=cls();learner.observe_many(data['episodes'].values())
        for role,program in data['programs'].items():
            if (program.get('input_representation')!='token_sequence' or
                    program.get('hypothesis_generator')!='bounded_spans' or
                    not isinstance(program.get('operators'),list) or
                    not set(program['operators'])<=set(OPERATORS) or
                    len(program['operators'])>3 or
                    program.get('search')!='rank_by_count_odds' or
                    program.get('rollback')!='withdraw_on_invalidated' or
                    program.get('budget')!={'max_descriptions':MAX_DESCRIPTIONS,
                                            'max_scored_spans':MAX_SCORED} or
                    type(program.get('threshold')) not in (int,float) or
                    program['threshold'] not in (0.0,0.5,1.0,2.0)):
                raise ValueError('Programa de tramos no permitido')
            learner.programs[role]=program
        return learner

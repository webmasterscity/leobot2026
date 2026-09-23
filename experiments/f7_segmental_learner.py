"""Bounded, explicit-count sequence learner used only by the F-7 pilot.

The learner accepts role names as data.  It has no dataset, relation, question
word, or answer in its code.  Decoding is finite dynamic programming, not a
neural model or an interpreter for generated Python.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict


MAX_TOKENS=128
MAX_ROLES=3


def _type(state):
    return state.split(':',1)[0]


def _shape(raw):
    if any(char.isdigit() for char in raw):
        return 'digit'
    if raw[:1].isupper():
        return 'capital'
    return 'lower'


def _features(tokens,index,context):
    row=tokens[index]
    norm=row['norm'];raw=row['text']
    left=tokens[index-1]['norm'] if index else '<start>'
    right=tokens[index+1]['norm'] if index+1<len(tokens) else '<end>'
    overlap=norm in context
    location=min(3,4*index//max(1,len(tokens)))
    return (f'word:{norm}',f'left:{left}',f'right:{right}',
            f'shape:{_shape(raw)}',f'length:{min(len(norm),12)}',
            f'position:{location}',f'context:{int(overlap)}',
            f'left_context:{int(left in context)}',
            f'right_context:{int(right in context)}')


class SegmentalLearner:
    def __init__(self):
        self.episodes={}
        self.role_counts=defaultdict(Counter)
        self.role_totals=Counter()
        self.generic_counts=defaultdict(Counter)
        self.generic_totals=Counter()
        self.transition=Counter()
        self.transition_total=Counter()
        self.labels=Counter()
        self.label_words=defaultdict(Counter)
        self.label_totals=Counter()
        self.all_words=Counter()
        self.candidate_labels=0

    @staticmethod
    def _validate(tokens,spans):
        if not 1<=len(tokens)<=MAX_TOKENS or len(spans)>MAX_ROLES:
            return False
        used=set()
        for role,start,end in spans:
            if (not isinstance(role,str) or not role or
                    not 0<=start<end<=len(tokens) or
                    used.intersection(range(start,end))):
                return False
            used.update(range(start,end))
        return True

    def observe(self,identifier,tokens,context,spans,label=None):
        if not self._validate(tokens,spans):
            return {'status':'rejected_episode'}
        context=[str(x) for x in context]
        self.episodes[str(identifier)]={'tokens':tokens,'context':context,
                                        'spans':[[role,start,end] for role,start,end in spans],
                                        'label':label}
        self._rebuild()
        return {'status':'observed','episodes':len(self.episodes)}

    def observe_many(self,rows):
        for row in rows:
            if self._validate(row['tokens'],row['spans']):
                self.episodes[str(row['id'])]={
                    'tokens':row['tokens'],'context':list(row['context']),
                    'spans':[[role,start,end] for role,start,end in row['spans']],
                    'label':row.get('label')}
        self._rebuild()

    def _rebuild(self):
        self.role_counts=defaultdict(Counter);self.role_totals=Counter()
        self.generic_counts=defaultdict(Counter);self.generic_totals=Counter()
        self.transition=Counter();self.transition_total=Counter()
        self.labels=Counter();self.label_words=defaultdict(Counter)
        self.label_totals=Counter();self.all_words=Counter()
        for identifier in sorted(self.episodes):
            episode=self.episodes[identifier]
            tokens=episode['tokens'];context=set(episode['context'])
            states=['O']*len(tokens)
            for role,start,end in episode['spans']:
                states[start]='B:'+role
                for index in range(start+1,end):states[index]='I:'+role
            prev='<start>'
            for index,state in enumerate(states):
                self.transition[(prev,_type(state))]+=1
                self.transition_total[prev]+=1
                prev=_type(state)
                features=_features(tokens,index,context)
                self.role_counts[state].update(features)
                self.role_totals[state]+=1
                # Cross-domain prior only uses role-independent shape/position.
                general=[f for f in features if f.startswith(('shape:','length:','position:'))]
                self.generic_counts[_type(state)].update(general)
                self.generic_totals[_type(state)]+=1
            self.transition[(prev,'<end>')]+=1
            self.transition_total[prev]+=1
            label=episode['label']
            if label is not None:
                self.labels[label]+=1
                covered={i for _,start,end in episode['spans'] for i in range(start,end)}
                words=set(tokens[i]['norm'] for i in range(len(tokens)) if i not in covered)
                self.label_words[label].update(words)
                self.label_totals[label]+=len(words)
                self.all_words.update(words)

    def as_dict(self):
        return {'episodes':{key:self.episodes[key] for key in sorted(self.episodes)}}

    @classmethod
    def from_dict(cls,data):
        learner=cls()
        learner.episodes={str(key):value for key,value in data['episodes'].items()}
        learner._rebuild()
        return learner

    def _emission(self,state,features,allow_transfer):
        if state=='O':return 0.0
        role=self.role_counts[state];other=self.role_counts['O']
        role_total=self.role_totals[state];other_total=self.role_totals['O']
        total=0.0
        for feature in features:
            if role[feature]+other[feature]<4:
                continue
            pos=(role[feature]+1)/(role_total+2)
            neg=(other[feature]+1)/(other_total+2)
            total+=0.4*math.log(pos/neg)
        if allow_transfer:
            kind=_type(state)
            for feature in features:
                if not feature.startswith(('shape:','length:','position:')):
                    continue
                pos=self.generic_counts[kind][feature]
                neg=self.generic_counts['O'][feature]
                if pos+neg<5:continue
                total+=0.15*math.log(
                    ((pos+1)/(self.generic_totals[kind]+2))/
                    ((neg+1)/(self.generic_totals['O']+2)))
        return total

    def _transition_score(self,previous,next_type):
        count=self.transition[(previous,next_type)]
        total=self.transition_total[previous]
        return 0.35*math.log((count+1)/(total+5))

    @staticmethod
    def _allowed(previous,next_state,mask,roles):
        if next_state=='O':return True
        kind,role=next_state.split(':',1)
        bit=1<<roles.index(role)
        if kind=='B':return not mask & bit
        return previous in ('B:'+role,'I:'+role)

    def _label_score(self,tokens,spans):
        if not self.labels:return None
        used={index for start,end in spans.values() for index in range(start,end)}
        words=set(row['norm'] for index,row in enumerate(tokens) if index not in used)
        labels={label for word in words for label,row in self.label_words.items()
                if row[word]>0 and self.labels[label]>=3}
        if not labels:return None
        vocab=max(1,len(self.all_words));scores=[]
        for label in sorted(labels):
            score=0.0
            for word in words:
                if self.all_words[word]<3:continue
                score+=math.log((self.label_words[label][word]+1)/
                                (self.label_totals[label]+vocab))
            scores.append((score,label))
        scores.sort(reverse=True)
        if len(scores)>1 and scores[0][0]-scores[1][0]<1.0:
            return None
        return scores[0][1]

    def predict(self,tokens,context,roles,*,allow_transfer=True):
        if not 1<=len(tokens)<=MAX_TOKENS or not 1<=len(roles)<=MAX_ROLES:
            return {'status':'budget_or_roles','spans':{},'label':None,'candidates':0}
        roles=tuple(dict.fromkeys(roles))
        if any(self.role_totals['B:'+role]==0 for role in roles):
            return {'status':'unlearned_role','spans':{},'label':None,'candidates':0}
        states=('O',)+tuple(kind+':'+role for role in roles for kind in ('B','I'))
        options={(0,'<start>'):[(0.0,())]};explored=0
        context=set(context)
        for index in range(len(tokens)):
            features=_features(tokens,index,context)
            nxt=defaultdict(list)
            for (mask,previous),paths in options.items():
                for state in states:
                    if not self._allowed(previous,state,mask,roles):continue
                    kind=_type(state)
                    bit=(1<<roles.index(state.split(':',1)[1])) if kind=='B' else 0
                    new_mask=mask|bit
                    weight=self._transition_score(_type(previous),kind)+self._emission(
                        state,features,allow_transfer)
                    for score,path in paths:
                        nxt[(new_mask,state)].append((score+weight,path+(state,)))
                        explored+=1
            options={key:sorted(value,key=lambda row:(-row[0],row[1]))[:2]
                     for key,value in nxt.items()}
            if explored>100_000:
                return {'status':'search_budget','spans':{},'label':None,
                        'candidates':explored}
        finalists=[];full=(1<<len(roles))-1
        for (mask,state),paths in options.items():
            if mask!=full:continue
            finalists.extend((score+self._transition_score(_type(state),'<end>'),path)
                             for score,path in paths)
        finalists.sort(key=lambda row:(-row[0],row[1]))
        if not finalists:
            return {'status':'no_parse','spans':{},'label':None,'candidates':explored}
        winner=finalists[0][1]
        spans={};active=None;start=0
        for index,state in enumerate(winner+('O',)):
            if state.startswith('B:'):
                if active is not None:spans[active]=(start,index)
                active=state[2:];start=index
            elif state=='O' and active is not None:
                spans[active]=(start,index);active=None
            elif state.startswith('I:') and active!=state[2:]:
                return {'status':'invalid_path','spans':{},'label':None,
                        'candidates':explored}
        if len(spans)!=len(roles):
            return {'status':'incomplete_parse','spans':{},'label':None,
                    'candidates':explored}
        margin=finalists[0][0]-finalists[1][0] if len(finalists)>1 else 100.0
        if margin<1.0 and finalists[0][1]!=finalists[1][1]:
            return {'status':'ambiguous','spans':spans,'label':None,
                    'margin':margin,'candidates':explored,
                    'evidence_request':{'kind':'label_one_span','alternatives':2}}
        label=self._label_score(tokens,spans)
        return {'status':'parsed','spans':spans,'label':label,
                'margin':margin,'candidates':explored}

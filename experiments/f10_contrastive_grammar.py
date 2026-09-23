"""F-10 pilot: bounded anti-unification of grounded language constructions.

Programs are lists of literal, role and skip instructions. They are data, not
Python. Candidate construction and execution use no task or predicate names.
"""
from __future__ import annotations

import re
from collections import Counter,defaultdict
from itertools import combinations

from leobot.language import normalize
from leobot.language_acquisition import LanguageAcquisitionMixin


MAX_ROLE=8
MAX_SKIP=4
MAX_ANALYSES=32
MAX_PROGRAMS=4096


def _tokens(text):
    return [(m.group(),m.start(),m.end()) for m in
            re.finditer(r'<a\d+>|[^\W_]+|[^\w\s]',text)]


def episode(row):
    frame={'act':'assert','pred':row['predicate'],
           'args':[row['subject'],row['object']]}
    signature=LanguageAcquisitionMixin._grounding_signature(row['text'],frame)
    if signature is None:return None
    values=tuple(token for token,_,_ in _tokens(signature[0]))
    if values.count('<a0>')!=1 or values.count('<a1>')!=1:
        return None
    return {'id':row['id'],'text':row['text'],'subject':row['subject'],
            'object':row['object'],'predicate':row['predicate'],
            'surface':signature[0],'tokens':values}


def _alignment(a,b):
    n=len(a);m=len(b);dp=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n-1,-1,-1):
        for j in range(m-1,-1,-1):
            both=(10 if a[i] in ('<a0>','<a1>') else 1)+dp[i+1][j+1]
            dp[i][j]=max(both if a[i]==b[j] else -1,
                         dp[i+1][j],dp[i][j+1])
    result=[];i=j=0
    while i<n and j<m:
        weight=10 if a[i] in ('<a0>','<a1>') else 1
        if a[i]==b[j] and dp[i][j]==weight+dp[i+1][j+1]:
            result.append((i,j,a[i]));i+=1;j+=1
        elif dp[i+1][j]>=dp[i][j+1]:i+=1
        else:j+=1
    return result


def antiunify(a,b):
    left=a['tokens'];right=b['tokens']
    matched=_alignment(left,right)
    common=[token for _,_,token in matched]
    if common.count('<a0>')!=1 or common.count('<a1>')!=1:
        return None
    program=[];li=ri=-1
    for ai,bi,token in [*matched,(len(left),len(right),'<end>')]:
        gap_a=ai-li-1;gap_b=bi-ri-1
        if max(gap_a,gap_b)>MAX_SKIP:return None
        if gap_a or gap_b:
            program.append(('skip',max(gap_a,gap_b)))
        if token!='<end>':
            program.append(('role',int(token[2:-1])) if token in ('<a0>','<a1>')
                           else ('literal',token))
        li=ai;ri=bi
    if sum(kind=='literal' for kind,_ in program)<1:return None
    return tuple(program)


def parse(program,text,limit=MAX_ANALYSES):
    norm=normalize(text)
    tokens=_tokens(norm);length=len(tokens)
    solutions=[];seen=set()
    minimum=[0]*(len(program)+1)
    for index in range(len(program)-1,-1,-1):
        minimum[index]=minimum[index+1]+(program[index][0]!='skip')

    def walk(step,index,captures):
        if len(solutions)>=limit:return
        if step==len(program):
            if index!=length or set(captures)!={0,1}:return
            values=tuple(norm[tokens[start][1]:tokens[end-1][2]]
                         for start,end in (captures[0],captures[1]))
            if values not in seen:
                seen.add(values);solutions.append(values)
            return
        kind,value=program[step]
        if kind=='literal':
            if index<length and tokens[index][0]==value:
                walk(step+1,index+1,captures)
            return
        last=min(length-minimum[step+1],index+(MAX_ROLE if kind=='role' else value))
        if kind=='role':
            for end in range(index+1,last+1):
                captures[value]=(index,end)
                walk(step+1,end,captures)
                if len(solutions)>=limit:break
            captures.pop(value,None)
        else:
            for end in range(index,last+1):
                walk(step+1,end,captures)
                if len(solutions)>=limit:break

    walk(0,0,{})
    return solutions


def generate(rows,max_per_predicate=64):
    groups=defaultdict(list)
    for row in rows:
        ep=episode(row)
        if ep is not None:groups[ep['predicate']].append(ep)
    result=[];considered=0
    for pred,examples in sorted(groups.items()):
        examples=sorted(examples,key=lambda row:row['id'])
        candidates={}
        for left,right in combinations(examples,2):
            considered+=1
            program=antiunify(left,right)
            if program is None or program in candidates:continue
            pairs=(left,right)
            if all(parse(program,row['text'],limit=3)==[
                    (row['subject'],row['object'])] for row in pairs):
                candidates[program]=tuple(row['id'] for row in pairs)
            if len(candidates)>=max_per_predicate:break
        for program,sources in sorted(candidates.items(),key=lambda row:(
                -sum(kind=='literal' for kind,_ in row[0]),len(row[0]),row[0])):
            result.append({'predicate':pred,'program':program,'sources':sources})
            if len(result)>=MAX_PROGRAMS:return result,considered
    return result,considered


class ContrastiveGrammar:
    """Promote only programs supported by distinct entities and separate text."""
    def __init__(self):
        self.fit_rows=[]
        self.validation_rows=[]
        self.programs=[]
        self.index={}
        self.report={}

    @staticmethod
    def _index(programs,rows):
        frequency=Counter()
        for row in rows:
            frequency.update({token for token,_,_ in _tokens(normalize(row['text']))})
        index=defaultdict(list)
        for number,item in enumerate(programs):
            words=[value for kind,value in item['program'] if kind=='literal']
            if not words:continue
            anchor=min(words,key=lambda token:(frequency[token],token))
            index[anchor].append(number)
        return index

    @staticmethod
    def _triggered(index,text):
        observed={token for token,_,_ in _tokens(normalize(text))}
        return sorted({number for token in observed for number in index.get(token,())})

    def train(self,fit,validation):
        self.fit_rows=list(fit);self.validation_rows=list(validation)
        proposed,pairs=generate(fit)
        index=self._index(proposed,fit)
        support=defaultdict(set);verification=defaultdict(set)
        contradicted=set();valid_contradicted=set();fit_analyses=val_analyses=0
        def scan(rows,backing,bad):
            nonlocal fit_analyses,val_analyses
            for row in rows:
                target=(row['predicate'],(row['subject'],row['object']))
                for number in self._triggered(index,row['text']):
                    item=proposed[number]
                    possible=parse(item['program'],row['text'])
                    if backing is support:fit_analyses+=1
                    else:val_analyses+=1
                    if not possible:continue
                    if len(possible)==1 and (item['predicate'],possible[0])==target:
                        backing[number].add(row['id'])
                    else:bad.add(number)
        scan(fit,support,contradicted)
        scan(validation,verification,valid_contradicted)
        by_id={row['id']:row for row in fit}
        promoted=[]
        for number,item in enumerate(proposed):
            ids=support[number]
            subjects={by_id[key]['subject'] for key in ids}
            objects={by_id[key]['object'] for key in ids}
            if (number in contradicted or number in valid_contradicted or
                    len(subjects)<2 or len(objects)<2 or
                    not verification[number]):
                continue
            promoted.append({**item,'fit_support':len(ids),
                             'validation_support':len(verification[number]),
                             'dependencies':sorted(ids)})
        self.programs=promoted
        self.index=self._index(promoted,fit)
        self.report={'candidate_programs':len(proposed),'source_pairs':pairs,
                     'fit_analyses':fit_analyses,'validation_analyses':val_analyses,
                     'fit_contradicted':len(contradicted),
                     'validation_contradicted':len(valid_contradicted),
                     'promoted':len(promoted)}
        return dict(self.report)

    def predict(self,text):
        numbers=self._triggered(self.index,text)
        possibilities=set()
        for number in numbers:
            item=self.programs[number]
            for args in parse(item['program'],text):
                possibilities.add((item['predicate'],args))
                if len(possibilities)>1:
                    return {'status':'ambiguous','candidates':len(numbers)}
        if not possibilities:
            return {'status':'abstain','candidates':len(numbers)}
        pred,args=next(iter(possibilities))
        return {'status':'parsed','predicate':pred,'args':args,
                'candidates':len(numbers)}

    def correct(self,identifier,replacement):
        if not any(row['id']==identifier for row in self.fit_rows):
            return False
        self.fit_rows=[replacement if row['id']==identifier else row
                       for row in self.fit_rows]
        self.train(self.fit_rows,self.validation_rows)
        return True

    def as_dict(self):
        return {'fit_rows':self.fit_rows,'validation_rows':self.validation_rows}

    @classmethod
    def from_dict(cls,data):
        model=cls()
        if not isinstance(data,dict) or set(data)!={'fit_rows','validation_rows'}:
            raise ValueError('Episodios de gramática inválidos')
        model.train(data['fit_rows'],data['validation_rows'])
        return model

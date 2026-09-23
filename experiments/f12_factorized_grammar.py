"""F-12 pilot: learned frame and relation phrase as separate typed components."""
from __future__ import annotations

from collections import Counter,defaultdict
from time import process_time

from leobot.language import normalize
from experiments.f10_contrastive_grammar import episode,_tokens


REL='<relation>'
MAX_ROLE=8
MAX_RELATION=4
MAX_ANALYSES=32


def decompositions(row):
    observed=episode(row)
    if observed is None:return []
    tokens=observed['tokens'];result=[]
    for start in range(len(tokens)):
        for stop in range(start+1,min(len(tokens),start+MAX_RELATION)+1):
            phrase=tokens[start:stop]
            if any(token in ('<a0>','<a1>') for token in phrase):continue
            frame=tokens[:start]+(REL,)+tokens[stop:]
            result.append((frame,phrase))
    return result


def parse_frame(frame,text,limit=MAX_ANALYSES):
    norm=normalize(text);tokens=_tokens(norm);length=len(tokens)
    if frame.count('<a0>')!=1 or frame.count('<a1>')!=1 or frame.count(REL)!=1:
        return []
    minimum=[0]*(len(frame)+1)
    for i in range(len(frame)-1,-1,-1):minimum[i]=minimum[i+1]+1
    found=[];seen=set()

    def walk(step,index,slots):
        if len(found)>=limit:return
        if step==len(frame):
            if index!=length or set(slots)!={'<a0>','<a1>',REL}:return
            values=tuple(norm[tokens[slots[name][0]][1]:
                              tokens[slots[name][1]-1][2]]
                         for name in ('<a0>','<a1>',REL))
            if values not in seen:seen.add(values);found.append(values)
            return
        item=frame[step]
        if item not in ('<a0>','<a1>',REL):
            if index<length and tokens[index][0]==item:
                walk(step+1,index+1,slots)
            return
        max_width=MAX_RELATION if item==REL else MAX_ROLE
        end_limit=min(length-minimum[step+1],index+max_width)
        for end in range(index+1,end_limit+1):
            slots[item]=(index,end)
            walk(step+1,end,slots)
            if len(found)>=limit:break
        slots.pop(item,None)

    walk(0,0,{})
    return found


class FactorizedGrammar:
    def __init__(self):
        self.fit_rows=[];self.validation_rows=[]
        self.frames={};self.lexicon={};self.index={}
        self.report={}

    @staticmethod
    def _components(rows):
        frame_support=defaultdict(lambda:defaultdict(set))
        lex_support=defaultdict(lambda:defaultdict(set))
        by_id={row['id']:row for row in rows}
        candidates=0
        for row in rows:
            for frame,phrase in decompositions(row):
                candidates+=1
                target=(row['subject'],row['object'],' '.join(phrase))
                if parse_frame(frame,row['text'],limit=3)!=[target]:continue
                frame_support[frame][row['predicate']].add(row['id'])
                lex_support[phrase][(row['predicate'],frame)].add(row['id'])
        return frame_support,lex_support,by_id,candidates

    @staticmethod
    def _compile(frame_support,lex_support,by_id,min_support):
        frames={}
        for frame,by_pred in frame_support.items():
            supported={pred:ids for pred,ids in by_pred.items() if
                       len({by_id[i]['subject'] for i in ids})>=min_support and
                       len({by_id[i]['object'] for i in ids})>=min_support}
            if len(supported)>=2:
                frames[frame]={pred:sorted(ids) for pred,ids in supported.items()}
        lexicon={}
        for phrase,by_pair in lex_support.items():
            options=defaultdict(set);dependencies=defaultdict(set)
            for (pred,frame),ids in by_pair.items():
                if frame in frames:
                    options[pred].add(frame);dependencies[pred].update(ids)
            if len(options)!=1:continue
            pred=next(iter(options))
            if len(options[pred])<2:continue
            subjects={by_id[key]['subject'] for key in dependencies[pred]}
            objects={by_id[key]['object'] for key in dependencies[pred]}
            if len(subjects)<min_support or len(objects)<min_support:continue
            lexicon[phrase]={'predicate':pred,'frames':len(options[pred]),
                             'dependencies':sorted(dependencies[pred])}
        frequency=Counter()
        for row in by_id.values():
            frequency.update({token for token,_,_ in _tokens(normalize(row['text']))})
        index=defaultdict(list)
        for frame in frames:
            words=[word for word in frame if word not in ('<a0>','<a1>',REL)]
            if not words:continue
            anchor=min(words,key=lambda word:(frequency[word],word))
            index[anchor].append(frame)
        return frames,lexicon,dict(index)

    @staticmethod
    def _predict(text,frames,lexicon,index):
        observed={token for token,_,_ in _tokens(normalize(text))}
        candidates={frame for token in observed for frame in index.get(token,())}
        answers=set();analyses=0
        for frame in sorted(candidates):
            for subject,obj,phrase in parse_frame(frame,text):
                analyses+=1
                entry=lexicon.get(tuple(token for token,_,_ in _tokens(phrase)))
                if entry:
                    answers.add((entry['predicate'],subject,obj))
                if len(answers)>1:
                    return {'status':'ambiguous','candidates':len(candidates),
                            'analyses':analyses}
        if not answers:
            return {'status':'abstain','candidates':len(candidates),'analyses':analyses}
        pred,subject,obj=next(iter(answers))
        return {'status':'parsed','predicate':pred,'args':(subject,obj),
                'candidates':len(candidates),'analyses':analyses}

    def train(self,fit,validation):
        self.fit_rows=list(fit);self.validation_rows=list(validation)
        frame_support,lex_support,by_id,generated=self._components(fit)
        best=None;options=[]
        for support in (2,3,4):
            frames,lexicon,index=self._compile(frame_support,lex_support,
                                                by_id,support)
            correct=attempts=0
            for row in validation:
                result=self._predict(row['text'],frames,lexicon,index)
                if result['status']!='parsed':continue
                attempts+=1
                correct+=result['predicate']==row['predicate'] and result['args']==(
                    row['subject'],row['object'])
            precision=correct/attempts if attempts else 0.0
            options.append({'min_support':support,'frames':len(frames),
                            'expressions':len(lexicon),'correct':correct,
                            'attempts':attempts,'precision':round(precision,6)})
            if attempts>=2 and correct>=2 and precision>=0.8:
                rank=(-correct,-precision,support)
                if best is None or rank<best[0]:best=(rank,frames,lexicon,index,support)
        if best is None:
            self.frames={};self.lexicon={};self.index={};selected=None
        else:
            _,self.frames,self.lexicon,self.index,selected=best
        self.report={'status':'fitted' if best else 'rejected',
                     'generated_decompositions':generated,
                     'candidate_frames':len(frame_support),
                     'candidate_expressions':len(lex_support),
                     'validation_options':options,'selected_support':selected,
                     'promoted_frames':len(self.frames),
                     'promoted_expressions':len(self.lexicon)}
        return dict(self.report)

    def predict(self,text):
        return self._predict(text,self.frames,self.lexicon,self.index)

    def correct(self,identifier,replacement):
        if not any(row['id']==identifier for row in self.fit_rows):return False
        rows=[replacement if row['id']==identifier else row for row in self.fit_rows]
        self.train(rows,self.validation_rows)
        return True

    def as_dict(self):
        return {'fit_rows':self.fit_rows,'validation_rows':self.validation_rows}

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict) or set(data)!={'fit_rows','validation_rows'}:
            raise ValueError('Experiencias inválidas')
        model=cls();model.train(data['fit_rows'],data['validation_rows'])
        return model

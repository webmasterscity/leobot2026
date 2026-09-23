"""V4.1: learn a multi-role concept through one unmentioned existential event node.

Ablation removes every candidate body containing the hidden variable.  The
remaining V4.0-style schema language must then fail on the same frozen examples.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.core import Atom, Engine, KnowledgeBase
from leobot.schemas import OpenArityConceptGrounder

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v41_existential_event_schema.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def world(count=140,junk=5000):
    kb=KnowledgeBase()
    for i in range(count):
        event=f'evento{i}'
        kb.add(Atom('actor',(event,f'persona{i}')))
        kb.add(Atom('tema',(event,f'objeto{i}')))
        kb.add(Atom('sitio',(event,f'lugar{i}')))
    for j in range(junk):
        kb.add(Atom(f'junk{j}',(f'jx{j}',f'jy{j}')))
    return kb


def training():
    return [
        'persona0 vincula objeto0 en lugar0',
        'persona1 vincula objeto1 en lugar1',
        'persona0 no vincula objeto0 en lugar1',
        'persona0 no vincula objeto1 en lugar0',
        'persona1 no vincula objeto0 en lugar0',
    ]


def ablation_without_existential(learner, session):
    examples=learner._examples(session)
    predicates=learner._relevant_predicates(examples)
    engine=Engine(learner.kb)
    evaluated=0;solutions=[];rejected=0
    started=perf_counter()
    mention_count=len(next(iter(examples)))
    from itertools import combinations
    for arity in range(1,mention_count+1):
        for projection in combinations(range(mention_count),arity):
            labels=learner._projected_labels(examples,projection)
            if any(len(v)>1 for v in labels.values()):
                rejected+=1;continue
            for body in learner._bodies(arity,predicates):
                if any(i < 0 for _,roles in body for i in roles):
                    continue
                evaluated+=1;ok=True
                for args,labs in labels.items():
                    if learner._body_holds(engine,body,args) != next(iter(labs)):
                        ok=False;break
                if ok:
                    solutions.append({'arity':arity,'projection':list(projection),'body':body})
    return {'solutions':len(solutions),'candidates_evaluated':evaluated,
            'projection_rejections':rejected,'ms':(perf_counter()-started)*1000}


def main():
    before=code_hash();kb=world();g=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
    reports=[]
    for text in training(): reports.append(g.observe(text))
    final=reports[-1]['learning'];session=g.sessions['<e0> vincula <e1> en <e2>']
    ablation=ablation_without_existential(g,session)

    positive=negative=0;times=[]
    for i in range(10,110):
        t=perf_counter();rp=g.resolve(f'persona{i} vincula objeto{i} en lugar{i}');times.append((perf_counter()-t)*1000)
        t=perf_counter();rn=g.resolve(f'persona{i} vincula objeto{i} en lugar{(i+1)%140}');times.append((perf_counter()-t)*1000)
        positive += rp['status']=='entailed';negative += rn['status']!='entailed'

    mentioned_text=' '.join(training())
    hidden_mentions=sum(f'evento{i}' in mentioned_text for i in range(140))
    memory={tuple(o['mentions']) for o in session['observations'] if o['positive']}
    episodic=sum((f'persona{i}',f'objeto{i}',f'lugar{i}') in memory for i in range(10,110))
    after=code_hash()
    report={
        'version':'0.4.1',
        'experiment':'existential_reified_event_schema',
        'code_hash_before':before,
        'learned':{
            'status':reports[-1]['status'],'arity':final.get('arity'),'projection':final.get('projection'),
            'selected':final.get('selected'),'candidates_evaluated':final.get('candidates_evaluated'),
            'projection_rejections':final.get('projection_rejections'),'ms':final.get('ms'),
            'predicate_selected':final.get('predicates'),'unrelated_predicates_in_world':5000,
            'hidden_event_mentions_in_training_text':hidden_mentions,
            'heldout_positive':positive,'heldout_positive_cases':100,
            'heldout_negative_rejected':negative,'heldout_negative_cases':100,
            'median_query_ms':median(times),
        },
        'controls':{
            'v40_schema_language_without_existential':ablation,
            'episodic_memory_positive_heldout_hits':episodic,
            'episodic_memory_positive_heldout_cases':100,
        },
        'code_hash_after':after,'code_unchanged_during_evaluation':before==after,
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

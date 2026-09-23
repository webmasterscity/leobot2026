"""V4.0: infer 1--3 semantic roles and role remapping from natural examples.

The experiment freezes the implementation, teaches only through the learner's
normal natural-language observation interface, and compares against (a) exact
episodic memory, (b) the previous binary concept parser, and (c) the same schema
search with the correct role projection supplied manually.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot.concepts import ConceptGrounder
from leobot.core import Atom, Engine, KnowledgeBase
from leobot.schemas import OpenArityConceptGrounder

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v40_open_arity_schema.json'


def code_hash() -> str:
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(b'\0'); h.update(path.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def ternary_world(count=140, junk=5000):
    kb=KnowledgeBase()
    for i in range(count):
        kb.add(Atom('posee',(f'persona{i}',f'objeto{i}')))
        kb.add(Atom('ubicado',(f'objeto{i}',f'lugar{i}')))
    for j in range(junk):
        kb.add(Atom(f'junk{j}',(f'jx{j}',f'jy{j}')))
    return kb


def teach_ternary(learner):
    examples=[
        'persona0 enlaza objeto0 con lugar0',
        'persona1 enlaza objeto1 con lugar1',
        'persona0 no enlaza objeto0 con lugar1',
        'persona0 no enlaza objeto1 con lugar0',
        'persona1 no enlaza objeto0 con lugar0',
    ]
    reports=[]
    for text in examples:
        reports.append(learner.observe(text))
    return examples,reports


def heldout(learner, template_positive, template_negative, start=10, count=100):
    positive=negative=0; times=[]
    for i in range(start,start+count):
        t0=perf_counter(); rp=learner.resolve(template_positive(i)); times.append((perf_counter()-t0)*1000)
        t0=perf_counter(); rn=learner.resolve(template_negative(i)); times.append((perf_counter()-t0)*1000)
        positive += rp.get('status')=='entailed'
        negative += rn.get('status')!='entailed'
    return {'positive_cases':count,'positive_entailed':positive,
            'negative_cases':count,'negative_rejected':negative,'median_ms':median(times)}


def manual_projection_control(learner, session, projection):
    examples=learner._examples(session)
    labels=learner._projected_labels(examples,tuple(projection))
    predicates=learner._relevant_predicates(examples)
    bodies=learner._bodies(len(projection),predicates)
    engine=Engine(learner.kb); evaluated=0; matches=[]
    started=perf_counter()
    for body in bodies:
        evaluated += 1; ok=True
        for args,labs in labels.items():
            label=next(iter(labs))
            if learner._body_holds(engine,body,args) != label:
                ok=False;break
        if ok:
            text=' & '.join(p+'('+','.join(f'r{i}' for i in roles)+')' for p,roles in body)
            matches.append(text)
    return {'projection_supplied':list(projection),'candidates_evaluated':evaluated,
            'solutions':sorted(matches),'ms':(perf_counter()-started)*1000}


def unary_experiment():
    kb=KnowledgeBase()
    for i in range(120): kb.add(Atom('activo',(f'activo{i}',)))
    for i in range(120): kb.add(Atom('persona',(f'inactivo{i}',)))
    for city in ('norte','sur'): kb.add(Atom('zona',(city,)))
    for obj in ('caja','mesa'): kb.add(Atom('objeto',(obj,)))
    g=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
    train=['norte activo0 junto a caja destaca','sur activo1 junto a mesa destaca',
           'norte inactivo0 junto a mesa no destaca','sur inactivo1 junto a caja no destaca']
    reports=[g.observe(x) for x in train]
    good=bad=0
    for i in range(10,110):
        good += g.resolve(f'norte activo{i} junto a caja destaca')['status']=='entailed'
        bad += g.resolve(f'sur inactivo{i} junto a mesa destaca')['status']!='entailed'
    final=reports[-1]['learning']
    return {'arity':final.get('arity'),'projection':final.get('projection'),'selected':final.get('selected'),
            'heldout_positive':good,'heldout_negative_rejected':bad}


def binary_experiment():
    kb=KnowledgeBase()
    for i in range(120): kb.add(Atom('mentor',(f'mentor{i}',f'alumno{i}')))
    for city in ('norte','sur'): kb.add(Atom('zona',(city,)))
    g=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
    train=['mentor0 en norte guia alumno0','mentor1 en sur guia alumno1',
           'mentor0 en norte no guia alumno1','mentor1 en norte no guia alumno0']
    reports=[g.observe(x) for x in train]
    good=bad=0
    for i in range(10,110):
        good += g.resolve(f'mentor{i} en norte guia alumno{i}')['status']=='entailed'
        bad += g.resolve(f'mentor{i} en sur guia alumno{i+1}')['status']!='entailed'
    final=reports[-1]['learning']
    return {'arity':final.get('arity'),'projection':final.get('projection'),'selected':final.get('selected'),
            'heldout_positive':good,'heldout_negative_rejected':bad}


def main():
    before=code_hash()
    kb=ternary_world()
    learner=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
    training,reports=teach_ternary(learner)
    final=reports[-1]['learning']
    session=learner.sessions['<e0> enlaza <e1> con <e2>']

    # Exact episodic memory sees only the training tuples and cannot answer new ones.
    memorized={tuple(o['mentions']) for o in session['observations'] if o['positive']}
    episodic_hits=sum((f'persona{i}',f'objeto{i}',f'lugar{i}') in memorized for i in range(10,110))

    binary=ConceptGrounder(kb)
    binary_unrecognized=sum(binary.parse(text) is None for text in training)

    transfer=heldout(
        learner,
        lambda i:f'persona{i} enlaza objeto{i} con lugar{i}',
        lambda i:f'persona{i} enlaza objeto{i} con lugar{(i+1)%140}',
    )
    manual=manual_projection_control(learner,session,[0,1,2])

    # New wording reverses surface order: place, object, person.
    alias_train=[
        'en lugar0 objeto0 corresponde a persona0',
        'en lugar1 objeto1 corresponde a persona1',
        'en lugar1 objeto0 no corresponde a persona0',
        'en lugar0 objeto1 no corresponde a persona0',
    ]
    alias_reports=[learner.observe(x) for x in alias_train]
    alias_transfer=heldout(
        learner,
        lambda i:f'en lugar{i} objeto{i} corresponde a persona{i}',
        lambda i:f'en lugar{(i+1)%140} objeto{i} corresponde a persona{i}',
    )

    after=code_hash()
    report={
        'version':'0.4.0',
        'experiment':'open_arity_schema_and_role_remapping',
        'code_hash_before':before,
        'ternary':{
            'status':reports[-1]['status'],
            'arity':final.get('arity'),'projection':final.get('projection'),
            'selected':final.get('selected'),
            'projection_rejections':final.get('projection_rejections'),
            'candidates_evaluated':final.get('candidates_evaluated'),
            'predicate_selected':final.get('predicates'),
            'unrelated_predicates_in_world':5000,
            'heldout':transfer,
        },
        'controls':{
            'binary_v39_unrecognized_training_examples':binary_unrecognized,
            'binary_v39_training_examples':len(training),
            'episodic_memory_positive_heldout_hits':episodic_hits,
            'episodic_memory_positive_heldout_cases':100,
            'manual_arity_roles':manual,
        },
        'role_alias':{
            'status':alias_reports[-1]['status'],
            'mapping':alias_reports[-1].get('alias',{}).get('mapping'),
            'root_target':alias_reports[-1].get('alias',{}).get('target'),
            'heldout':alias_transfer,
        },
        'unary':unary_experiment(),
        'binary_from_three_mentions':binary_experiment(),
        'code_hash_after':after,
        'code_unchanged_during_evaluation':before==after,
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

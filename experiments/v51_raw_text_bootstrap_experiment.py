from __future__ import annotations
import hashlib, json
from pathlib import Path
from statistics import median
from time import perf_counter
from leobot.bot import Bot
from leobot.core import KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v51_raw_text_bootstrap.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def raw_support(bot):
    rows_a=[
        'sujeto alfa enlaza modulo rojo',
        'sujeto beta enlaza modulo azul',
        'sujeto gamma enlaza modulo verde',
    ]
    rows_b=[
        'modulo rojo reposa zona norte',
        'modulo azul reposa zona sur',
        'modulo verde reposa zona este',
    ]
    ra=[bot.respond(x) for x in rows_a]
    rb=[bot.respond(x) for x in rows_b]
    return rows_a,rows_b,ra,rb

def teach_composition(bot):
    texts=[
        'sujeto alfa coordina modulo rojo en zona norte',
        'sujeto beta coordina modulo azul en zona sur',
        # P(person,obj) true but Q(obj,zone) false.
        'sujeto alfa no coordina modulo rojo en zona sur',
        # Q(obj,zone) true but P(person,obj) false.
        'sujeto alfa no coordina modulo azul en zona sur',
        # person->zone is true through another object, but the mentioned object is wrong.
        'sujeto alfa no coordina modulo azul en zona norte',
    ]
    return texts,[bot.observe_schema_statement(x) for x in texts]

def main():
    before=code_hash()
    bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
    assert bot.kb.stats()['facts']==0
    a,b,ra,rb=raw_support(bot)
    assert ra[-1]['status']=='raw_relation_learned',ra[-1]
    assert rb[-1]['status']=='raw_relation_learned',rb[-1]
    pa,pb=ra[-1]['predicate'],rb[-1]['predicate']
    train,reports=teach_composition(bot)
    learned=reports[-1]
    assert learned['status']=='schema_learned',learned
    selected=learned['learning']['selected']
    # Held-out: no ternary sentence is taught. Only the two learned raw surfaces
    # receive novel entities; the composed relation must then be inferred.
    correct=wrong_rejected=stored=0; times=[]
    for i in range(100):
        person=f'nuevo{i}'
        obj=f'obj{i}'
        zone=f'lugar{i}'
        t0=perf_counter();x=bot.respond(f'sujeto {person} enlaza modulo {obj}');times.append((perf_counter()-t0)*1000)
        t0=perf_counter();y=bot.respond(f'modulo {obj} reposa zona {zone}');times.append((perf_counter()-t0)*1000)
        stored += x.get('status')=='stored' and y.get('status')=='stored'
        good=bot.query_schema(f'sujeto {person} coordina modulo {obj} en zona {zone}')
        bad=bot.query_schema(f'sujeto {person} coordina modulo {obj} en zona lugar{(i+1)%100}')
        correct += good.get('status')=='entailed'
        wrong_rejected += bad.get('status')!='entailed'
    # Same text and budget, but raw primitive promotion disabled: cannot bootstrap.
    ctl=Bot(KnowledgeBase(),raw_relation_min_support=999,allow_extensional_grounding=False)
    ca,cb,cra,crb=raw_support(ctl)
    ctrain,creports=teach_composition(ctl)
    control_new=[]
    for i in range(20):
        control_new.append(ctl.respond(f'sujeto control{i} enlaza modulo control{i}').get('status'))
    after=code_hash()
    report={
      'version':'0.5.1-hybrid-eval',
      'experiment':'zero_ontology_raw_text_to_composed_relation',
      'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
      'initial_facts':0,
      'raw_primitives':{
        'learned':2,'predicates':[pa,pb],
        'support_statuses_a':[x.get('status') for x in ra],
        'support_statuses_b':[x.get('status') for x in rb],
      },
      'composition':{
        'status':learned.get('status'),'arity':learned.get('learning',{}).get('arity'),
        'selected':selected,'uses_both_raw_primitives':pa in selected and pb in selected,
      },
      'heldout':{
        'novel_pairs_stored':stored,'cases':100,
        'composed_positive_entailed':correct,'positive_cases':100,
        'mismatched_rejected':wrong_rejected,'negative_cases':100,
        'median_raw_assertion_ms':median(times),
      },
      'control_no_raw_promotion':{
        'primitive_promotions':len(ctl.raw_relation_promotions),
        'composition_last_status':creports[-1].get('status'),
        'novel_statuses':sorted(set(control_new)),
      },
      'limits':[
        'La induccion cruda sigue limitada a primitivas binarias con dos spans y anclas compartidas.',
        'El concepto ternario se aprende desde ejemplos contrastivos sobre primitivas ya adquiridas; no es comprension abierta de documentos.',
        'Evaluacion interna sintetica; no demuestra AGI/ASI.'
      ]
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

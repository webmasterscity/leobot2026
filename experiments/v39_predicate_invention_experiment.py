#!/usr/bin/env python3
"""V3.9: autonomous bounded predicate invention and reuse.

A target relation whose shortest expression is longer than the learner's direct
path budget is learned by inventing one unnamed intermediate relation.  The
invented helper must then reduce the representation/search needed by a different
target while new invention is disabled.  Controls separate memory, direct-depth
budget, and a deeper non-inventing learner.
"""
from __future__ import annotations
import hashlib,json,tempfile
from pathlib import Path
from statistics import median
from time import perf_counter
from leobot import Bot,Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v39_predicate_invention.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def add4(b,prefix):
    n=[f'{prefix}{i}' for i in range(5)]
    for pred,a,c in [('r',n[0],n[1]),('s',n[1],n[2]),('r',n[2],n[3]),('s',n[3],n[4])]:
        b.kb.add(Atom(pred,(a,c)),'world')

def add3(b,prefix):
    n=[f'{prefix}x{i}' for i in range(4)]
    for pred,a,c in [('r',n[0],n[1]),('s',n[1],n[2]),('t',n[2],n[3])]:
        b.kb.add(Atom(pred,(a,c)),'world')

def build_world(b,n_hold=100):
    for pref in ('a','b','c','d','e'):add4(b,pref)
    for pref in ('u','v','w','z'):add3(b,pref)
    p4=[];p3=[];neg=[]
    for i in range(n_hold):
        pref=f'h4_{i}_';add4(b,pref);p4.append((f'{pref}0',f'{pref}4'))
        pref3=f'h3_{i}_';add3(b,pref3);p3.append((f'{pref3}x0',f'{pref3}x3'))
        x,y=f'nx{i}',f'ny{i}';b.kb.add(Atom('other',(x,y)),'negative');neg.append((x,y))
    # fixed negative entities used in training
    for x,y in [('n1','n2'),('n3','n4'),('n5','n6'),('n7','n8')]:b.kb.add(Atom('other',(x,y)),'negative')
    return p4,p3,neg

def teach4(b):
    out=None
    for text in ('A0 abarca a A4.','B0 abarca a B4.','N1 no abarca a N2.','N3 no abarca a N4.'):
        out=b.observe_concept_statement(text)
    return out

def teach3(b):
    out=None
    for text in ('Ux0 alcanza a Ux3.','Vx0 alcanza a Vx3.','N5 no alcanza a N6.','N7 no alcanza a N8.'):
        out=b.observe_concept_statement(text)
    return out

def eval_surface(b,fmt,pairs):
    ok=0;times=[]
    for a,c in pairs:
        t=perf_counter();r=b.query_concept(fmt.format(a=a,b=c)+'?');times.append((perf_counter()-t)*1000)
        ok += r.get('status')=='entailed'
    return {'cases':len(pairs),'entailed':ok,'median_ms':median(times) if times else 0.0}

def main():
    hb=code_hash()
    full=Bot();full.concepts.max_relation_length=2
    p4,p3,neg=build_world(full)
    first=teach4(full);first_eval=eval_surface(full,'{a} abarca a {b}',p4)
    helper=first.get('learning',{}).get('invented_predicate')

    # Same direct budget, invention disabled.
    tight=Bot();tight.concepts.max_relation_length=2;tight.concepts.allow_predicate_invention=False
    tp4,_,_=build_world(tight);tight_first=teach4(tight);tight_eval=eval_surface(tight,'{a} abarca a {b}',tp4)

    # Deeper direct search shows the target is representable without invention,
    # but under a larger compositional budget.
    deep=Bot();deep.concepts.max_relation_length=4;deep.concepts.allow_predicate_invention=False
    dp4,_,_=build_world(deep);deep_first=teach4(deep);deep_eval=eval_surface(deep,'{a} abarca a {b}',dp4)

    # Persist the helper before using it on another target.
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'state.json';full.save(path);transfer=Bot.load(path)
        transfer.concepts.max_relation_length=2
        transfer.concepts.allow_predicate_invention=False
        second=teach3(transfer);second_eval=eval_surface(transfer,'{a} alcanza a {b}',p3)
        helper_survived=any(r.head.pred==helper for r in transfer.kb.rules.values()) if helper else False

    # Second target from scratch under same depth and no invention.
    c2=Bot();c2.concepts.max_relation_length=2;c2.concepts.allow_predicate_invention=False
    _,cp3,_=build_world(c2);second_control=teach3(c2);second_control_eval=eval_surface(c2,'{a} alcanza a {b}',cp3)

    # A deeper direct baseline for the second target.
    d2=Bot();d2.concepts.max_relation_length=3;d2.concepts.allow_predicate_invention=False
    _,dp3,_=build_world(d2);second_deep=teach3(d2);second_deep_eval=eval_surface(d2,'{a} alcanza a {b}',dp3)

    ha=code_hash()
    report={
      'version':'0.3.9','experiment':'bounded_predicate_invention_and_cross_target_reuse',
      'code_hash_before':hb,
      'first_target_with_invention':{
        'status':first['status'],'selected':first.get('learning',{}).get('selected'),
        'invented_predicate':helper,'invention_definition':first.get('learning',{}).get('invention_definition'),
        'invention_attempts':first.get('learning',{}).get('invention_attempts'),
        'base_candidates':first.get('learning',{}).get('invention_base_candidates'),
        'total_target_candidates':first.get('learning',{}).get('invention_total_target_candidates'),
        'total_invention_ms':first.get('learning',{}).get('invention_total_ms'),
        'heldout':first_eval,
      },
      'first_target_tight_no_invention':{
        'status':tight_first['status'],'selected':tight_first.get('learning',{}).get('selected'),
        'candidates':tight_first.get('learning',{}).get('candidates'),'heldout':tight_eval,
      },
      'first_target_deep_no_invention':{
        'status':deep_first['status'],'selected':deep_first.get('learning',{}).get('selected'),
        'candidates':deep_first.get('learning',{}).get('candidates'),'ms':deep_first.get('learning',{}).get('ms'),
        'heldout':deep_eval,
      },
      'second_target_reusing_invented_helper_no_new_invention':{
        'status':second['status'],'selected':second.get('learning',{}).get('selected'),
        'candidates':second.get('learning',{}).get('candidates'),'ms':second.get('learning',{}).get('ms'),
        'helper_survived_restart':helper_survived,'heldout':second_eval,
      },
      'second_target_tight_without_helper':{
        'status':second_control['status'],'selected':second_control.get('learning',{}).get('selected'),
        'candidates':second_control.get('learning',{}).get('candidates'),'heldout':second_control_eval,
      },
      'second_target_deep_without_helper':{
        'status':second_deep['status'],'selected':second_deep.get('learning',{}).get('selected'),
        'candidates':second_deep.get('learning',{}).get('candidates'),'ms':second_deep.get('learning',{}).get('ms'),
        'heldout':second_deep_eval,
      },
      'code_hash_after':ha,'code_unchanged_during_evaluation':hb==ha,
    }
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

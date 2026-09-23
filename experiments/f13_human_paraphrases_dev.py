"""F-13 frozen-engine education with independent human paraphrases of facts."""
from __future__ import annotations

import json
import resource
import statistics
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path

from experiments.f6e_human_text_grounding import BASE,CATEGORIES,entity
from experiments.f6f_anchored_constructions_pilot import (
    AnchoredConstructions,evaluate as old_evaluate,correction_probe,
)
from experiments.f7_typed_sequences_dev import git
from experiments.f12_factor_inventory import partition as f12_partition


ROOT=Path(__file__).resolve().parents[1]


def source_rows():
    rows=[];sources={};total=0
    for category in CATEGORIES:
        name=f'train/1triples/{category}_allSolutions.xml'
        with urllib.request.urlopen(f'{BASE}/{name}',timeout=15) as response:
            data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise RuntimeError('Fuente excede el tope')
        total+=len(data);sources[name]=sha256(data).hexdigest()
        if total>32*1024*1024:raise RuntimeError('Fuentes exceden el tope')
        root=ET.fromstring(data)
        for entry in root.findall('entries/entry'):
            triples=[node.text for node in entry.findall('modifiedtripleset/mtriple')
                     if node.text]
            if len(triples)!=1:continue
            parts=[part.strip() for part in triples[0].split(' | ')]
            if len(parts)!=3:continue
            subject,pred,obj=parts
            lexicalizations=list(dict.fromkeys(node.text.strip() for node in
                entry.findall('lex') if node.attrib.get('comment')=='good' and
                node.text and node.text.strip()))
            identifier=category+':'+entry.attrib.get('eid','')
            if not lexicalizations or identifier==category+':':continue
            subject=entity(subject);obj=entity(obj)
            if not subject or not obj:continue
            rows.append({'id':identifier,'category':category,'subject':subject,
                         'predicate':pred,'object':obj,'texts':lexicalizations,
                         'text':lexicalizations[0]})
    return rows,sources,total


def split(rows,tree):
    _,f12_val,f12_held,_=f12_partition(rows,tree)
    # f12_partition already excludes every earlier development partition.
    prior={row['id'] for row in (*f12_val,*f12_held)}
    # Include all earlier evaluation ids, which f12_partition filtered when it
    # built its available set. Reconstruct through the same published selectors.
    from experiments.f6f_anchored_constructions_pilot import train_partition
    from experiments.f6g_learned_normalization_pilot import partition as f6g_partition
    from experiments.f7_typed_sequences_dev import select_webnlg
    from experiments.f8_span_programs_dev import split_web
    from experiments.f10_pattern_ceiling import split as f10_split
    from experiments.f11_active_feedback_dev import split as f11_split
    prior.update(row['id'] for row in train_partition(rows,tree)[1])
    prior.update(row['id'] for row in f6g_partition(rows,tree)[2])
    prior.update(row['id'] for row in select_webnlg(rows,tree)[1])
    prior.update(row['id'] for row in split_web(rows,tree)[2])
    _,f10_val,f10_held,_=f10_split(rows,tree)
    _,_,f11_val,f11_held,_=f11_split(rows,tree)
    prior.update(row['id'] for row in (*f10_val,*f10_held,*f11_val,*f11_held))
    ranked=sorted((row for row in rows if row['id'] not in prior),
       key=lambda row:(sha256((tree+':F-13:web:'+row['id']).encode()).hexdigest(),
                       row['id']))
    held=[];used=set()
    for row in ranked:
        if row['subject'] in used or row['object'] in used:continue
        held.append(row);used.update((row['subject'],row['object']))
        if len(held)==128:break
    held_ids={row['id'] for row in held};validation=[]
    for row in ranked:
        if row['id'] in held_ids or row['subject'] in used or row['object'] in used:
            continue
        validation.append(row);used.update((row['subject'],row['object']))
        if len(validation)==64:break
    reserved={row['id'] for row in (*held,*validation)}
    taught=[row for row in ranked if row['id'] not in reserved and
            row['subject'] not in used and row['object'] not in used][:1000]
    return taught,validation,held,len(prior)


def variant_rows(rows,tree):
    selected=[]
    for row in rows:
        digit=int(sha256((tree+':F-13:variant:'+row['id']).encode()).hexdigest()[:8],16)
        selected.append({**row,'text':row['texts'][digit%len(row['texts'])]})
    return selected


def train(rows,variants):
    model=AnchoredConstructions();texts=0
    tick=time.process_time()
    for row in rows:
        for index,text in enumerate(row['texts'][:variants]):
            model.observe({'id':row['id']+':lex:'+str(index),'text':text,
                           'subject':row['subject'],'object':row['object'],
                           'predicate':row['predicate']})
            texts+=1
    observation_cpu=time.process_time()-tick
    tick=time.process_time();report=model.compile()
    compilation_cpu=time.process_time()-tick
    return model,{**report,'facts':len(rows),'texts_offered':texts,
                  'observation_cpu_s':round(observation_cpu,6),
                  'compilation_cpu_s':round(compilation_cpu,6)}


def evaluate_all_variants(model,rows):
    triples=attempts=wrong=0;total=0;times=[]
    for row in rows:
        for text in row['texts'][:3]:
            total+=1;tick=time.perf_counter()
            result=model.language.parse(text)
            times.append((time.perf_counter()-tick)*1000)
            if result['status']!='parsed':continue
            attempts+=1
            exact=(result['frame'].get('pred')==row['predicate'] and
                   result['frame'].get('args')==[row['subject'],row['object']])
            triples+=exact;wrong+=not exact
    times.sort()
    return {'total_texts':total,'correct':triples,'attempts':attempts,
            'wrong_confident':wrong,'precision':round(triples/attempts,6)
            if attempts else None,'p95_ms':round(times[(95*len(times)+99)//100-1],5)}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    rows,sources,total_bytes=source_rows()
    taught,validation,held,excluded=split(rows,tree)
    if len(held)<128 or len(validation)<64 or len(taught)<250:
        raise RuntimeError('Partición insuficiente')
    selected=variant_rows(held,tree)
    stages=[];last=None;baseline=None
    for n in (250,500,750,1000):
        if len(taught)<n and n!=1000:continue
        subset=taught[:min(n,len(taught))]
        model,learning=train(subset,3)
        result=old_evaluate(model,selected)
        control,control_learning=train(subset,1)
        control_result=old_evaluate(control,selected)
        stages.append({'facts':len(subset),'treatment_learning':learning,
                       'treatment':result,'single_learning':control_learning,
                       'single':control_result})
        last=model;baseline=control
    if not stages:raise RuntimeError('Sin hitos de enseñanza')
    treatment=stages[-1]['treatment'];single=stages[-1]['single']
    last_all=evaluate_all_variants(last,held)
    single_all=evaluate_all_variants(baseline,held)
    last.language.max_rewrite_steps=0
    no_rewrite=old_evaluate(last,selected)
    last.language.max_rewrite_steps=3
    correction=(correction_probe(AnchoredConstructions.from_dict(last.as_dict()))
                if last.promoted else None)
    tick=time.process_time()
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'learned.json'
        path.write_text(json.dumps(last.as_dict(),ensure_ascii=False),encoding='utf8')
        restored=AnchoredConstructions.from_dict(json.loads(path.read_text(encoding='utf8')))
        stored_bytes=path.stat().st_size
    restart_cpu=time.process_time()-tick
    restart=old_evaluate(restored,selected)
    restart_same=(restart['correct']==treatment['correct'] and
                  restart['attempts']==treatment['attempts'])
    preliminary=(treatment['correct']>=20 and treatment['attempts']>0 and
                 treatment['precision']>=0.8 and
                 treatment['correct']>=single['correct']+5 and
                 treatment['correct']>=no_rewrite['correct']+5 and
                 restart_same and correction and
                 treatment['p95_ms']<=10 and
                 stages[-1]['treatment_learning']['observation_cpu_s']+
                 stages[-1]['treatment_learning']['compilation_cpu_s']<=3*(
                     stages[-1]['single_learning']['observation_cpu_s']+
                     stages[-1]['single_learning']['compilation_cpu_s']))
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'preregistration':'prereg/F-13-parafrasis-humanas-mismo-hecho.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'source_hashes':sources,'source_bytes':total_bytes,
            'source_facts':len(rows),'excluded_previous_development_ids':excluded,
            'fit_entries':len(taught),'validation_entries':len(validation),
            'heldout_entries':len(held),
            'fit_with_multiple_lexicalizations':sum(len(row['texts'])>=2 for row in taught),
            'stages':stages,'treatment_all_variants':last_all,
            'single_all_variants':single_all,'no_rewrite':no_rewrite,
            'correction':correction,'restart_same':restart_same,
            'restart_cpu_s':round(restart_cpu,6),'stored_bytes':stored_bytes,
            'preliminary_gate_passed':bool(preliminary and unchanged),
            'adversarial_controls':'pending_if_preliminary_passes',
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f13_paraphrases_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('source_hashes','stages')}
                     |{'stages':[(stage['facts'],stage['treatment']['correct'],
                                  stage['treatment']['attempts'],
                                  stage['single']['correct'])
                                 for stage in stages]},ensure_ascii=False))


if __name__=='__main__':main()

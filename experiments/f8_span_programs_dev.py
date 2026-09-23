"""F-8 development gate: one safe span-program search on two human corpora."""
from __future__ import annotations

import json
import random
import resource
import statistics
import tempfile
import time
from hashlib import sha256
from pathlib import Path

from experiments.f4_feedback_span_pilot import select_distinct
from experiments.f6e_human_text_grounding import download_split as web_download
from experiments.f7_typed_sequences_dev import (
    git,locate,ranked_sentences,select_sqac as f7_sqac_select,
    sqac_download,sqac_flatten,tokens,webnlg_episode,sqac_episode,
)
from experiments.f7_segmental_learner import SegmentalLearner
from experiments.f8_typed_span_programs import SpanProgramLearner,MAX_SPAN


ROOT=Path(__file__).resolve().parents[1]


def order_key(tree,domain,identifier):
    return sha256(f'{tree}:F-8:{domain}:{identifier}'.encode()).hexdigest()


def split_web(rows,tree):
    ranked=sorted(rows,key=lambda row:(order_key(tree,'web',row['id']),row['id']))
    held=[];entities=set()
    for row in ranked:
        if row['subject'] in entities or row['object'] in entities:continue
        held.append(row);entities.update((row['subject'],row['object']))
        if len(held)==128:break
    available=[row for row in ranked if row not in held and
               row['subject'] not in entities and row['object'] not in entities]
    validation=[];seen=set()
    for row in available:
        if row['subject'] in seen or row['object'] in seen:continue
        ep=webnlg_episode(row)
        if ep is None or any(end-start>MAX_SPAN for _,start,end in ep['spans']):continue
        validation.append(ep);seen.update((row['subject'],row['object']))
        if len(validation)==32:break
    fit=[webnlg_episode(row) for row in available if row['subject'] not in seen
         and row['object'] not in seen][:2000]
    return [row for row in fit if row is not None],validation,held


def split_sqac(rows,tree):
    _,f7held=f7_sqac_select(rows,tree)
    ordered=sorted(rows,key=lambda row:row['id'])
    old_taught=random.Random(1642).sample(ordered,2000)
    old_ids={row['id'] for row in old_taught}
    f4=select_distinct([row for row in rows if row['id'] not in old_ids],64,2117)
    f5=select_distinct([row for row in rows if row['id'] not in old_ids and
          row['context_key'] not in {r['context_key'] for r in old_taught}|{
              r['context_key'] for r in f4}],64,4039)
    excluded={row['context_key'] for row in (*f4,*f5,*f7held)}
    ranked=sorted(rows,key=lambda row:(order_key(tree,'sqac',row['id']),row['id']))
    held=[];held_contexts=set()
    for row in ranked:
        if row['context_key'] in excluded|held_contexts:continue
        held.append(row);held_contexts.add(row['context_key'])
        if len(held)==64:break
    validation=[];validation_contexts=set()
    for row in ranked:
        if row['context_key'] in excluded|held_contexts|validation_contexts:continue
        ep=sqac_training_episode(row)
        if ep is None or any(end-start>MAX_SPAN for _,start,end in ep['spans']):continue
        validation.append(ep);validation_contexts.add(row['context_key'])
        if len(validation)==32:break
    reserved=held_contexts|validation_contexts
    fit=[sqac_training_episode(row) for row in ranked
         if row['context_key'] not in reserved][:2000]
    return [row for row in fit if row is not None],validation,held


def sqac_training_episode(row):
    episode=sqac_episode(row)
    if episode is None:return None
    for rank,(_,_,_,sequence) in enumerate(ranked_sentences(
            row['context'],row['question'])):
        if sequence==episode['tokens']:
            episode['container_rank']=rank
            break
    return episode


def assess_web(model,rows):
    correct=attempts=candidates=0;latencies=[]
    for row in rows:
        sequence=tokens(row['text']);tick=time.perf_counter()
        left=model.predict('subject',sequence)
        right=model.predict('object',sequence)
        latencies.append((time.perf_counter()-tick)*1000)
        candidates+=left['candidates']+right['candidates']
        if left['status']!='predicted' or right['status']!='predicted':continue
        attempts+=1
        wanted=webnlg_episode(row)
        if wanted is not None:
            gold={role:(start,end) for role,start,end in wanted['spans']}
            correct+=left['span']==gold['subject'] and right['span']==gold['object']
    latencies.sort()
    return {'correct':correct,'attempts':attempts,'precision':
            round(correct/attempts,6) if attempts else None,
            'candidates':candidates,'p50_ms':round(statistics.median(latencies),5),
            'p95_ms':round(latencies[(95*len(latencies)+99)//100-1],5)}


def assess_sqac(model,rows):
    correct=attempts=candidates=0;latencies=[]
    for row in rows:
        tick=time.perf_counter();choices=[]
        for rank,(_,_,sentence,sequence) in enumerate(ranked_sentences(
                row['context'],row['question'])):
            result=model.predict('answer',sequence,
                [token['norm'] for token in tokens(row['question'])],rank)
            candidates+=result['candidates']
            if result['status']=='predicted':
                start,end=result['span']
                answer=' '.join(token['text'] for token in sequence[start:end])
                choices.append((result['margin'],answer))
        if choices:
            choices.sort(key=lambda item:(-item[0],item[1]))
            if len(choices)>1 and choices[0][0]==choices[1][0] and (
                    choices[0][1]!=choices[1][1]):
                continue
            attempts+=1
            from experiments.f4_feedback_span_pilot import canonical
            correct+=canonical(choices[0][1]) in {canonical(answer)
                                                      for answer in row['answers']}
        latencies.append((time.perf_counter()-tick)*1000)
    latencies.sort()
    return {'correct':correct,'attempts':attempts,'precision':
            round(correct/attempts,6) if attempts else None,
            'candidates':candidates,'p50_ms':round(statistics.median(latencies),5),
            'p95_ms':round(latencies[(95*len(latencies)+99)//100-1],5)}


def f7_roles(model,rows):
    correct=attempts=0
    for row in rows:
        ep=webnlg_episode(row)
        if ep is None:continue
        result=model.predict(ep['tokens'],[],('subject','object'))
        if result['status']!='parsed':continue
        attempts+=1
        gold={role:(start,end) for role,start,end in ep['spans']}
        correct+=all(result['spans'].get(role)==span for role,span in gold.items())
    return {'correct':correct,'attempts':attempts}


def f7_answers(model,rows):
    from experiments.f7_typed_sequences_dev import assess_sqac as old_assess
    return old_assess(model,rows)


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    web,_,_=web_download('train')
    webfit,webvalid,webheld=split_web(web,tree)
    sq_source,_=sqac_download('sqac_train')
    sqfit,sqvalid,sqheld=split_sqac(sqac_flatten(sq_source),tree)
    model=SpanProgramLearner();tick=time.process_time()
    model.observe_many(webfit);web_fit_cpu=time.process_time()-tick
    web_search=[model.synthesize(role,webvalid) for role in ('subject','object')]
    web_result=assess_web(model,webheld)
    prior=tuple(dict.fromkeys(name for result in web_search
                 for name in result.get('program',{}).get('operators',())))
    tick=time.process_time();model.observe_many(sqfit)
    sq_fit_cpu=time.process_time()-tick
    educated_search=model.synthesize('answer',sqvalid,prior=prior)
    educated=assess_sqac(model,sqheld)
    fresh=SpanProgramLearner();fresh.observe_many(sqfit)
    fresh_search=fresh.synthesize('answer',sqvalid)
    fresh_result=assess_sqac(fresh,sqheld)
    old=SegmentalLearner();old.observe_many(webfit)
    old_web=f7_roles(old,webheld)
    old.observe_many(sqfit)
    old_sq=f7_answers(old,sqheld)
    tick=time.process_time()
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'programs.json'
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        restart=SpanProgramLearner.from_dict(json.loads(path.read_text(encoding='utf8')))
        saved_bytes=path.stat().st_size
    restart_cpu=time.process_time()-tick
    restart_same=(assess_web(restart,webheld)['correct']==web_result['correct']
                  and assess_sqac(restart,sqheld)['correct']==educated['correct'])
    unchanged=git('rev-parse','HEAD:leobot')==tree and not git(
        'status','--porcelain','--','leobot')
    gate=(unchanged and web_result['correct']>=45 and web_result['attempts']>0
          and web_result['precision']>=0.8 and educated['correct']>=8
          and educated['attempts']>0 and educated['precision']>=0.6
          and web_result['correct']>=old_web['correct']+5
          and educated['correct']>=old_sq['correct']+5 and restart_same
          and educated_search['candidates']<=0.8*fresh_search['candidates']
          and educated['correct']>=fresh_result['correct']
          and web_result['p95_ms']<=10 and educated['p95_ms']<=10)
    output={'preregistration':'prereg/F-8-sintesis-de-learner-de-tramos.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'web_fit':len(webfit),'web_validation':len(webvalid),
            'web_heldout':len(webheld),'web_search':web_search,
            'web_result':web_result,'web_f7_roles':old_web,
            'sqac_fit':len(sqfit),'sqac_validation':len(sqvalid),
            'sqac_heldout':len(sqheld),'sqac_educated_search':educated_search,
            'sqac_educated':educated,'sqac_fresh_search':fresh_search,
            'sqac_fresh':fresh_result,'sqac_f7_baseline':old_sq,
            'web_fit_cpu_s':round(web_fit_cpu,6),
            'sqac_fit_cpu_s':round(sq_fit_cpu,6),
            'restart_same':restart_same,'restart_cpu_s':round(restart_cpu,6),
            'saved_bytes':saved_bytes,'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f8_span_programs_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

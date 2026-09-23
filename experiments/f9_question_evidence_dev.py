"""Preregistered F-9 SQAC development and controls; never reads external reserve."""
from __future__ import annotations

import json
import random
import resource
import statistics
import tempfile
import time
from hashlib import sha256
from pathlib import Path

from experiments.f4_feedback_span_pilot import (
    canonical, evaluate as old_evaluate, select_distinct,
    train_model as old_train,
)
from experiments.f7_typed_sequences_dev import (
    git,locate,ranked_sentences,select_sqac as f7_select,
    sqac_download,sqac_flatten,tokens,
)
from experiments.f8_span_programs_dev import split_sqac as f8_select
from experiments.f9_relational_evidence import RelationalEvidence,MAX_SPAN


ROOT=Path(__file__).resolve().parents[1]


def _previous_contexts(rows,tree):
    ordered=sorted(rows,key=lambda row:row['id'])
    old_taught=random.Random(1642).sample(ordered,2000)
    old_ids={row['id'] for row in old_taught}
    f4=select_distinct([row for row in rows if row['id'] not in old_ids],64,2117)
    f5=select_distinct([row for row in rows if row['id'] not in old_ids and
       row['context_key'] not in {r['context_key'] for r in old_taught}|{
           r['context_key'] for r in f4}],64,4039)
    _,f7=f7_select(rows,tree)
    _,_,f8=f8_select(rows,tree)
    return {row['context_key'] for row in (*f4,*f5,*f7,*f8)}


def _ranked(rows,tree):
    return sorted(rows,key=lambda row:(
        sha256((tree+':F-9:sqac:'+row['id']).encode()).hexdigest(),row['id']))


def choose_rows(rows,tree):
    excluded=_previous_contexts(rows,tree)
    ranked=_ranked(rows,tree)
    held=[];used=set()
    for row in ranked:
        key=row['context_key']
        if key in excluded|used:continue
        held.append(row);used.add(key)
        if len(held)==64:break
    validation=[]
    for row in ranked:
        key=row['context_key']
        if key in excluded|used:continue
        episode=make_episode(row)
        if episode is None:continue
        validation.append(episode);used.add(key)
        if len(validation)==32:break
    fit_rows=[row for row in ranked if row['context_key'] not in excluded|used][:2000]
    fit=[ep for row in fit_rows if (ep:=make_episode(row)) is not None]
    return fit_rows,fit,validation,held,excluded


def make_episode(row):
    ranked=ranked_sentences(row['context'],row['question'])
    sequences=[sequence for _,_,_,sequence in ranked]
    for rank,sequence in enumerate(sequences):
        for answer in row['answers']:
            span=locate(sequence,answer)
            if span is None or span[1]-span[0]>MAX_SPAN:continue
            return {'id':str(row['id']),'question':tokens(row['question']),
                    'sequences':sequences,'gold_rank':rank,
                    'gold':list(span)}
    return None


def assess(model,rows,questions=None):
    correct=attempts=wrong=candidates=0;times=[];outputs=[]
    for index,row in enumerate(rows):
        question=questions[index] if questions is not None else row['question']
        ranked=ranked_sentences(row['context'],question)
        sequences=[sequence for _,_,_,sequence in ranked]
        tick=time.perf_counter()
        prediction=model.predict(tokens(question),sequences)
        times.append((time.perf_counter()-tick)*1000)
        candidates+=prediction['candidates']
        if prediction['status']!='predicted':
            outputs.append(None);continue
        rank,start,end=prediction['choice']
        answer=' '.join(token['text'] for token in sequences[rank][start:end])
        outputs.append(answer);attempts+=1
        exact=canonical(answer) in {canonical(gold) for gold in row['answers']}
        correct+=exact;wrong+=not exact
    times.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'wrong_confident':wrong,'precision':round(correct/attempts,6)
            if attempts else None,'candidates':candidates,
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[(95*len(times)+99)//100-1],5)},outputs


def incompatible_rows(rows):
    """Pair each question with a different paragraph maximizing lexical overlap."""
    result=[]
    context_terms={row['context_key']:{token['norm'] for token in
                    tokens(row['context'])} for row in rows}
    for index,row in enumerate(rows):
        question={token['norm'] for token in tokens(row['question'])}
        candidates=[other for other in rows if other['context_key']!=row['context_key']]
        other=max(candidates,key=lambda candidate:(
            len(question & context_terms[candidate['context_key']]),
            -len(candidate['context']),candidate['id']))
        result.append({**row,'context':other['context'],
                       'answers':row['answers']})
    return result


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    document,_=sqac_download('sqac_train')
    fit_rows,fit,validation,held,excluded=choose_rows(sqac_flatten(document),tree)
    ceiling=sum(make_episode(row) is not None for row in held)
    if ceiling<30:raise RuntimeError('Techo previo insuficiente; no ejecutar piloto')
    model=RelationalEvidence();tick=time.process_time()
    model.observe_many(fit)
    fit_cpu=time.process_time()-tick
    calibration=model.calibrate(validation)
    treatment,outputs=assess(model,held)
    baseline=RelationalEvidence(use_join=False);tick=time.process_time()
    baseline.observe_many(fit);baseline_fit_cpu=time.process_time()-tick
    baseline_calibration=baseline.calibrate(validation)
    ablation,_=assess(baseline,held)
    old,timing=old_train(fit_rows)
    old_result={key:value for key,value in old_evaluate(old,held).items()
                if key!='rows'}
    random_q=[row['question'] for row in held]
    random.Random(53).shuffle(random_q)
    shuffled,_=assess(model,held,questions=random_q)
    incompatible,_=assess(model,incompatible_rows(held))
    tick=time.process_time()
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'model.json'
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        restored=RelationalEvidence.from_dict(json.loads(path.read_text(encoding='utf8')))
        stored_bytes=path.stat().st_size
    restart_cpu=time.process_time()-tick
    restart,_=assess(restored,held)
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    gate=(unchanged and ceiling>=30 and treatment['correct']>=10
          and treatment['attempts']>0 and treatment['precision']>=0.7
          and treatment['correct']>=old_result['correct']+5
          and treatment['correct']>=ablation['correct']+5
          and incompatible['attempts']==0
          and restart['correct']==treatment['correct']
          and restart['attempts']==treatment['attempts']
          and treatment['p95_ms']<=10
          and model.train_candidates+treatment['candidates']<=250000)
    output={'preregistration':'prereg/F-9-relaciones-pregunta-evidencia.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'excluded_previous_dev_contexts':len(excluded),
            'fit_offered':len(fit_rows),'fit_episodes':len(fit),
            'validation':len(validation),'development':len(held),
            'candidate_ceiling':ceiling,'train_candidates':model.train_candidates,
            'treatment_calibration':calibration,'treatment':treatment,
            'ablation_calibration':baseline_calibration,'ablation':ablation,
            'f4_baseline':old_result,'f4_train':timing,
            'shuffled_question':shuffled,'incompatible':incompatible,
            'restart_same':restart['correct']==treatment['correct'] and
                           restart['attempts']==treatment['attempts'],
            'stored_bytes':stored_bytes,'fit_cpu_s':round(fit_cpu,6),
            'ablation_fit_cpu_s':round(baseline_fit_cpu,6),
            'restart_cpu_s':round(restart_cpu,6),'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f9_question_evidence_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

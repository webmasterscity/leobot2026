"""F-7 development: one explicit sequence learner on RDF text and Spanish QA."""
from __future__ import annotations

import json
import random
import re
import resource
import statistics
import tempfile
import time
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from leobot.language import normalize
from experiments.b1_aggregate_operator import ROOT, git
from experiments.f4_feedback_span_pilot import (
    canonical, download as sqac_download, flatten as sqac_flatten,
    select_distinct, train_model as old_span_train, evaluate as old_span_evaluate,
)
from experiments.f6e_human_text_grounding import download_split as webnlg_download
from experiments.f6f_anchored_constructions_pilot import (
    AnchoredConstructions, evaluate as old_relation_evaluate,
)
from experiments.f7_segmental_learner import SegmentalLearner, MAX_TOKENS


def tokens(text):
    return [{'text':match.group(),'norm':canonical(match.group()),
             'start':match.start(),'end':match.end()}
            for match in re.finditer(r'[^\W_]+',text)
            if canonical(match.group())]


def locate(rows,value):
    wanted=[row['norm'] for row in tokens(value)]
    hits=[(i,i+len(wanted)) for i in range(len(rows)-len(wanted)+1)
          if [row['norm'] for row in rows[i:i+len(wanted)]]==wanted]
    return hits[0] if len(hits)==1 else None


def select_webnlg(rows,tree):
    ranked=sorted(rows,key=lambda row:(sha256((tree+':F-7:webnlg:'+row['id']).encode()).hexdigest(),row['id']))
    held=[];entities=set()
    for row in ranked:
        if row['subject'] in entities or row['object'] in entities:continue
        held.append(row);entities.update((row['subject'],row['object']))
        if len(held)==128:break
    reserved={row['id'] for row in held}
    taught=[row for row in ranked if row['id'] not in reserved and
            row['subject'] not in entities and row['object'] not in entities][:2000]
    return taught,held


def select_sqac(rows,tree):
    ordered=sorted(rows,key=lambda row:row['id'])
    taught=random.Random(int(sha256((tree+':F-7:sqac:teaching').encode()).hexdigest()[:8],16)).sample(
        ordered,2000)
    ids={row['id'] for row in taught}
    old_taught=random.Random(1642).sample(ordered,2000)
    old_ids={row['id'] for row in old_taught}
    f4=select_distinct([row for row in rows if row['id'] not in old_ids],64,2117)
    excluded={row['context_key'] for row in f4}
    f5=select_distinct([row for row in rows if row['id'] not in old_ids
                        and row['context_key'] not in {r['context_key'] for r in old_taught}|excluded],
                       64,4039)
    excluded.update(row['context_key'] for row in (*f4,*f5,*taught))
    pool={}
    for row in rows:
        if row['id'] not in ids and row['context_key'] not in excluded:
            pool.setdefault(row['context_key'],row)
    held=sorted(pool.values(),key=lambda row:(
        sha256((tree+':F-7:sqac:'+row['id']).encode()).hexdigest(),row['id']))[:64]
    return taught,held


def webnlg_episode(row):
    lex=tokens(row['text'])
    if len(lex)>MAX_TOKENS:return None
    subj=locate(lex,row['subject']);obj=locate(lex,row['object'])
    if subj is None or obj is None or set(range(*subj))&set(range(*obj)):
        return None
    return {'id':'web:'+row['id'],'tokens':lex,'context':[],
            'spans':[('subject',*subj),('object',*obj)],'label':row['predicate']}


def ranked_sentences(context,query):
    query_words={row['norm'] for row in tokens(query)}
    ranked=[]
    for index,sentence in enumerate(Bot._document_sentences(context)):
        sequence=tokens(sentence)
        shared=len(query_words & {row['norm'] for row in sequence})
        ranked.append((-shared,index,sentence,sequence))
    ranked.sort()
    return ranked[:2]


def sqac_episode(row):
    gold={canonical(value) for value in row['answers']}
    for _,_,sentence,sequence in ranked_sentences(row['context'],row['question']):
        if len(sequence)>MAX_TOKENS:continue
        for answer in row['answers']:
            span=locate(sequence,answer)
            if span is not None and canonical(sentence[sequence[span[0]]['start']:
                                                 sequence[span[1]-1]['end']]) in gold:
                return {'id':'sqac:'+row['id'],'tokens':sequence,
                        'context':[x['norm'] for x in tokens(row['question'])],
                        'spans':[('answer',*span)],'label':None}
    return None


def span_text(sequence,span):
    return ' '.join(row['text'] for row in sequence[span[0]:span[1]])


def assess_web(model,rows):
    correct=attempts=wrong=explored=0;times=[];statuses=Counter()
    for row in rows:
        sequence=tokens(row['text'])
        tick=time.perf_counter()
        answer=model.predict(sequence,[],('subject','object'))
        times.append((time.perf_counter()-tick)*1000)
        explored+=answer['candidates'];statuses[answer['status']]+=1
        if answer['status']!='parsed' or answer['label'] is None:continue
        attempts+=1
        subject=normalize(span_text(sequence,answer['spans']['subject']))
        obj=normalize(span_text(sequence,answer['spans']['object']))
        exact=(answer['label']==row['predicate'] and subject==row['subject'] and obj==row['object'])
        correct+=exact;wrong+=not exact
    times.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'precision':round(correct/attempts,6) if attempts else None,
            'wrong_confident':wrong,'candidates':explored,'status':dict(statuses),
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[(95*len(times)+99)//100-1],5)}


def assess_sqac(model,rows):
    correct=attempts=wrong=explored=0;times=[];statuses=Counter()
    for row in rows:
        tick=time.perf_counter();choices=[]
        for _,_,sentence,sequence in ranked_sentences(row['context'],row['question']):
            if not sequence or len(sequence)>MAX_TOKENS:continue
            result=model.predict(sequence,[x['norm'] for x in tokens(row['question'])],('answer',))
            explored+=result['candidates']
            if result['status']=='parsed':
                choices.append((result.get('margin',0),span_text(sequence,result['spans']['answer'])))
        if choices:
            choices.sort(key=lambda choice:(-choice[0],choice[1]))
            top=choices[0][1]
            if len(choices)>1 and choices[0][0]==choices[1][0] and top!=choices[1][1]:
                statuses['ambiguous_sentences']+=1
            else:
                statuses['answered']+=1;attempts+=1
                exact=canonical(top) in {canonical(value) for value in row['answers']}
                correct+=exact;wrong+=not exact
        else:statuses['abstain']+=1
        times.append((time.perf_counter()-tick)*1000)
    times.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'precision':round(correct/attempts,6) if attempts else None,
            'wrong_confident':wrong,'candidates':explored,'status':dict(statuses),
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[(95*len(times)+99)//100-1],5)}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    web_rows,web_sources,web_bytes=webnlg_download('train')
    web_taught,web_held=select_webnlg(web_rows,tree)
    sqac_source,sqac_bytes=sqac_download('sqac_train')
    sqac_rows=sqac_flatten(sqac_source)
    sqac_taught,sqac_held=select_sqac(sqac_rows,tree)
    web_episodes=[episode for row in web_taught
                  if (episode:=webnlg_episode(row)) is not None]
    sqac_episodes=[episode for row in sqac_taught
                   if (episode:=sqac_episode(row)) is not None]
    model=SegmentalLearner();tick=time.process_time()
    model.observe_many(web_episodes)
    web_learning_cpu=time.process_time()-tick
    web_result=assess_web(model,web_held)
    old_web=AnchoredConstructions()
    for row in web_taught:old_web.observe(row)
    old_web.compile();web_baseline=old_relation_evaluate(old_web,web_held)
    tick=time.process_time();model.observe_many(sqac_episodes)
    sqac_learning_cpu=time.process_time()-tick
    combined_result=assess_sqac(model,sqac_held)
    fresh=SegmentalLearner();tick=time.process_time()
    fresh.observe_many(sqac_episodes)
    fresh_cpu=time.process_time()-tick
    sqac_fresh=assess_sqac(fresh,sqac_held)
    old_span,old_learning=old_span_train(sqac_taught)
    old_span_result={key:value for key,value in old_span_evaluate(old_span,sqac_held).items()
                     if key!='rows'}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'model.json';tick=time.process_time()
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        restored=SegmentalLearner.from_dict(json.loads(path.read_text(encoding='utf8')))
        restart_cpu=time.process_time()-tick
        restored_result=assess_sqac(restored,sqac_held)
        restart_same=all(restored_result[key]==combined_result[key] for key in
                         ('correct','attempts','wrong_confident'))
        saved_bytes=path.stat().st_size
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    gate=(unchanged and web_result['correct']>=20 and web_result['precision'] is not None
          and web_result['precision']>=0.8 and combined_result['correct']>=10
          and combined_result['precision'] is not None and combined_result['precision']>=0.6
          and web_result['correct']-web_baseline['correct']>=5
          and combined_result['correct']-old_span_result['correct']>=5
          and restart_same and web_result['p95_ms']<=10 and combined_result['p95_ms']<=10
          and web_learning_cpu<=40 and sqac_learning_cpu<=40
          and combined_result['correct']>sqac_fresh['correct'])
    output={'preregistration':'prereg/F-7-segmentacion-y-roles-tipados.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'web_source_hashes':web_sources,'web_source_bytes':web_bytes,
            'sqac_source_bytes':sqac_bytes,'web_train':len(web_taught),
            'web_episodes':len(web_episodes),'web_heldout':len(web_held),
            'sqac_train':len(sqac_taught),'sqac_episodes':len(sqac_episodes),
            'sqac_heldout':len(sqac_held),'web':web_result,
            'web_template_baseline':web_baseline,'sqac_educated':combined_result,
            'sqac_fresh':sqac_fresh,'sqac_span_baseline':old_span_result,
            'web_learning_cpu_s':round(web_learning_cpu,6),
            'sqac_learning_cpu_s':round(sqac_learning_cpu,6),
            'sqac_fresh_cpu_s':round(fresh_cpu,6),
            'sqac_old_learning':old_learning,
            'restart_same':restart_same,'restart_cpu_s':round(restart_cpu,6),
            'saved_bytes':saved_bytes,'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f7_typed_sequences_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('web_source_hashes',)},ensure_ascii=False))


if __name__=='__main__':
    main()

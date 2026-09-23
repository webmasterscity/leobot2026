"""G-28b evaluator: required gap marker, anchor-free spans, learned correspondences.

See prereg/G-28b-hueco-exigido-y-correspondencias-lexicas.md.
Run from the repository root: python3 -m experiments.g28b_gap_correspondences [--dev]
"""
from __future__ import annotations

import io
import json
import os
import random
import resource
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from experiments.agi_board import MLQA_ARCHIVE_SHA, MLQA_URL, SEED as BOARD_SEED, canonical
from experiments.cmp1_compare import token_f1

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-28b-hueco-exigido-y-correspondencias-lexicas.md'
EDU_SEED=2828
CACHE=Path(os.environ.get('MLQA_CACHE','/tmp/leobot_mlqa_v1.zip'))


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def archive():
    if CACHE.exists() and sha256(CACHE.read_bytes()).hexdigest()==MLQA_ARCHIVE_SHA:
        return zipfile.ZipFile(CACHE)
    data=urllib.request.urlopen(MLQA_URL,timeout=60).read()
    if sha256(data).hexdigest()!=MLQA_ARCHIVE_SHA:
        raise RuntimeError('MLQA cambió.')
    CACHE.write_bytes(data)
    return zipfile.ZipFile(io.BytesIO(data))


def rows(z,member):
    doc=json.loads(z.read(member)); out=[]
    for article in doc['data']:
        for paragraph in article['paragraphs']:
            for qa in paragraph['qas']:
                out.append({'id':qa['id'],'context':paragraph['context'],
                            'question':qa['question'],
                            'answers':[a['text'] for a in qa['answers']]})
    return sorted(out,key=lambda r:r['id'])


def educate(examples,shuffled=False):
    bot=Bot(); answers=[e['answers'][0] for e in examples]
    if shuffled:
        answers=answers[1:]+answers[:1]
    started=time.process_time()
    for example,answer in zip(examples,answers):
        bot.observe_reading_example(example['context'],example['question'],answer)
    bot.consolidate_reading()
    return bot,time.process_time()-started


def ask(template,case,context=None,use_model=True,question=None,use_correspondences=True):
    # Each question gets a new bot carrying the same learned reading model
    # (read-only while answering), so answers never depend on earlier cases.
    bot=Bot(); bot.reading_model=template.reading_model
    source=f'caso:{case["id"]}'
    bot.ingest_document_text(context if context is not None else case['context'],source=source)
    started=time.perf_counter()
    text=question if question is not None else case['question']
    if use_model and use_correspondences:
        reply=bot.respond(text)
    else:
        reply=bot.answer_from_utterances(text,use_model=use_model,
                                         use_correspondences=use_correspondences) or {'status':'unrecognized'}
    elapsed=(time.perf_counter()-started)*1000
    bot.forget_utterances(source)
    answer=reply.get('text','') if reply.get('status')=='literal' else ''
    return answer,elapsed,reply.get('status')


def answer_sentence(bot,case):
    from leobot.reading import _TOKEN,_is_word,_norm
    target=[_norm(t) for t in _TOKEN.findall(case['answers'][0]) if _is_word(t)]
    for sentence in bot._document_sentences(case['context']):
        words=[_norm(t) for t in _TOKEN.findall(sentence) if _is_word(t)]
        if target and any(words[k:k+len(target)]==target for k in range(len(words)-len(target)+1)):
            return sentence.rstrip('.?!¿¡ ')
    return None


def scored(answer,case):
    return {'answered':bool(answer),
            'exact':bool(answer) and canonical(answer) in {canonical(a) for a in case['answers']},
            'f1':round(token_f1(answer,case['answers']),4) if answer else 0.0}


def summary(results):
    n=len(results)
    return {'n':n,'answered':sum(r['answered'] for r in results),
            'exact':round(sum(r['exact'] for r in results)/n,4),
            'f1':round(sum(r['f1'] for r in results)/n,4)}


def p95(values):
    ordered=sorted(values)
    return round(ordered[max(0,-(-95*len(ordered)//100)-1)],4) if ordered else None


RENAME_ALPHABET='bcdfgjklmnpqrstvxz'


def rename(case,index):
    """Replace every word shared by context and question with an invented word."""
    import re
    token=re.compile(r'\w+')
    shared={w.casefold() for w in token.findall(case['question'])} & \
           {w.casefold() for w in token.findall(case['context'])}
    mapping={}
    rng=random.Random(f'{index}:{case["id"]}')
    for word in sorted(shared):
        if any(ch.isdigit() for ch in word):
            continue
        fresh=''.join(rng.choice(RENAME_ALPHABET)+rng.choice('aeiou') for _ in range(max(2,len(word)//2)))
        mapping[word]=fresh
    def sub(text):
        def one(match):
            word=match.group(0); new=mapping.get(word.casefold())
            if new is None:
                return word
            return new.capitalize() if word[:1].isupper() else new
        return token.sub(one,text)
    return {'id':case['id'],'context':sub(case['context']),'question':sub(case['question']),
            'answers':[sub(a) for a in case['answers']]}


def main():
    dev='--dev' in sys.argv[1:]
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean_before=not git('status','--porcelain','--','leobot','experiments/g28b_gap_correspondences.py')
    z=archive()
    test=rows(z,'MLQA_V1/test/test-context-es-question-es.json')
    devset=rows(z,'MLQA_V1/dev/dev-context-es-question-es.json')
    rng=random.Random(EDU_SEED); chosen=rng.sample(test,2300)
    education=chosen[:2000]
    edu_context_set={r['context'] for r in education}
    visible=[r for r in rng.sample(test,len(test)) if r['context'] not in edu_context_set][:300]
    board_ids={r['id'] for r in random.Random(BOARD_SEED).sample(devset,20)}
    if dev:
        seed=None; reserve=visible
    else:
        seed=int(before[:8],16)
        pool=[r for r in devset if r['id'] not in board_ids]
        reserve=random.Random(seed).sample(pool,200)
    edu_contexts={r['context'] for r in education}
    leak=sum(r['context'] in edu_contexts for r in reserve)

    treated,edu_cpu=educate(education)
    shuffled,_=educate(education,shuffled=True)
    fresh=Bot()
    rows_out=[]; lat_single=[]
    for index,case in enumerate(reserve):
        answer,ms,status=ask(treated,case); lat_single.append(ms)
        row={'id':case['id'],'question':case['question'],'answers':case['answers'],
             'answer':answer,'status':status,**scored(answer,case)}
        abl,_,_=ask(treated,case,use_model=False); row['ablation']=scored(abl,case)
        nocorr,_,_=ask(treated,case,use_correspondences=False); row['no_correspondences']=scored(nocorr,case)
        sentence=answer_sentence(treated,case)
        if sentence is not None:
            gapless,_,_=ask(treated,case,question='¿'+sentence+'?'); row['no_gap_abstained']=not gapless
        shu,_,_=ask(shuffled,case); row['shuffled']=scored(shu,case)
        fr,_,_=ask(fresh,case); row['fresh_answered']=bool(fr)
        other=reserve[(index+1)%len(reserve)]
        hon,_,_=ask(treated,case,context=other['context']); row['honest_abstained']=not hon
        renamed=rename(case,index)
        ren,_,_=ask(treated,renamed); row['renamed']=scored(ren,renamed)
        rows_out.append(row)
    # Restart: save/load the educated bot and repeat the treatment answers.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; treated.save(path); restored=Bot.load(path)
    restart_same=all(ask(restored,case)[0]==row['answer'] for case,row in zip(reserve,rows_out))
    # Joint memory: every reserve paragraph read by one bot.
    joint=restored
    for case in reserve:
        joint.ingest_document_text(case['context'],source=f'conjunta:{case["id"]}')
    joint_rows=[]; lat_joint=[]
    for case in reserve:
        started=time.perf_counter(); reply=joint.respond(case['question'])
        lat_joint.append((time.perf_counter()-started)*1000)
        joint_rows.append(scored(reply.get('text','') if reply.get('status')=='literal' else '',case))
    after=git('rev-parse','HEAD:leobot')

    treat=summary(rows_out)
    ablation=summary([r['ablation'] for r in rows_out])
    shuffled_s=summary([r['shuffled'] for r in rows_out])
    renamed_s=summary([r['renamed'] for r in rows_out])
    joint_s=summary(joint_rows)
    fresh_answers=sum(r['fresh_answered'] for r in rows_out)
    nocorr_s=summary([r['no_correspondences'] for r in rows_out])
    gapless=[r['no_gap_abstained'] for r in rows_out if 'no_gap_abstained' in r]
    no_gap=sum(gapless)/max(1,len(gapless))
    honesty=sum(r['honest_abstained'] for r in rows_out)/len(rows_out)
    cpu=time.process_time()-cpu0; wall=time.perf_counter()-wall0
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget=edu_cpu<=60 and rss<=256*1024 and p95(lat_single)<=10 and p95(lat_joint)<=200
    gate=(treat['f1']>=0.25 and treat['exact']>=0.10 and
          treat['f1']-ablation['f1']>=0.05 and treat['f1']-shuffled_s['f1']>=0.10 and
          fresh_answers==0 and honesty>=0.90 and no_gap>=0.95 and abs(renamed_s['f1']-treat['f1'])<=0.03 and
          restart_same and joint_s['f1']>=0.8*treat['f1'] and budget and leak==0 and
          before==after and clean_before)
    result={'kind':'G28b_gap_correspondences','preregistration':PREREG,'development':dev,
            'engine_tree':before,'engine_unchanged':before==after,'engine_committed':clean_before,
            'seed':seed,'hashseed':os.environ.get('PYTHONHASHSEED'),'education':len(education),
            'education_skipped':treated.reading_model['skipped'],'reserve':len(reserve),
            'reserve_context_leak':leak,'threshold':treated._reading_threshold(),
            'treatment':treat,'ablation':ablation,'shuffled':shuffled_s,'renamed':renamed_s,
            'joint':joint_s,'no_correspondences':nocorr_s,'no_gap_abstention':round(no_gap,4),
            'no_gap_cases':len(gapless),'correspondence_words':len(treated.reading_model['correspondences']),
            'fresh_answers':fresh_answers,'honest_abstention':round(honesty,4),
            'restart_identical':restart_same,'latency_single_p95_ms':p95(lat_single),
            'latency_joint_p95_ms':p95(lat_joint),'education_cpu_s':round(edu_cpu,3),
            'cpu_total_s':round(cpu,3),'wall_total_s':round(wall,3),'max_rss_kib':rss,
            'budget_ok':budget,'gate_pass':gate,'rows':rows_out}
    name='g28b_gap_correspondences_dev' if dev else f'g28b_gap_correspondences_{seed}'
    out=ROOT/'results_v3'/f'{name}_hashseed{result["hashseed"]}.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':
    main()

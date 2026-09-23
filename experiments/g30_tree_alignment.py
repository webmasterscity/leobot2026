"""G-30 evaluator: answering by aligning question and sentence through learned trees.

See prereg/G-30-alineacion-por-arboles.md.
Run from the repository root: python3 -m experiments.g30_tree_alignment [--dev]
"""
from __future__ import annotations

import json
import os
import random
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.agi_board import SEED as BOARD_SEED
from experiments.g28_reading_alignment import archive, rows, scored, summary, p95, rename, EDU_SEED
from experiments.g28b_gap_correspondences import answer_sentence
from experiments.g29_syntax_counts import split

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-30-alineacion-por-arboles.md'


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def educate(treebank,examples,shuffle_syntax=False,shuffle_answers=False):
    bot=Bot(); started=time.process_time(); rng=random.Random(7)
    for words,tags,heads in treebank:
        if shuffle_syntax:
            heads=[rng.choice([h for h in range(len(words)+1) if h!=i+1]) for i in range(len(words))]
        bot.observe_parsed_sentence(words,tags,heads)
    bot.consolidate_syntax()
    answers=[e['answers'][0] for e in examples]
    if shuffle_answers:
        answers=answers[1:]+answers[:1]
    for example,answer in zip(examples,answers):
        bot.observe_reading_example(example['context'],example['question'],answer)
    bot.consolidate_reading()
    return bot,time.process_time()-started


def ask(template,case,context=None,question=None,structure=True):
    bot=Bot(); bot.reading_model=template.reading_model; bot.syntax_model=template.syntax_model
    source=f'caso:{case["id"]}'
    started=time.perf_counter()
    bot.ingest_document_text(context if context is not None else case['context'],source=source)
    read_ms=(time.perf_counter()-started)*1000
    text=question if question is not None else case['question']
    started=time.perf_counter()
    reply=(bot.respond(text) if structure else
           bot.answer_from_utterances(text,use_structure=False) or {'status':'unrecognized'})
    answer_ms=(time.perf_counter()-started)*1000
    answer=reply.get('text','') if reply.get('status')=='literal' else ''
    return answer,answer_ms,read_ms


def main():
    dev='--dev' in sys.argv[1:]
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean=not git('status','--porcelain','--','leobot','experiments/g30_tree_alignment.py')
    z=archive()
    test=rows(z,'MLQA_V1/test/test-context-es-question-es.json')
    devset=rows(z,'MLQA_V1/dev/dev-context-es-question-es.json')
    rng=random.Random(EDU_SEED); chosen=rng.sample(test,2300); education=chosen[:2000]
    edu_contexts={r['context'] for r in education}
    board_ids={r['id'] for r in random.Random(BOARD_SEED).sample(devset,20)}
    if dev:
        seed=None
        reserve=[r for r in rng.sample(test,len(test)) if r['context'] not in edu_contexts][:300]
    else:
        seed=int(before[:8],16)
        reserve=random.Random(seed).sample([r for r in devset if r['id'] not in board_ids],200)
    leak=sum(r['context'] in edu_contexts for r in reserve)
    treebank=split('train')
    treated,edu_cpu=educate(treebank,education)
    shuffled_syntax,_=educate(treebank,education,shuffle_syntax=True)
    fresh=Bot()
    out_rows=[]; answer_lat=[]; read_lat=[]
    for index,case in enumerate(reserve):
        answer,ms,read_ms=ask(treated,case); answer_lat.append(ms)
        read_lat.append(read_ms/max(1,len(treated._document_sentences(case['context']))))
        row={'id':case['id'],'question':case['question'],'answers':case['answers'],'answer':answer,
             **scored(answer,case)}
        row['no_structure']=scored(ask(treated,case,structure=False)[0],case)
        row['shuffled_syntax']=scored(ask(shuffled_syntax,case)[0],case)
        row['fresh_answered']=bool(ask(fresh,case)[0])
        other=reserve[(index+1)%len(reserve)]
        row['honest_abstained']=not ask(treated,case,context=other['context'])[0]
        sentence=answer_sentence(treated,case)
        if sentence is not None:
            row['no_gap_abstained']=not ask(treated,case,question='¿'+sentence+'?')[0]
        renamed=rename(case,index)
        row['renamed']=scored(ask(treated,renamed)[0],renamed)
        out_rows.append(row)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; treated.save(path); restored=Bot.load(path)
    restart=all(ask(restored,case)[0]==row['answer'] for case,row in zip(reserve,out_rows))
    joint=Bot(); joint.reading_model=treated.reading_model; joint.syntax_model=treated.syntax_model
    for case in reserve:
        joint.ingest_document_text(case['context'],source=f'conjunta:{case["id"]}')
    joint_rows=[]; joint_lat=[]
    for case in reserve:
        started=time.perf_counter(); reply=joint.respond(case['question'])
        joint_lat.append((time.perf_counter()-started)*1000)
        joint_rows.append(scored(reply.get('text','') if reply.get('status')=='literal' else '',case))
    after=git('rev-parse','HEAD:leobot')
    treat=summary(out_rows)
    no_structure=summary([r['no_structure'] for r in out_rows])
    shuffled=summary([r['shuffled_syntax'] for r in out_rows])
    renamed=summary([r['renamed'] for r in out_rows])
    joint_s=summary(joint_rows)
    honesty=sum(r['honest_abstained'] for r in out_rows)/len(out_rows)
    gapless=[r['no_gap_abstained'] for r in out_rows if 'no_gap_abstained' in r]
    no_gap=sum(gapless)/max(1,len(gapless))
    fresh_answers=sum(r['fresh_answered'] for r in out_rows)
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget=(edu_cpu<=240 and rss<=512*1024 and p95(answer_lat)<=10 and p95(joint_lat)<=200 and
            p95(read_lat)<=100)
    gate=(treat['f1']>=0.25 and treat['exact']>=0.10 and treat['f1']-no_structure['f1']>=0.02 and
          treat['f1']-shuffled['f1']>=0.02 and honesty>=0.90 and no_gap>=0.95 and fresh_answers==0 and
          abs(renamed['f1']-treat['f1'])<=0.03 and restart and joint_s['f1']>=0.8*treat['f1'] and
          budget and leak==0 and before==after and clean)
    result={'kind':'G30_tree_alignment','preregistration':PREREG,'development':dev,'engine_tree':before,
            'engine_unchanged':before==after,'engine_committed':clean,'seed':seed,
            'hashseed':os.environ.get('PYTHONHASHSEED'),'reserve':len(reserve),'reserve_context_leak':leak,
            'treatment':treat,'no_structure':no_structure,'shuffled_syntax':shuffled,'renamed':renamed,
            'joint':joint_s,'honest_abstention':round(honesty,4),'no_gap_abstention':round(no_gap,4),
            'fresh_answers':fresh_answers,'restart_identical':restart,
            'answer_p95_ms':p95(answer_lat),'joint_p95_ms':p95(joint_lat),'read_sentence_p95_ms':p95(read_lat),
            'education_cpu_s':round(edu_cpu,2),'cpu_total_s':round(time.process_time()-cpu0,2),
            'wall_total_s':round(time.perf_counter()-wall0,2),'max_rss_kib':rss,'budget_ok':budget,
            'gate_pass':gate,'rows':out_rows}
    name='g30_tree_alignment_dev' if dev else f'g30_tree_alignment_{seed}'
    (ROOT/'results_v3'/f'{name}_hashseed{result["hashseed"]}.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':
    main()

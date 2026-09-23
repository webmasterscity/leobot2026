"""CMP-1: Leobot versus a Claude subagent on identical information.

See prereg/cmp-1-leobot-frente-a-subagente.md. Run from the repository root:
python3 -m experiments.cmp1_compare <subagent_answers.json>
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from leobot import Bot
from experiments.agi_board import canonical, mlqa_cases
from experiments.user_text_probe import QUESTIONS, STATEMENTS

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/cmp-1-leobot-frente-a-subagente.md'


def tree():
    return subprocess.check_output(('git','rev-parse','HEAD:leobot'),cwd=ROOT,text=True).strip()


def token_f1(prediction,references):
    best=0.0
    words=canonical(prediction).split()
    for reference in references:
        gold=canonical(reference).split()
        common=sum((Counter(words)&Counter(gold)).values())
        if common:
            p=common/len(words); r=common/len(gold)
            best=max(best,2*p*r/(p+r))
    return best


def score(answer,references):
    return {'exact':canonical(answer) in {canonical(r) for r in references},
            'f1':round(token_f1(answer,references),4)}


def main(path):
    before=tree()
    subagent=json.loads(Path(path).read_text(encoding='utf8'))
    cases,_=mlqa_cases()
    started=time.process_time(); wall=time.perf_counter()
    rows=[]
    for case in cases:
        bot=Bot()
        bot.ingest_document_text(case['context'],source=f'mlqa:{case["id"]}')
        reply=bot.respond(case['question'])
        leo=reply.get('text','') if reply.get('status') not in ('unrecognized',) else ''
        other=subagent['mlqa'].get(case['id'],'')
        rows.append({'id':case['id'],'question':case['question'],'answers':case['answers'],
                     'leobot_status':reply.get('status'),'leobot':leo,
                     'leobot_score':score(leo,case['answers']),
                     'subagent':other,'subagent_score':score(other,case['answers'])})
    leo_cpu=time.process_time()-started; leo_wall=time.perf_counter()-wall
    bot=Bot(); reading=[]
    for index,sentence in enumerate(STATEMENTS):
        bot.ingest_document_text(sentence,source=f'brief_user_{index}')
    for question,other in zip(QUESTIONS,subagent['reading']):
        reply=bot.respond(question)
        reading.append({'question':question,'leobot_status':reply.get('status'),
                        'leobot':reply.get('text'),'subagent':other})
    after=tree()
    summary={name:{'exact':sum(r[f'{name}_score']['exact'] for r in rows),
                   'f1_mean':round(sum(r[f'{name}_score']['f1'] for r in rows)/len(rows),4)}
             for name in ('leobot','subagent')}
    superior=(summary['subagent']['exact']-summary['leobot']['exact']>=3 or
              summary['subagent']['f1_mean']-summary['leobot']['f1_mean']>=0.15)
    result={'kind':'CMP1','preregistration':PREREG,'engine_tree':before,
            'engine_unchanged':before==after,'mlqa':rows,'reading':reading,
            'summary':summary,'subagent_superior':superior,
            'leobot_cpu_s':round(leo_cpu,4),'leobot_wall_s':round(leo_wall,4)}
    out=ROOT/'results_v3'/'cmp1_leobot_vs_subagent.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'summary':summary,'subagent_superior':superior,
                      'engine_unchanged':before==after},ensure_ascii=False))


if __name__=='__main__':
    main(sys.argv[1])

"""F-6 development gate: raw assertions plus world changes before action learning."""
from __future__ import annotations

import json
import resource
import time

from leobot import Bot
from experiments.b1_aggregate_operator import ROOT, git
from experiments.d1_cross_modal_chain import WORDS, b_experience, c_experience, remove_transfer, score_b


PREFIX = 'f6dev'
WORDS_DEV = WORDS[0]


def raw_documents(bot):
    who, verb, what, where, _ = WORDS_DEV
    for index in range(4):
        bot.ingest_document_text(
            f'{who} {PREFIX}p{index} {verb} {what} {PREFIX}i{index} en {where} {PREFIX}d{index}.',
            source=f'f6:document:{index}')


def world_changes(bot):
    reports=[]
    for index in range(3):
        person, item, dest=(f'{PREFIX}p{index}',f'{PREFIX}i{index}',f'{PREFIX}d{index}')
        before={(PREFIX+'signal',person,dest,'closed'),(PREFIX+'item',item)}
        after={(PREFIX+'signal',person,dest,'open'),(PREFIX+'item',item)}
        reports.append(bot.observe_world_transition(before,after))
    return reports


def one(name, *, documents=False, observations=False, disable_meta=False):
    start=time.process_time(); bot=Bot(); reports=[]
    if documents:
        raw_documents(bot)
    if observations:
        reports=world_changes(bot)
    prior=bot.meta_representations.rows()
    if disable_meta:
        remove_transfer(bot)
    b=b_experience(bot,PREFIX,WORDS_DEV)
    b_score=score_b(bot,PREFIX,WORDS_DEV,2117)
    label,c=c_experience(bot,PREFIX,0)
    return {'name':name,'world_statuses':[r['status'] for r in reports],
            'meta_before_b':prior,'b_statuses':[r['status'] for r in b],
            'b_correct':b_score['correct'],'b_unsafe':b_score['unsafe_without_precondition'],
            'b_p95_ms':b_score['p95_ms'],'c_statuses':[r['status'] for r in c],
            'cpu_s':round(time.process_time()-start,6)}


def main():
    start=time.monotonic()
    results=[one('treatment',documents=True,observations=True),
             one('raw_only',documents=True),
             one('world_only',observations=True),
             one('same_information_no_meta',documents=True,observations=True,disable_meta=True),
             one('fresh')]
    baseline_tree=git('rev-parse','HEAD:leobot')
    output={'preregistration':'prereg/F-6-anclaje-texto-efectos.md',
            'kind':'development_only','baseline_engine_tree':baseline_tree,
            'working_engine_changes':git('status','--porcelain','--','leobot'),
            'results':results,'wall_s':round(time.monotonic()-start,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'gate_passed':results[0]['b_statuses'][-1]=='operator_learned'
                          and results[-1]['b_statuses'][-1]!='operator_learned'}
    path=ROOT/'results_v3'/'f6_raw_world_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    main()

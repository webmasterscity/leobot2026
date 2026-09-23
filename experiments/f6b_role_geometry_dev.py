"""F-6b development controls for raw-text/world-effect role geometry."""
from __future__ import annotations

import json
import resource
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.b1_aggregate_operator import ROOT, git
from experiments.d1_cross_modal_chain import (
    b_experience, b_world, c_cases, c_experience, remove_transfer, score_b, score_c,
)
from experiments.f6_raw_world_dev import PREFIX, WORDS_DEV, raw_documents, world_changes


def timed(function):
    start=time.process_time(); result=function()
    return result,round(time.process_time()-start,6)


def change(index,mode='normal'):
    person,item,dest=(f'{PREFIX}p{index}',f'{PREFIX}i{index}',f'{PREFIX}d{index}')
    if mode=='three_roles':
        before={(PREFIX+'signal',person,item,dest,'closed')}
        after={(PREFIX+'signal',person,item,dest,'open')}
    elif mode=='no_edge':
        before={(PREFIX+'subject',person,'closed'),(PREFIX+'destination',dest,'closed'),
                (PREFIX+'item',item)}
        after={(PREFIX+'subject',person,'open'),(PREFIX+'destination',dest,'open'),
               (PREFIX+'item',item)}
    elif mode=='counter':
        before={(PREFIX+'signal',person,item,'closed'),(PREFIX+'destination',dest)}
        after={(PREFIX+'signal',person,item,'open'),(PREFIX+'destination',dest)}
    else:
        before={(PREFIX+'signal',person,dest,'closed'),(PREFIX+'item',item)}
        after={(PREFIX+'signal',person,dest,'open'),(PREFIX+'item',item)}
    return before,after


def reload(bot):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'
        bot.save(path)
        size=path.stat().st_size
        loaded=Bot.load(path)
    return loaded,size


def learn_action(bot,fourth=False):
    reports=b_experience(bot,PREFIX,WORDS_DEV)
    if fourth:
        person,origin,dest,before,after=b_world(PREFIX,3,success=True)
        reports.append(bot.observe_symbolic_transition(
            f'{WORDS_DEV[-1]} a {person} desde {origin} hacia {dest}.',before,after))
    return reports


def variant(name,docs=False,world=False,disable_meta=False,restart=False,fourth=False,
            counter_before=False,counter_after=False):
    bot=Bot();cost={}; world_reports=[]; persisted_bytes=None; counter_report=None
    if docs:
        _,cost['documents']=timed(lambda:raw_documents(bot))
    if world:
        world_reports,cost['world_observations']=timed(lambda:world_changes(bot))
    meta_before=bot.meta_representations.rows()
    if counter_before:
        counter_report,cost['counter_before']=timed(lambda:bot.observe_world_transition(*change(3,'counter')))
    if disable_meta:
        remove_transfer(bot)
    if restart:
        (bot,persisted_bytes),cost['restart']=timed(lambda:reload(bot))
    b,cost['action_acquisition']=timed(lambda:learn_action(bot,fourth=fourth))
    bscore,cost['action_response']=timed(lambda:score_b(bot,PREFIX,WORDS_DEV,2117))
    (label,c),cost['procedure_acquisition']=timed(lambda:c_experience(bot,PREFIX,0))
    cscore,cost['procedure_response']=timed(lambda:score_c(bot,label,c_cases(2117)))
    before_after_counter={'meta':bot.meta_representations.rows(),
                          'active_actions':len(bot.symbolic.operators()),
                          'c_correct':cscore['correct']}
    if counter_after:
        counter_report,cost['counter_after']=timed(lambda:bot.observe_world_transition(*change(3,'counter')))
    after_counter={'meta':bot.meta_representations.rows(),
                   'active_actions':len(bot.symbolic.operators()),
                   'c_correct':score_c(bot,label,c_cases(2117))['correct']}
    return {'name':name,'world_statuses':[row['status'] for row in world_reports],
            'meta_before_action':meta_before,'action_statuses':[row['status'] for row in b],
            'action_score':bscore,'procedure_statuses':[row['status'] for row in c],
            'procedure_score':cscore,'persisted_bytes':persisted_bytes,
            'counter_status':counter_report['status'] if counter_report else None,
            'before_counter':before_after_counter,'after_counter':after_counter,
            'cost':cost,'cpu_total_s':round(sum(cost.values()),6)}


def special_controls():
    reports={}
    for mode in ('three_roles','no_edge'):
        bot=Bot();raw_documents(bot)
        observed=[bot.observe_world_transition(*change(index,mode)) for index in range(3)]
        reports[mode]={'statuses':[row['status'] for row in observed],
                       'meta':bot.meta_representations.rows()}
    bot=Bot();raw_documents(bot);world_changes(bot)
    duplicate=bot.observe_world_transition(*change(0))
    reports['duplicate']={'status':duplicate['status'],
                          'observations':len(next(iter(bot.raw_world_alignment_hypotheses.values()))['observations'])}
    competing=Bot();raw_documents(competing)
    for index in range(4):
        competing.ingest_document_text(
            f'El registro {PREFIX}p{index} une {PREFIX}i{index} con el sitio {PREFIX}d{index}.',
            source=f'competing:{index}')
    reports['competing_relations']={
        'promotions':len(competing.raw_relation_promotions),
        'observation':competing.observe_world_transition(*change(0))['status'],
        'meta':competing.meta_representations.rows()}
    return reports


def main():
    start=time.monotonic(); variants=[
        variant('treatment',docs=True,world=True,restart=True),
        variant('raw_only',docs=True),
        variant('world_only',world=True),
        variant('same_information_no_meta',docs=True,world=True,disable_meta=True),
        variant('fresh'),
        variant('direct_four',fourth=True),
        variant('counter_before',docs=True,world=True,counter_before=True),
        variant('counter_after',docs=True,world=True,counter_after=True),
    ]
    special=special_controls(); treatment=variants[0];fresh=variants[4]
    gate=(treatment['action_statuses'][-1]=='operator_learned'
          and fresh['action_statuses'][-1]!='operator_learned'
          and treatment['action_score']['correct']>=116
          and treatment['action_score']['unsafe_without_precondition']==0
          and treatment['procedure_score']['correct']>=116
          and all(row['action_statuses'][-1]!='operator_learned' for row in variants[1:5])
          and variants[6]['action_statuses'][-1]!='operator_learned'
          and variants[7]['after_counter']['active_actions']==0
          and variants[7]['after_counter']['c_correct']==0
          and not special['three_roles']['meta'] and not special['no_edge']['meta']
          and special['duplicate']['status']=='raw_world_duplicate'
          and special['competing_relations']['promotions']>=2
          and special['competing_relations']['observation']=='raw_world_ambiguous'
          and not special['competing_relations']['meta']
          and treatment['action_score']['p95_ms']<=10)
    output={'preregistration':'prereg/F-6b-geometria-roles-observados.md',
            'kind':'development_only','base_engine_tree':git('rev-parse','HEAD:leobot'),
            'working_engine_changes':git('status','--porcelain','--','leobot'),
            'variants':variants,'special_controls':special,
            'gate_passed':bool(gate),'wall_s':round(time.monotonic()-start,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6b_role_geometry_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'gate_passed':gate,'special_controls':special,
                      'variants':[{key:value for key,value in row.items()
                                   if key in ('name','action_statuses','action_score',
                                              'procedure_statuses','procedure_score',
                                              'counter_status','after_counter','cpu_total_s')}
                                  for row in variants],
                      'wall_s':output['wall_s'],'max_rss_kib':output['max_rss_kib']},
                     ensure_ascii=False))


if __name__=='__main__':
    main()

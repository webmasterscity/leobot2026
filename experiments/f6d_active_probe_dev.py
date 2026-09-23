"""F-6d development: ask one intervention, then learn either observed outcome."""
from __future__ import annotations

import json
import resource
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.b1_aggregate_operator import ROOT, git
from experiments.f6b_role_geometry_freeze import (
    FAMILIES, action_episode, names, remove_transfer, source_experience, train_action,
    train_procedure, evaluate_procedure,
)


PREFIX='f6ddev';SEED=12345;SPEC=FAMILIES[2]


def clock(fn):
    start=time.process_time();result=fn()
    return result,round(time.process_time()-start,6)


def reload(bot):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json';bot.save(path)
        size=path.stat().st_size
        loaded=Bot.load(path)
    return loaded,size


def environment_result(request,branch):
    before={tuple(row) for row in request['before']}
    if branch=='necessary':
        return before
    old=next(row for row in before if row[0]==PREFIX+'loc')
    link=next(row for row in before if row[0]==PREFIX+'link')
    return (before-{old})|{(old[0],old[1],link[2])}


def score(bot,branch):
    full=full_correct=missing=missing_correct=unsafe=no_link=no_loc=0
    times=[]
    for index in range(1000,1064):
        cue,before,_,destination=action_episode(SPEC,PREFIX,SEED,index)
        with_item=index%2==0
        if not with_item:
            before={row for row in before if row[0]!=PREFIX+'inventory'}
        tick=time.perf_counter()
        result=bot.execute_symbolic_transition(cue,before)
        times.append((time.perf_counter()-tick)*1000)
        executed=result.get('status')=='executed_symbolic_action'
        correct_result=executed and destination in set(result.get('result',()))
        if with_item:
            full+=1;full_correct+=correct_result
        else:
            missing+=1
            missing_correct+=correct_result if branch=='irrelevant' else not executed
            unsafe+=executed and branch=='necessary'
        without_link={row for row in before if row[0]!=PREFIX+'link'}
        without_loc={row for row in before if row[0]!=PREFIX+'loc'}
        no_link+=bot.execute_symbolic_transition(cue,without_link).get('status')=='executed_symbolic_action'
        no_loc+=bot.execute_symbolic_transition(cue,without_loc).get('status')=='executed_symbolic_action'
    times.sort()
    return {'full':full,'full_correct':full_correct,'missing':missing,
            'missing_correct':missing_correct,'unsafe':unsafe,
            'unsafe_without_link':no_link,'unsafe_without_location':no_loc,
            'p50_ms':round((times[31]+times[32])/2,5),
            'p95_ms':round(times[60],5)}


def train(mode):
    bot=Bot()
    if mode!='fresh':
        source_experience(bot,SPEC,PREFIX,SEED)
    if mode=='same_information_no_meta':
        remove_transfer(bot)
    reports=train_action(bot,SPEC,PREFIX,SEED)
    return bot,reports


def branch(name):
    bot,reports=train('treatment')
    request=reports[-1].get('evidence_request')
    if request is None:
        return {'branch':name,'failure':'no_evidence_request','reports':[r['status'] for r in reports]}
    before_sessions=set(bot.symbolic.sessions)
    (bot,bytes_saved),restart_cpu=clock(lambda:reload(bot))
    pending_same=(bot.symbolic.sessions[reports[-1]['pattern']].get('evidence_request')==request)
    before=score(bot,'necessary')
    observed=environment_result(request,name)
    feedback,feedback_cpu=clock(lambda:bot.observe_symbolic_transition(
        request['text'],request['before'],observed))
    after=score(bot,name)
    same_session=set(bot.symbolic.sessions)==before_sessions
    (loaded,bytes_after),restart_after_cpu=clock(lambda:reload(bot))
    reloaded_score=score(loaded,name)
    persisted=all(reloaded_score[key]==after[key] for key in (
        'full_correct','missing_correct','unsafe',
        'unsafe_without_link','unsafe_without_location'))
    label,procedure_reports=train_procedure(bot,PREFIX,0)
    procedure_score=evaluate_procedure(bot,label,2117)
    action_depends_on_meta=bool(bot.symbolic.operators()[0].get('cross_modal_sources'))
    row=names(PREFIX,3,SEED)
    counter_before={(PREFIX+'signal',row['p'],row['i'],'closed'),
                    (PREFIX+'destination',row['d'])}
    counter_after={(PREFIX+'signal',row['p'],row['i'],'open'),
                   (PREFIX+'destination',row['d'])}
    counter=bot.observe_world_transition(counter_before,counter_after)
    withdrawn_action=score(bot,name)['full_correct']==0
    withdrawn_procedure=evaluate_procedure(bot,label,2117)['correct']==0
    return {'branch':name,'before_training_statuses':[r['status'] for r in reports],
            'request':request,'pending_restart_same':pending_same,
            'before':before,'feedback_status':feedback.get('status'),
            'feedback_pattern':feedback.get('pattern'),'same_session':same_session,
            'after':after,'after_restart_same':persisted,
            'procedure_status':procedure_reports[-1]['status'],
            'procedure_correct':procedure_score['correct'],
            'action_depends_on_meta':action_depends_on_meta,
            'counter_status':counter['status'],
            'withdrawn_action':withdrawn_action,
            'withdrawn_procedure':withdrawn_procedure,
            'saved_bytes':bytes_saved,'saved_bytes_after':bytes_after,
            'restart_cpu_s':restart_cpu,'feedback_cpu_s':feedback_cpu,
            'restart_after_cpu_s':restart_after_cpu}


def main():
    start=time.process_time()
    necessary=branch('necessary');irrelevant=branch('irrelevant')
    fresh,fr=train('fresh');no_meta,nm=train('same_information_no_meta')
    incompatible_bot,incompatible_reports=train('treatment')
    incompatible_request=incompatible_reports[-1].get('evidence_request')
    incompatible_after=set(tuple(x) for x in incompatible_request['before'])
    incompatible_after.add((PREFIX+'new_effect','unmentioned_entity'))
    incompatible_result=incompatible_bot.observe_symbolic_transition(
        incompatible_request['text'],incompatible_request['before'],incompatible_after)
    auxiliary_bot=Bot()
    source_experience(auxiliary_bot,FAMILIES[0],PREFIX+'aux',SEED)
    auxiliary_reports=train_action(auxiliary_bot,FAMILIES[0],PREFIX+'aux',SEED)
    controls={'fresh_status':fr[-1]['status'],'no_meta_status':nm[-1]['status'],
              'fresh_correct':score(fresh,'necessary')['full_correct'],
              'no_meta_correct':score(no_meta,'necessary')['full_correct'],
              'incompatible_status':incompatible_result['status'],
              'incompatible_operator_count':len(incompatible_bot.symbolic.operators()),
              'unmentioned_auxiliary_status':auxiliary_reports[-1]['status']}
    gates=[]
    for row in (necessary,irrelevant):
        after=row.get('after',{})
        gates.append(row.get('before_training_statuses',())[-1:] == ['pending_discriminating_evidence']
                     and row.get('pending_restart_same') and row.get('same_session')
                     and row.get('feedback_status')=='operator_learned'
                     and row.get('after_restart_same')
                     and row.get('counter_status')=='raw_world_conflict'
                     and row.get('withdrawn_action')==row.get('action_depends_on_meta')
                     and row.get('withdrawn_procedure')
                     and after.get('full_correct')==32 and after.get('missing_correct')==32
                     and after.get('unsafe')==0 and after.get('unsafe_without_link')==0
                     and after.get('unsafe_without_location')==0
                     and after.get('p95_ms',100)>0 and after.get('p95_ms',100)<=10)
    output={'preregistration':'prereg/F-6d-prueba-activa-de-precondicion.md',
            'kind':'development_only','base_engine_tree':git('rev-parse','HEAD:leobot'),
            'working_engine_changes':git('status','--porcelain','--','leobot'),
            'necessary':necessary,'irrelevant':irrelevant,'controls':controls,
            'gate_passed':all(gates) and controls['fresh_correct']==0 and controls['no_meta_correct']==0
                          and controls['incompatible_status']=='ungrounded_transition'
                          and controls['incompatible_operator_count']==0
                          and controls['unmentioned_auxiliary_status']=='operator_learned',
            'cpu_s':round(time.process_time()-start,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6d_active_probe_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('necessary','irrelevant')}
                     | {'branches':[{key:value for key,value in row.items()
                                     if key not in ('request',)}
                                    for row in (necessary,irrelevant)]},ensure_ascii=False))


if __name__=='__main__':
    main()

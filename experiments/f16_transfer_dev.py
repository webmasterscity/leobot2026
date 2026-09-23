"""F-16 frozen-engine cross-structure transfer gate on three human corpora."""
from __future__ import annotations

import json
import resource
import statistics
import time
from collections import Counter
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.f16_defeasible_baselines import FAMILIES,load
from experiments.f16_update_learner import LABELS,UpdateLearner


ROOT=Path(__file__).resolve().parents[1]


def adapt(rows,family):
    # Data-field adapter only; it never interprets the prose or supplies labels.
    return [{'group':row['GroupId'],
             'information':row['Premise'] if family!='defeasible-social' else None,
             'claim':row['Hypothesis'],'update':row['Update'],
             'label':row['UpdateType']} for row in rows]


def first_groups(rows,count):
    found=set();selected=[]
    for row in rows:
        if row['group'] not in found:
            if len(found)==count:break
            found.add(row['group'])
        selected.append(row)
    return selected


def metrics(rows,predictions):
    totals=Counter();correct=Counter();attempts=0
    for row,pred in zip(rows,predictions):
        label=row['label'];totals[label]+=1
        if pred is not None:
            attempts+=1;correct[label]+=pred==label
    total=sum(totals.values());hits=sum(correct.values())
    return {'total':total,'correct':hits,'attempts':attempts,
            'macro_accuracy':round(sum(correct[label]/max(1,totals[label])
                                  for label in LABELS)/len(LABELS),6),
            'precision':round(hits/attempts,6) if attempts else None,
            'coverage':round(attempts/total,6) if total else 0.0,
            'by_label':{label:{'correct':correct[label],
                               'total':totals[label]} for label in LABELS}}


def assess(model,rows):
    predictions=[];times=[]
    for row in rows:
        tick=time.perf_counter();predictions.append(model.predict(row))
        times.append((time.perf_counter()-tick)*1000)
    result=metrics(rows,predictions);times.sort()
    result.update(p50_ms=round(statistics.median(times),5),
                  p95_ms=round(times[(95*len(times)+99)//100-1],5))
    return result


def run_curve(train,validation,development,prior):
    stages=[]
    for count in (100,250,500,1000):
        subset=first_groups(train,count)
        learner=UpdateLearner();tick=time.process_time()
        fitted=learner.fit(subset);fit_cpu=time.process_time()-tick
        selected=learner.select_program(validation,metrics,prior=prior)
        educated_result=assess(learner,development)
        fresh_selected=learner.select_program(validation,metrics)
        fresh_result=assess(learner,development)
        stages.append({'groups':count,'examples':len(subset),
                       'shared_fit':fitted,'shared_fit_cpu_s':round(fit_cpu,6),
                       'educated_selection':selected,'educated':educated_result,
                       'fresh_selection':fresh_selected,'fresh':fresh_result})
    return stages


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    inventory=json.loads((ROOT/'results_v3'/'f16_defeasible_inventory.json').read_text())
    baselines=json.loads((ROOT/'results_v3'/'f16_defeasible_baselines.json').read_text())
    source=json.loads((ROOT/'results_v3'/'f15_relation_dev.json').read_text())
    program=source['selection']['best_raw_program']
    if program['comparison']!=['added','other_new']:
        raise RuntimeError('Prior F-15 diferente del preregistro')
    # A structural hint only: no F-15 label or trained weight enters this model.
    prior=('claim','overlap_binary')
    results={}
    for family in FAMILIES:
        train,validation,development,partition=load(
            family,tree,inventory['files'][family+'/train.jsonl']['sha256'])
        curve=run_curve(adapt(train,family),adapt(validation,family),
                        adapt(development,family),prior)
        results[family]={'partition':partition,'stages':curve,
                         'lexical_control':baselines['families'][family]['lexical_update']}
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    gates={}
    for family,entry in results.items():
        last=entry['stages'][-1];got=last['educated'];control=entry['lexical_control']
        threshold=0.7 if family=='defeasible-snli' else 0.65
        gates[family]=(got['macro_accuracy']>=threshold and
            (got['precision'] or 0)>=0.8 and got['coverage']>=0.5 and
            got['macro_accuracy']>=control['macro_accuracy']+0.05 and
            got['p95_ms']<=10)
    transfer=False
    if all(gates.values()):
        transfer=all(results[family]['stages'][-1]['educated_selection']['descriptions']<=
            0.8*results[family]['stages'][-1]['fresh_selection']['descriptions'] and
            results[family]['stages'][-1]['educated']['macro_accuracy']>=
            results[family]['stages'][-1]['fresh']['macro_accuracy']
            for family in ('defeasible-snli','defeasible-atomic'))
    output={'preregistration':'prereg/F-16-transferencia-igualdad-actualizaciones.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'source_prior':'F-15 unpromoted structural recommendation',
            'prior_descriptor':list(prior),'families':results,'family_gates':gates,
            'transfer_gate_passed':bool(unchanged and transfer),
            'adversarial_restart_controls':'pending_if_family_and_transfer_gates_pass',
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f16_transfer_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'engine_tree':tree,'engine_unchanged':unchanged,
      'family_gates':gates,'transfer_gate_passed':output['transfer_gate_passed'],
      'families':{name:[{'groups':x['groups'],
                         'educated_selection':x['educated_selection']['status'],
                         'educated_descriptions':x['educated_selection']['descriptions'],
                         'educated_macro':x['educated']['macro_accuracy'],
                         'fresh_descriptions':x['fresh_selection']['descriptions'],
                         'fresh_macro':x['fresh']['macro_accuracy']}
                        for x in row['stages']] for name,row in results.items()},
      'cpu_total_s':output['cpu_total_s'],
      'wall_total_s':output['wall_total_s'],
      'max_rss_kib':output['max_rss_kib']},ensure_ascii=False))


if __name__=='__main__':main()

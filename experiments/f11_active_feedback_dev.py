"""F-11: frozen-engine active feedback curve against three random orders."""
from __future__ import annotations

import json
import random
import resource
import time
from hashlib import sha256
from pathlib import Path

from experiments.f6e_human_text_grounding import download_split
from experiments.f6f_anchored_constructions_pilot import train_partition
from experiments.f6g_learned_normalization_pilot import partition as f6g_partition
from experiments.f7_typed_sequences_dev import git,select_webnlg
from experiments.f8_span_programs_dev import split_web
from experiments.f10_pattern_ceiling import split as f10_split
from experiments.f10_contrastive_grammar import ContrastiveGrammar
from experiments.f10_contrastive_dev import evaluate
from experiments.f11_active_contrasts import select_queries


ROOT=Path(__file__).resolve().parents[1]


def split(rows,tree):
    previous={row['id'] for row in train_partition(rows,tree)[1]}
    previous.update(row['id'] for row in f6g_partition(rows,tree)[2])
    previous.update(row['id'] for row in select_webnlg(rows,tree)[1])
    previous.update(row['id'] for row in split_web(rows,tree)[2])
    _,f10_valid,f10_held,_=f10_split(rows,tree)
    previous.update(row['id'] for row in (*f10_valid,*f10_held))
    ranked=sorted((row for row in rows if row['id'] not in previous),
        key=lambda row:(sha256((tree+':F-11:web:'+row['id']).encode()).hexdigest(),
                        row['id']))
    held=[];used=set()
    for row in ranked:
        if row['subject'] in used or row['object'] in used:continue
        held.append(row);used.update((row['subject'],row['object']))
        if len(held)==128:break
    validation=[]
    held_ids={row['id'] for row in held}
    for row in ranked:
        if row['id'] in held_ids or row['subject'] in used or row['object'] in used:
            continue
        validation.append(row);used.update((row['subject'],row['object']))
        if len(validation)==64:break
    reserved={row['id'] for row in (*held,*validation)}
    available=[row for row in ranked if row['id'] not in reserved and
               row['subject'] not in used and row['object'] not in used]
    return available[:400],available[400:800],validation,held,len(previous)


def curve(seed_rows,pool,validation,held,policy,random_seed=None):
    labeled=list(seed_rows);remaining={row['id']:row for row in pool}
    rng=random.Random(random_seed)
    stages=[];selector_cpu=learning_cpu=assessment_cpu=0.0
    for stage in range(6):
        if stage:
            if policy=='active':
                unlabeled=[{'id':row['id'],'text':row['text']}
                           for row in remaining.values()]
                picked,selection=select_queries(labeled,unlabeled,20)
                selector_cpu+=selection['cpu_s']
            else:
                picked=rng.sample(sorted(remaining),20)
                selection={'programs':None,'rival_texts':None,
                           'representation_gaps':None,'analyses':0,'cpu_s':0.0}
            labeled.extend(remaining.pop(identifier) for identifier in picked)
        else:
            selection={'programs':None,'rival_texts':None,
                       'representation_gaps':None,'analyses':0,'cpu_s':0.0}
        model=ContrastiveGrammar();tick=time.process_time()
        learning=model.train(labeled,validation)
        step_learning=time.process_time()-tick;learning_cpu+=step_learning
        tick=time.process_time();score=evaluate(model,held)
        step_assessment=time.process_time()-tick;assessment_cpu+=step_assessment
        stages.append({'examples':len(labeled),'requested':len(labeled)-len(seed_rows),
                       'selection':selection,'learning':learning,'score':score,
                       'learning_cpu_s':round(step_learning,6),
                       'assessment_cpu_s':round(step_assessment,6)})
    return {'policy':policy,'random_seed':random_seed,'stages':stages,
            'selector_cpu_s':round(selector_cpu,6),
            'learning_cpu_s':round(learning_cpu,6),
            'assessment_cpu_s':round(assessment_cpu,6),
            'synthesis_candidates':sum(stage['learning']['source_pairs']+
                                       stage['learning']['candidate_programs']
                                       for stage in stages),
            'total_measured_cpu_s':round(selector_cpu+learning_cpu+assessment_cpu,6)}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    rows,sources,source_bytes=download_split('train')
    seed,pool,validation,held,previous=split(rows,tree)
    if min(len(seed),len(pool))<400 or len(validation)<64 or len(held)<128:
        raise RuntimeError('Partición preregistrada sin datos suficientes')
    active=curve(seed,pool,validation,held,'active')
    random_curves=[curve(seed,pool,validation,held,'random',seed_number)
                   for seed_number in (17,53,97)]
    final=active['stages'][-1]['score'];others=[run['stages'][-1]['score']
                                               for run in random_curves]
    average_correct=sum(row['correct'] for row in others)/len(others)
    average_cpu=sum(run['total_measured_cpu_s'] for run in random_curves)/len(random_curves)
    random_candidates=sum(run['synthesis_candidates'] for run in random_curves)/len(random_curves)
    early=max((stage['score']['correct'] for stage in active['stages']
               if stage['requested']<=80),default=0)
    preliminary=(final['correct']>=5 and final['attempts']>0 and
                 final['precision'] is not None and final['precision']>=0.8 and
                 final['correct']>=average_correct+3 and
                 active['total_measured_cpu_s']<=1.5*average_cpu and
                 ((average_correct>0 and early>=average_correct) or
                  (random_candidates>0 and
                   active['synthesis_candidates']<=0.8*random_candidates)) and
                 final['p95_ms']<=10)
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    # Remaining adversarial, correction and restart controls are only useful if
    # active selection passes its preregistered capability/cost gate.
    output={'preregistration':'prereg/F-11-consulta-activa-contrastes.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'source_hashes':sources,'source_bytes':source_bytes,
            'previous_development_ids_excluded':previous,
            'initial_examples':len(seed),'unlabeled_pool':len(pool),
            'validation':len(validation),'development':len(held),
            'active':active,'random_controls':random_curves,
            'random_mean_correct_100':average_correct,
            'random_mean_cpu_s':round(average_cpu,6),
            'preliminary_gate_passed':bool(preliminary and unchanged),
            'adversarial_controls':'pending_if_preliminary_passes',
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f11_active_feedback_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('source_hashes','active','random_controls')}
                     |{'active_stages':[(row['requested'],row['score']['correct'],
                        row['score']['attempts']) for row in active['stages']],
                       'random_final':[(run['random_seed'],
                        run['stages'][-1]['score']['correct'],
                        run['stages'][-1]['score']['attempts'])
                        for run in random_curves]},ensure_ascii=False))


if __name__=='__main__':main()

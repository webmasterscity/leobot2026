"""F-10 development gate after preregistered candidate-coverage ceiling."""
from __future__ import annotations

import json
import resource
import statistics
import tempfile
import time
from pathlib import Path

from experiments.f6e_human_text_grounding import download_split
from experiments.f6f_anchored_constructions_pilot import (
    AnchoredConstructions,evaluate as baseline_evaluate,
)
from experiments.f7_typed_sequences_dev import git
from experiments.f10_pattern_ceiling import split
from experiments.f10_contrastive_grammar import ContrastiveGrammar


ROOT=Path(__file__).resolve().parents[1]


def evaluate(model,rows):
    correct=attempts=wrong=candidates=0;latencies=[]
    for row in rows:
        tick=time.perf_counter()
        prediction=model.predict(row['text'])
        latencies.append((time.perf_counter()-tick)*1000)
        candidates+=prediction['candidates']
        if prediction['status']!='parsed':continue
        attempts+=1
        exact=(prediction['predicate']==row['predicate'] and
               prediction['args']==(row['subject'],row['object']))
        correct+=exact;wrong+=not exact
    latencies.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'wrong_confident':wrong,'precision':round(correct/attempts,6)
            if attempts else None,'candidates':candidates,
            'p50_ms':round(statistics.median(latencies),5),
            'p95_ms':round(latencies[(95*len(latencies)+99)//100-1],5)}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    ceiling=json.loads((ROOT/'results_v3'/'f10_pattern_ceiling.json').read_text())
    if not ceiling['ceiling_gate_passed'] or ceiling['engine_tree']!=tree:
        raise RuntimeError('Puerta previa de cobertura no satisfecha')
    rows,_,_=download_split('train')
    fit,validation,held,previous=split(rows,tree)
    model=ContrastiveGrammar();tick=time.process_time()
    learning=model.train(fit,validation)
    learning_cpu=time.process_time()-tick
    treatment=evaluate(model,held)
    base=AnchoredConstructions();tick=time.process_time()
    for row in fit:base.observe(row)
    base_learning=base.compile();base_cpu=time.process_time()-tick
    baseline=baseline_evaluate(base,held)
    ordered=sorted(fit,key=lambda row:row['id'])
    shuffled=[{**row,'predicate':ordered[(i+1)%len(ordered)]['predicate']}
              for i,row in enumerate(ordered)]
    bad=ContrastiveGrammar();tick=time.process_time()
    bad_learning=bad.train(shuffled,validation)
    bad_cpu=time.process_time()-tick
    shuffled_result=evaluate(bad,held)
    inverted=[{**row,'subject':row['object'],'object':row['subject']}
              for row in fit]
    reverse=ContrastiveGrammar();tick=time.process_time()
    reverse_learning=reverse.train(inverted,validation)
    reverse_cpu=time.process_time()-tick
    inverted_result=evaluate(reverse,held)
    tick=time.process_time()
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'grammar.json'
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        restored=ContrastiveGrammar.from_dict(json.loads(path.read_text(encoding='utf8')))
        stored_bytes=path.stat().st_size
    restart_cpu=time.process_time()-tick
    restarted=evaluate(restored,held)
    restart_same=(restarted['correct']==treatment['correct'] and
                  restarted['attempts']==treatment['attempts'])
    correction=None
    if model.programs:
        first=model.programs[0];source=first['dependencies'][0]
        old=next(row for row in fit if row['id']==source)
        alternative=next(row['predicate'] for row in fit
                         if row['predicate']!=old['predicate'])
        tick=time.process_time()
        changed=model.correct(source,{**old,'predicate':alternative})
        correction={'changed':changed,
                    'source_removed_from_original_dependencies':all(
                       source not in row['dependencies'] for row in model.programs
                       if row['program']==first['program'] and
                          row['predicate']==first['predicate']),
                    'cpu_s':round(time.process_time()-tick,6)}
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    gate=(unchanged and treatment['correct']>=20 and
          treatment['attempts']>0 and treatment['precision']>=0.8 and
          treatment['correct']>=baseline['correct']+5 and
          bad_learning['promoted']==0 and shuffled_result['attempts']==0 and
          reverse_learning['promoted']==0 and inverted_result['attempts']==0 and
          restart_same and correction is not None and changed and
          correction['source_removed_from_original_dependencies'] and
          treatment['p95_ms']<=10 and learning_cpu<=120)
    output={'preregistration':'prereg/F-10-gramatica-composicional-contrastiva.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'prior_ids_excluded':previous,'fit_offered':len(fit),
            'validation':len(validation),'heldout':len(held),
            'learning':learning,'treatment':treatment,
            'baseline_learning':base_learning,'baseline':baseline,
            'shuffled_learning':bad_learning,'shuffled':shuffled_result,
            'inverted_learning':reverse_learning,'inverted':inverted_result,
            'restart_same':restart_same,'correction':correction,
            'stored_bytes':stored_bytes,'learning_cpu_s':round(learning_cpu,6),
            'baseline_cpu_s':round(base_cpu,6),'shuffled_cpu_s':round(bad_cpu,6),
            'inverted_cpu_s':round(reverse_cpu,6),
            'restart_cpu_s':round(restart_cpu,6),'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f10_contrastive_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

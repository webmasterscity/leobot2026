"""F-12 development on human text plus natural held-out recombinations."""
from __future__ import annotations

import json
import resource
import statistics
import tempfile
import time
from pathlib import Path

from experiments.f6e_human_text_grounding import download_split
from experiments.f6f_anchored_constructions_pilot import (
    AnchoredConstructions,evaluate as old_evaluate,
)
from experiments.f7_typed_sequences_dev import git
from experiments.f10_contrastive_grammar import ContrastiveGrammar
from experiments.f10_contrastive_dev import evaluate as f10_evaluate
from experiments.f12_factor_inventory import partition,structural_partition
from experiments.f12_factorized_grammar import FactorizedGrammar


ROOT=Path(__file__).resolve().parents[1]


def evaluate(model,rows):
    correct=attempts=wrong=candidates=analyses=0;times=[]
    for row in rows:
        tick=time.perf_counter();result=model.predict(row['text'])
        times.append((time.perf_counter()-tick)*1000)
        candidates+=result['candidates'];analyses+=result['analyses']
        if result['status']!='parsed':continue
        attempts+=1
        exact=(result['predicate']==row['predicate'] and
               result['args']==(row['subject'],row['object']))
        correct+=exact;wrong+=not exact
    times.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'wrong_confident':wrong,'precision':round(correct/attempts,6)
            if attempts else None,'candidates':candidates,'analyses':analyses,
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[(95*len(times)+99)//100-1],5)}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    inventory=json.loads((ROOT/'results_v3'/'f12_factor_inventory.json').read_text())
    if inventory['engine_tree']!=tree or not inventory['structural_gate_possible']:
        raise RuntimeError('Partición estructural preregistrada no evaluable')
    rows,_,_=download_split('train')
    available,validation,held,previous=partition(rows,tree)
    fit,structural,structural_counts=structural_partition(available,tree)
    if len(structural)<32:raise RuntimeError('Menos de 32 combinaciones disponibles')
    structural_rows=[item['row'] for item in structural]
    model=FactorizedGrammar();tick=time.process_time()
    learning=model.train(fit,validation)
    learning_cpu=time.process_time()-tick
    general=evaluate(model,held);composed=evaluate(model,structural_rows)
    baseline=AnchoredConstructions();tick=time.process_time()
    for row in fit:baseline.observe(row)
    old_learning=baseline.compile();old_cpu=time.process_time()-tick
    old_general=old_evaluate(baseline,held)
    old_composed=old_evaluate(baseline,structural_rows)
    earlier=ContrastiveGrammar();tick=time.process_time()
    earlier_learning=earlier.train(fit,validation)
    earlier_cpu=time.process_time()-tick
    f10_general=f10_evaluate(earlier,held)
    f10_composed=f10_evaluate(earlier,structural_rows)
    ordered=sorted(fit,key=lambda row:row['id'])
    shuffled=[{**row,'predicate':ordered[(i+1)%len(ordered)]['predicate']}
              for i,row in enumerate(ordered)]
    bad=FactorizedGrammar();tick=time.process_time()
    bad_learning=bad.train(shuffled,validation)
    bad_cpu=time.process_time()-tick
    bad_general=evaluate(bad,held)
    inverted=[{**row,'subject':row['object'],'object':row['subject']}
              for row in fit]
    reverse=FactorizedGrammar();tick=time.process_time()
    reverse_learning=reverse.train(inverted,validation)
    reverse_cpu=time.process_time()-tick
    reverse_general=evaluate(reverse,held)
    tick=time.process_time()
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'grammar.json'
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        restored=FactorizedGrammar.from_dict(json.loads(path.read_text(encoding='utf8')))
        stored_bytes=path.stat().st_size
    restart_cpu=time.process_time()-tick
    restart_general=evaluate(restored,held)
    restart_composed=evaluate(restored,structural_rows)
    restart_same=(restart_general['correct']==general['correct'] and
                  restart_general['attempts']==general['attempts'] and
                  restart_composed['correct']==composed['correct'] and
                  restart_composed['attempts']==composed['attempts'])
    correction=None
    if model.lexicon:
        phrase,item=next(iter(sorted(model.lexicon.items())))
        source=item['dependencies'][0]
        old=next(row for row in fit if row['id']==source)
        alternative=next(row['predicate'] for row in fit
                         if row['predicate']!=old['predicate'])
        tick=time.process_time()
        changed=model.correct(source,{**old,'predicate':alternative})
        correction={'changed':changed,'source_withdrawn':source not in
                    model.lexicon.get(phrase,{}).get('dependencies',()),
                    'cpu_s':round(time.process_time()-tick,6)}
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    gate=(unchanged and general['correct']>=20 and
          general['attempts']>0 and general['precision']>=0.8 and
          general['correct']>=max(old_general['correct'],f10_general['correct'])+5 and
          composed['correct']>=20 and composed['attempts']>0 and
          composed['precision']>=0.8 and
          composed['correct']>=old_composed['correct']+5 and
          bad_learning['promoted_expressions']==0 and bad_general['attempts']==0 and
          reverse_general['attempts']==0 and restart_same and
          correction is not None and correction['source_withdrawn'] and
          general['p95_ms']<=10 and composed['p95_ms']<=10 and learning_cpu<=120)
    output={'preregistration':'prereg/F-12-gramatica-factorizada.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'previous_evaluation_ids_excluded':previous,
            'fit_offered':len(fit),'validation':len(validation),'general_heldout':len(held),
            'structural_partition':structural_counts,'learning':learning,
            'general':general,'structural':composed,
            'f6f_learning':old_learning,'f6f_general':old_general,
            'f6f_structural':old_composed,
            'f10_learning':earlier_learning,'f10_general':f10_general,
            'f10_structural':f10_composed,
            'shuffled_learning':bad_learning,'shuffled_general':bad_general,
            'inverted_learning':reverse_learning,'inverted_general':reverse_general,
            'restart_same':restart_same,'correction':correction,
            'stored_bytes':stored_bytes,'learning_cpu_s':round(learning_cpu,6),
            'f6f_cpu_s':round(old_cpu,6),'f10_cpu_s':round(earlier_cpu,6),
            'shuffled_cpu_s':round(bad_cpu,6),
            'inverted_cpu_s':round(reverse_cpu,6),
            'restart_cpu_s':round(restart_cpu,6),'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f12_factorized_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

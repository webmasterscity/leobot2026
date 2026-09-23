"""F-10 preregistered feasibility gate; reads only WebNLG train development."""
from __future__ import annotations

import json
import resource
import time
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f6e_human_text_grounding import download_split
from experiments.f6f_anchored_constructions_pilot import train_partition
from experiments.f6g_learned_normalization_pilot import partition as f6g_partition
from experiments.f7_typed_sequences_dev import git,select_webnlg
from experiments.f8_span_programs_dev import split_web
from experiments.f10_contrastive_grammar import episode,generate,parse,_tokens
from leobot.language import normalize


ROOT=Path(__file__).resolve().parents[1]


def split(rows,tree):
    prior={row['id'] for row in train_partition(rows,tree)[1]}
    prior.update(row['id'] for row in f6g_partition(rows,tree)[2])
    prior.update(row['id'] for row in select_webnlg(rows,tree)[1])
    prior.update(row['id'] for row in split_web(rows,tree)[2])
    ranked=sorted((row for row in rows if row['id'] not in prior),
                  key=lambda row:(sha256((tree+':F-10:web:'+row['id']).encode()).hexdigest(),
                                  row['id']))
    held=[];used=set()
    for row in ranked:
        if row['subject'] in used or row['object'] in used:continue
        held.append(row);used.update((row['subject'],row['object']))
        if len(held)==128:break
    validation=[]
    for row in ranked:
        if row in held or row['subject'] in used or row['object'] in used:continue
        if episode(row) is None:continue
        validation.append(row);used.update((row['subject'],row['object']))
        if len(validation)==64:break
    kept={row['id'] for row in (*held,*validation)}
    fit=[row for row in ranked if row['id'] not in kept and
         row['subject'] not in used and row['object'] not in used][:2000]
    return fit,validation,held,len(prior)


def indexed(patterns,fit):
    frequency=Counter()
    for row in fit:
        frequency.update({token for token,_,_ in _tokens(normalize(row['text']))})
    index=defaultdict(list)
    for number,item in enumerate(patterns):
        words=[value for kind,value in item['program'] if kind=='literal']
        if not words:continue
        anchor=min(words,key=lambda token:(frequency[token],token))
        index[anchor].append(number)
    return index


def ceiling(patterns,index,rows):
    analyzed=correct=wrong_pred=wrong_roles=candidates=0
    for row in rows:
        observed={token for token,_,_ in _tokens(normalize(row['text']))}
        choices={i for token in observed for i in index.get(token,())}
        candidates+=len(choices)
        possible=[]
        for number in sorted(choices):
            item=patterns[number]
            for args in parse(item['program'],row['text']):
                possible.append((item['predicate'],args))
        analyzed+=bool(possible)
        target=(row['predicate'],(row['subject'],row['object']))
        correct+=target in possible
        wrong_pred+=bool(possible) and all(pred!=row['predicate'] for pred,_ in possible)
        wrong_roles+=any(pred==row['predicate'] and args!=target[1]
                         for pred,args in possible)
    return {'total':len(rows),'analyzed':analyzed,'correct_possible':correct,
            'wrong_predicate_only':wrong_pred,'wrong_role_analyses':wrong_roles,
            'program_candidates':candidates}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    rows,sources,bytes_total=download_split('train')
    fit,validation,held,previous=split(rows,tree)
    tick=time.process_time();patterns,considered=generate(fit)
    generation_cpu=time.process_time()-tick
    tick=time.process_time();index=indexed(patterns,fit)
    indexing_cpu=time.process_time()-tick
    tick=time.process_time();coverage=ceiling(patterns,index,held)
    evaluation_cpu=time.process_time()-tick
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'preregistration':'prereg/F-10-gramatica-composicional-contrastiva.md',
            'kind':'development_ceiling_only','engine_tree':tree,
            'engine_unchanged':unchanged,'source_hashes':sources,
            'source_bytes':bytes_total,'prior_ids_excluded':previous,
            'fit_offered':len(fit),'fit_aligned':sum(episode(r) is not None for r in fit),
            'validation':len(validation),'heldout':len(held),
            'held_aligned':sum(episode(r) is not None for r in held),
            'patterns':len(patterns),'pairs_considered':considered,
            'coverage':coverage,'ceiling_gate_passed':coverage['correct_possible']>=25,
            'generation_cpu_s':round(generation_cpu,6),
            'indexing_cpu_s':round(indexing_cpu,6),
            'evaluation_cpu_s':round(evaluation_cpu,6),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f10_pattern_ceiling.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key!='source_hashes'},ensure_ascii=False))


if __name__=='__main__':main()

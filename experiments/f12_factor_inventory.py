"""F-12 partition and natural crossover inventory before learner implementation."""
from __future__ import annotations

import json
import resource
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f6e_human_text_grounding import download_split
from experiments.f6f_anchored_constructions_pilot import train_partition
from experiments.f6g_learned_normalization_pilot import partition as f6g_partition
from experiments.f7_typed_sequences_dev import git,select_webnlg
from experiments.f8_span_programs_dev import split_web
from experiments.f10_pattern_ceiling import split as f10_split
from experiments.f11_active_feedback_dev import split as f11_split
from experiments.f10_contrastive_grammar import episode
from experiments.f12_factorized_grammar import decompositions,REL


ROOT=Path(__file__).resolve().parents[1]
def partition(rows,tree):
    previous={row['id'] for row in train_partition(rows,tree)[1]}
    previous.update(row['id'] for row in f6g_partition(rows,tree)[2])
    previous.update(row['id'] for row in select_webnlg(rows,tree)[1])
    previous.update(row['id'] for row in split_web(rows,tree)[2])
    _,f10_val,f10_held,_=f10_split(rows,tree)
    _,_,f11_val,f11_held,_=f11_split(rows,tree)
    previous.update(row['id'] for row in (*f10_val,*f10_held,*f11_val,*f11_held))
    ranked=sorted((row for row in rows if row['id'] not in previous),
        key=lambda row:(sha256((tree+':F-12:web:'+row['id']).encode()).hexdigest(),
                        row['id']))
    held=[];used=set()
    for row in ranked:
        if row['subject'] in used or row['object'] in used:continue
        held.append(row);used.update((row['subject'],row['object']))
        if len(held)==128:break
    validation=[];held_ids={row['id'] for row in held}
    for row in ranked:
        if row['id'] in held_ids or row['subject'] in used or row['object'] in used:
            continue
        validation.append(row);used.update((row['subject'],row['object']))
        if len(validation)==64:break
    reserved={row['id'] for row in (*held,*validation)}
    available=[row for row in ranked if row['id'] not in reserved and
               row['subject'] not in used and row['object'] not in used][:2000]
    return available,validation,held,len(previous)


def inventory(available,tree):
    by_frame=defaultdict(lambda:defaultdict(set))
    by_phrase=defaultdict(lambda:defaultdict(set))
    by_combo=defaultdict(set)
    surfaces={}
    for row in available:
        ep=episode(row)
        if ep is None:continue
        surfaces[row['id']]=ep['surface']
        for frame,phrase in decompositions(row):
            pred=row['predicate']
            by_frame[frame][pred].add(row['id'])
            by_phrase[(pred,phrase)][frame].add(row['id'])
            by_combo[(frame,pred,phrase)].add(row['id'])
    candidates=[]
    for combo,ids in by_combo.items():
        frame,pred,phrase=combo
        other_preds={name for name,rows in by_frame[frame].items()
                     if name!=pred and len(rows-ids)>=2}
        other_frames={other for other,rows in by_phrase[(pred,phrase)].items()
                      if other!=frame and len(rows-ids)>=2}
        if not other_preds or not other_frames:continue
        # Hold out every identical surface, not just one lexicalisation id.
        expression_surfaces={surfaces[key] for key in ids}
        excluded={key for key,value in surfaces.items() if value in expression_surfaces}
        if not any(len(rows-excluded)>=2 for name,rows in by_frame[frame].items()
                   if name!=pred):continue
        if not any(len(rows-excluded)>=2 for other,rows in by_phrase[(pred,phrase)].items()
                   if other!=frame):continue
        key=sha256((tree+':F-12:struct:'+str(combo)).encode()).hexdigest()
        candidates.append((key,combo,ids,excluded))
    candidates.sort(key=lambda row:row[0])
    return candidates,{'aligned':len(surfaces),
                       'frames':len(by_frame),'phrases':len(by_phrase),
                       'combinations':len(by_combo),
                       'eligible_combinations':len(candidates),
                       'eligible_text_ids':len(set().union(*(row[2] for row in candidates)))
                       if candidates else 0}


def structural_partition(available,tree):
    candidates,_=inventory(available,tree)
    by_id={row['id']:row for row in available}
    by_frame=defaultdict(lambda:defaultdict(set))
    by_phrase=defaultdict(lambda:defaultdict(set))
    for row in available:
        for frame,phrase in decompositions(row):
            by_frame[frame][row['predicate']].add(row['id'])
            by_phrase[(row['predicate'],phrase)][frame].add(row['id'])
    removed=set();selected=[];entities=set()
    for _,combo,ids,excluded in candidates:
        if len(selected)>=64:break
        frame,pred,phrase=combo
        choices=[by_id[key] for key in sorted(ids) if key not in removed]
        choices=[row for row in choices if row['subject'] not in entities
                 and row['object'] not in entities]
        if not choices:continue
        chosen=choices[0]
        entity_ids={row['id'] for row in available
                    if row['subject'] in (chosen['subject'],chosen['object']) or
                       row['object'] in (chosen['subject'],chosen['object'])}
        trial=removed|excluded|entity_ids
        if not any(len(support-trial)>=2 for name,support in by_frame[frame].items()
                   if name!=pred):continue
        if not any(len(support-trial)>=2 for other,support in
                   by_phrase[(pred,phrase)].items() if other!=frame):continue
        selected.append({'row':chosen,'frame':frame,'phrase':phrase})
        removed=trial
        entities.update((chosen['subject'],chosen['object']))
    taught=[row for row in available if row['id'] not in removed]
    verified=[]
    for item in selected:
        frame=item['frame'];phrase=item['phrase'];pred=item['row']['predicate']
        if (any(len(support-removed)>=2 for name,support in by_frame[frame].items()
                if name!=pred) and
            any(len(support-removed)>=2 for other,support in
                by_phrase[(pred,phrase)].items() if other!=frame)):
            verified.append(item)
    return taught,verified,{'excluded_training_ids':len(removed),
                            'structural_selected':len(selected),
                            'structural_heldout':len(verified),
                            'taught_after_structural_split':len(taught)}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    rows,sources,source_bytes=download_split('train')
    available,validation,held,prior=partition(rows,tree)
    candidates,counts=inventory(available,tree)
    taught,structural,structural_counts=structural_partition(available,tree)
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'preregistration':'prereg/F-12-gramatica-factorizada.md',
            'kind':'development_inventory_only','engine_tree':tree,
            'engine_unchanged':unchanged,'source_hashes':sources,
            'source_bytes':source_bytes,'previous_evaluation_ids_excluded':prior,
            'general_fit_available':len(available),'validation':len(validation),
            'general_heldout':len(held),'inventory':counts,
            'structural_partition':structural_counts,
            'structural_gate_possible':len(structural)>=32,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f12_factor_inventory.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key!='source_hashes'},ensure_ascii=False))


if __name__=='__main__':main()

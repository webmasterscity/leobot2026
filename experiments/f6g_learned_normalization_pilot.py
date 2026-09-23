"""F-6g: synthesize bounded string repairs from cross-fitted grounding errors."""
from __future__ import annotations

import json
import re
import resource
import statistics
import tempfile
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.b1_aggregate_operator import ROOT
from experiments.f6e_human_text_grounding import download_split, frozen
from experiments.f6f_anchored_constructions_pilot import AnchoredConstructions, evaluate as base_evaluate


def partition(rows,tree):
    ranked=sorted(rows,key=lambda row:(sha256(
        (tree+':F-6g:development:'+row['id']).encode()).hexdigest(),row['id']))
    held=[];reserved=set()
    for row in ranked:
        if row['subject'] in reserved or row['object'] in reserved:
            continue
        held.append(row);reserved.update((row['subject'],row['object']))
        if len(held)==128:break
    available=[row for row in rows if row['id'] not in {x['id'] for x in held}
               and row['subject'] not in reserved and row['object'] not in reserved]
    taught=sorted(available,key=lambda row:(sha256(
        (tree+':F-6g:teaching:'+row['id']).encode()).hexdigest(),row['id']))[:2000]
    proposal=[];verification=[]
    for row in taught:
        digest=int(sha256((tree+':F-6g:verify:'+row['id']).encode()).hexdigest()[:8],16)
        (verification if digest%5==0 else proposal).append(row)
    return proposal,verification,held,{'source_rows':len(rows),
                                       'teaching_rows':len(taught),
                                       'proposal_rows':len(proposal),
                                       'verification_rows':len(verification),
                                       'heldout_rows':len(held)}


def train(rows):
    model=AnchoredConstructions()
    for row in rows:model.observe(row)
    model.compile()
    return model


def program_candidates(surface,canonical):
    """Enumerate only bounded typed operations; parameters come from data."""
    out=[];left=surface.split();right=canonical.split()
    for length in (1,2):
        if len(left)>length and left[length:]==right:
            out.append((('drop_prefix',tuple(left[:length])),))
        if len(left)>length and left[:-length]==right:
            out.append((('drop_suffix',tuple(left[-length:])),))
    if any(char.isdigit() for char in surface):
        for char in sorted(set(surface)):
            if char.isalnum() or char.isspace():
                continue
            stripped=surface.replace(char,'')
            if stripped==canonical:
                out.append((('remove_char',char),))
            for size in (1,2,3):
                suffix=canonical[-size:]
                if (len(canonical)>size and stripped+suffix==canonical and
                        suffix and not suffix.isalpha()):
                    out.append((('remove_char',char),('append_suffix',suffix)))
    return sorted(set(out),key=lambda program:(len(program),str(program)))


def execute(program,value):
    result=value
    for op,parameter in program:
        if op=='drop_prefix':
            tokens=result.split()
            if tuple(tokens[:len(parameter)])!=parameter or len(tokens)<=len(parameter):
                return None
            result=' '.join(tokens[len(parameter):])
        elif op=='drop_suffix':
            tokens=result.split()
            if tuple(tokens[-len(parameter):])!=parameter or len(tokens)<=len(parameter):
                return None
            result=' '.join(tokens[:-len(parameter)])
        elif op=='remove_char':
            if not any(char.isdigit() for char in result) or parameter not in result:
                return None
            result=result.replace(parameter,'')
        elif op=='append_suffix':
            if not any(char.isdigit() for char in result) or result.endswith(parameter):
                return None
            result+=parameter
        else:
            raise ValueError('Operador fuera del DSL')
    return result if result!=value else None


def crossfit_candidates(rows,tree):
    folds=defaultdict(list)
    for row in rows:
        digest=int(sha256((tree+':F-6g:fold:'+row['id']).encode()).hexdigest()[:8],16)
        folds[digest%5].append(row)
    evidence=defaultdict(set);enumerated=0;parsed=0
    for index in range(5):
        model=train([row for fold,part in folds.items() if fold!=index for row in part])
        for row in folds[index]:
            prediction=model.language.parse(row['text'])
            if prediction['status']!='parsed' or prediction['frame'].get('pred')!=row['predicate']:
                continue
            parsed+=1
            for proposed,gold in zip(prediction['frame'].get('args',()),
                                     (row['subject'],row['object'])):
                if proposed==gold:continue
                programs=program_candidates(proposed,gold)
                enumerated+=len(programs)
                for program in programs:
                    evidence[program].add(gold)
    return evidence,{'crossfit_parsed':parsed,'programs_enumerated':enumerated,
                     'unique_programs':len(evidence)}


def verify_rules(evidence,model,rows):
    candidates={program for program,labels in evidence.items() if len(labels)>=5}
    reports={program:{'support':len(evidence[program]),'fixes':0,'harms':0}
             for program in candidates}
    for row in rows:
        prediction=model.language.parse(row['text'])
        if prediction['status']!='parsed':continue
        args=prediction['frame'].get('args',())
        for program in candidates:
            for original,gold in zip(args,(row['subject'],row['object'])):
                changed=execute(program,original)
                if changed is None:continue
                reports[program]['fixes']+=original!=gold and changed==gold
                reports[program]['harms']+=original==gold and changed!=gold
    promoted={program:stats for program,stats in reports.items()
              if stats['fixes']>=1 and stats['fixes']/(stats['fixes']+stats['harms'])>=0.95}
    return promoted,reports


def predict(model,rules,text):
    parsed=model.language.parse(text)
    if parsed['status']!='parsed':return parsed
    frame=dict(parsed['frame']);args=[]
    for value in frame.get('args',()):
        outputs={result for program in rules
                 if (result:=execute(program,value)) is not None}
        if len(outputs)>1:
            return {'status':'ambiguous_normalization','frame':None}
        args.append(next(iter(outputs)) if outputs else value)
    frame['args']=args
    return {'status':'parsed','frame':frame}


def evaluate(model,rules,rows):
    correct=attempts=wrong_pred=wrong_arg=0;times=[]
    for row in rows:
        tick=time.perf_counter();result=predict(model,rules,row['text'])
        times.append((time.perf_counter()-tick)*1000)
        if result['status']!='parsed':continue
        attempts+=1;frame=result['frame']
        pred_error=frame.get('pred')!=row['predicate']
        arg_error=frame.get('args')!=[row['subject'],row['object']]
        wrong_pred+=pred_error;wrong_arg+=arg_error
        correct+=not pred_error and not arg_error
    times.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'precision':round(correct/attempts,6) if attempts else None,
            'wrong_predicate':wrong_pred,'wrong_arguments':wrong_arg,
            'p50_ms':round(statistics.median(times),5),
            'p95_ms':round(times[(95*len(times)+99)//100-1],5)}


def encoded_rules(rules):
    return [{'program':[[op,list(value) if isinstance(value,tuple) else value]
                        for op,value in program],**stats}
            for program,stats in sorted(rules.items(),key=lambda item:str(item[0]))]


def main():
    start=time.monotonic();cpu=time.process_time();tree=frozen()
    rows,sources,source_bytes=download_split('train')
    proposal,verification,held,parts=partition(rows,tree)
    evidence,search=crossfit_candidates(proposal,tree)
    validation_model=train(proposal)
    rules,verification_reports=verify_rules(evidence,validation_model,verification)
    model=train(proposal+verification)
    baseline=base_evaluate(model,held)
    treatment=evaluate(model,rules,held)
    ordered=sorted(proposal+verification,key=lambda row:row['id'])
    shuffled=train([{**row,'predicate':ordered[(i+1)%len(ordered)]['predicate']}
                    for i,row in enumerate(ordered)])
    shuffled_control=evaluate(shuffled,rules,held)
    memory={'correct':0,'total':len(held)}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'candidate.json'
        path.write_text(json.dumps({'episodes':model.as_dict()['episodes'],
                                    'rules':encoded_rules(rules)},ensure_ascii=False),encoding='utf8')
        saved=json.loads(path.read_text(encoding='utf8'))
        restarted=AnchoredConstructions.from_dict({'episodes':saved['episodes']})
        restored={tuple((op,tuple(value) if isinstance(value,list) else value)
                        for op,value in row['program']):
                  {'support':row['support'],'fixes':row['fixes'],'harms':row['harms']}
                  for row in saved['rules']}
        restart_same=all(evaluate(restarted,restored,held)[key]==treatment[key]
                         for key in ('correct','attempts','wrong_predicate','wrong_arguments'))
        saved_bytes=path.stat().st_size
    # Development already fails the main quality gate. A dictionary deletion
    # would not verify rollback from an actual contradictory observation.
    rollback_ok=None
    unchanged=frozen()==tree
    gate=(unchanged and len(held)==128 and treatment['correct']>=20
          and treatment['attempts']>=25 and treatment['precision'] is not None
          and treatment['precision']>=0.8
          and treatment['correct']>=baseline['correct']
          and treatment['attempts']-treatment['correct']<baseline['attempts']-baseline['correct']
          and shuffled_control['correct']<=2
          and restart_same and rollback_ok is True and treatment['p95_ms']<=10)
    output={'preregistration':'prereg/F-6g-normalizacion-adquirida.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'source_bytes':source_bytes,'source_hashes':sources,'partition':parts,
            'search':search,'rules_promoted':encoded_rules(rules),
            'rules_verified':len(verification_reports),
            'baseline':baseline,'treatment':treatment,'memory_only':memory,
            'shuffled_control':shuffled_control,
            'restart_same':restart_same,'rollback_ok':rollback_ok,
            'saved_bytes':saved_bytes,'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-start,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6g_normalization_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items() if key!='source_hashes'},ensure_ascii=False))


if __name__=='__main__':
    main()

#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
from leobot import Bot,Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v53_dream_replay_shift.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def add_chain(bot,r,s,prefix,reverse=False):
    n=[f'{prefix}{i}' for i in range(5)]
    seq=[(s,n[0],n[1]),(r,n[1],n[2]),(s,n[2],n[3]),(r,n[3],n[4])] if reverse else [(r,n[0],n[1]),(s,n[1],n[2]),(r,n[2],n[3]),(s,n[3],n[4])]
    for pred,a,b in seq: bot.kb.add(Atom(pred,(a,b)),'world')
    return n[0],n[4]

def teach(bot,idx,reverse=False):
    r,s=f'r{idx}',f's{idx}'
    pos=[add_chain(bot,r,s,f'd{idx}a_',reverse),add_chain(bot,r,s,f'd{idx}b_',reverse)]
    neg=[]
    for j in range(2):
        a,b=f'd{idx}n{j}a',f'd{idx}n{j}b';bot.kb.add(Atom(f'other{idx}',(a,b)),'world');neg.append((a,b))
    surface=('reverso' if reverse else 'vinculo')+str(idx)
    for a,b in pos: out=bot.observe_concept_statement(f'{a} {surface} {b}')
    for a,b in neg: out=bot.observe_concept_statement(f'{a} no {surface} {b}')
    return out

def row(bot,idx,reverse):
    t=time.perf_counter();out=teach(bot,idx,reverse);ms=(time.perf_counter()-t)*1000
    l=out.get('learning',{});d=l.get('dream_replay_policy',{})
    return {'idx':idx,'regime':'reverse' if reverse else 'forward','attempts':l.get('invention_attempts'),
            'target_candidates':l.get('invention_total_target_candidates'),'ms':ms,
            'policy':bot.concepts.invention_candidate_policy,'regime_reset':bool(d.get('regime_reset')),
            'policy_updated':bool(d.get('updated')),'status':out.get('status')}

def main():
    before=code_hash(); bot=Bot();bot.concepts.max_relation_length=2
    rows=[]
    for i in range(8): rows.append(row(bot,i,False))
    for i in range(50,58): rows.append(row(bot,i,True))
    after=code_hash()
    forward=rows[:8];shift=rows[8:]
    result={'version':'V5.3-development','mechanism':'exact_history_replay_with_regret_rollback',
            'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
            'rows':rows,
            'summary':{'pre_shift_policy':forward[-1]['policy'],
                       'first_shift_attempts':shift[0]['attempts'],
                       'first_shift_regime_reset':shift[0]['regime_reset'],
                       'policy_after_first_shift':shift[0]['policy'],
                       'subsequent_shift_attempts':[x['attempts'] for x in shift[1:]],
                       'regime_resets':bot.concepts.invention_candidate_regime_resets,
                       'final_policy':bot.concepts.invention_candidate_policy}}
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()

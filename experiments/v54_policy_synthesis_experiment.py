#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from statistics import median
from leobot import Bot, Atom
from tests.test_meta_v54 import add_late_inversion_chain, teach_late_inversion

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v54_policy_synthesis.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def heldout(bot, idx, n=4):
    surface=f'invprofundo{idx}'; ok=0
    for j in range(n):
        a,b=add_late_inversion_chain(bot,idx,f'd{idx}h{j}_')
        ok += bot.query_concept(f'{a} {surface} {b}?').get('status')=='entailed'
    return ok,n

def run(n=40, fixed=None):
    bot=Bot(); bot.concepts.max_relation_length=2
    rows=[]
    default_inv=[(False,False),(False,True),(True,False),(True,True)]
    for i in range(n):
        # Isolate V5.4 candidate-policy synthesis from the older V5.3
        # inversion-order replay learner.
        bot.concepts.invention_policy_order=list(default_inv)
        if fixed is not None: bot.concepts.invention_candidate_policy=fixed
        t=time.perf_counter(); out=teach_late_inversion(bot,i); ms=(time.perf_counter()-t)*1000
        l=out.get('learning',{}); ok,total=heldout(bot,i)
        rows.append({'domain':i,'attempts':l.get('invention_attempts'),
                     'target_candidates':l.get('invention_total_target_candidates'),
                     'policy_used':l.get('invention_candidate_policy'),'policy_after':bot.concepts.invention_candidate_policy,'ms':ms,
                     'heldout':ok,'heldout_total':total})
        if fixed is not None: bot.concepts.invention_candidate_policy=fixed
    return bot,rows

def summarize(bot,rows):
    return {'domains':len(rows),'attempts_total':sum(r['attempts'] or 0 for r in rows),
            'target_candidates_total':sum(r['target_candidates'] or 0 for r in rows),
            'heldout_correct':sum(r['heldout'] for r in rows),
            'heldout_total':sum(r['heldout_total'] for r in rows),
            'median_ms':median(r['ms'] for r in rows),'final_policy':bot.concepts.invention_candidate_policy,
            'first_three':rows[:3],'last_three':rows[-3:]}

def main():
    before=code_hash(); treatment,trows=run(); control,crows=run(fixed='forward_first'); after=code_hash()
    result={'version':'V5.4-development','mechanism':'exact_replay_policy_synthesis',
            'policy_space':148,'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
            'treatment':summarize(treatment,trows),'legacy_forward_control':summarize(control,crows),
            'scope_note':'Policies are synthesized only from generic candidate metadata; replay scores only prefixes whose outcomes were historically observed.'}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()

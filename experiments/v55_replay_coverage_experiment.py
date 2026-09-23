#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
from statistics import median
from leobot import Bot
from tests.test_meta_v54 import teach_late_inversion
from tests.test_meta_v53 import teach_reverse_domain

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v55_replay_coverage.json'
DEFAULT_INV=[(False,False),(False,True),(True,False),(True,True)]

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def prepare(bot):
    bot.concepts.max_relation_length=2
    for i in range(3):
        bot.concepts.invention_policy_order=list(DEFAULT_INV)
        teach_late_inversion(bot,i)

def run(shadow_budget,n=30):
    bot=Bot();bot.concepts.invention_shadow_probe_budget=shadow_budget;prepare(bot)
    rows=[]
    for i in range(50,50+n):
        bot.concepts.invention_policy_order=list(DEFAULT_INV)
        t=time.perf_counter();out=teach_reverse_domain(bot,i);ms=(time.perf_counter()-t)*1000
        l=out['learning'];d=l.get('dream_replay_policy',{})
        rows.append({'domain':i,'online_attempts':l.get('invention_attempts',0),
                     'shadow_attempts':l.get('invention_shadow_attempts',0),
                     'online_candidates':l.get('invention_total_target_candidates',0),
                     'shadow_candidates':l.get('invention_shadow_target_candidates',0),
                     'all_candidates':l.get('invention_total_target_candidates_with_shadow',l.get('invention_total_target_candidates',0)),
                     'policy_used':l.get('invention_candidate_policy'),'policy_after':bot.concepts.invention_candidate_policy,
                     'regime_reset':bool(d.get('regime_reset')),'ms':ms})
    return bot,rows

def summary(bot,rows):
    return {'domains':len(rows),'online_attempts':sum(r['online_attempts'] for r in rows),
            'shadow_attempts':sum(r['shadow_attempts'] for r in rows),
            'online_candidates':sum(r['online_candidates'] for r in rows),
            'shadow_candidates':sum(r['shadow_candidates'] for r in rows),
            'all_candidates':sum(r['all_candidates'] for r in rows),
            'regime_resets':sum(r['regime_reset'] for r in rows),
            'median_ms':median(r['ms'] for r in rows),'final_policy':bot.concepts.invention_candidate_policy,
            'first_three':rows[:3],'last_three':rows[-3:]}

def main():
    before=code_hash();t,tr=run(24);c,cr=run(0);after=code_hash()
    result={'version':'V5.5-development','mechanism':'selective_exact_replay_tree_expansion',
            'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
            'treatment':summary(t,tr),'no_shadow_control':summary(c,cr),
            'scope_note':'Shadow probes run only when online attempts exceed the median-like historical threshold of the deployed policy, and execute on an isolated KB clone.'}
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

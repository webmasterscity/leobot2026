#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
from statistics import median
from leobot import Bot,Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v53_dream_replay.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def add_chain(bot,r,s,prefix):
    n=[f'{prefix}{i}' for i in range(5)]
    for pred,a,b in [(r,n[0],n[1]),(s,n[1],n[2]),(r,n[2],n[3]),(s,n[3],n[4])]:
        bot.kb.add(Atom(pred,(a,b)),'world')
    return n[0],n[4]

def domain(bot,idx,heldout=4):
    r,s=f'r{idx}',f's{idx}'
    pos=[add_chain(bot,r,s,f'd{idx}a_'),add_chain(bot,r,s,f'd{idx}b_')]
    held=[add_chain(bot,r,s,f'd{idx}h{j}_') for j in range(heldout)]
    neg=[]
    for j in range(2):
        a,b=f'd{idx}n{j}a',f'd{idx}n{j}b';bot.kb.add(Atom(f'other{idx}',(a,b)),'world');neg.append((a,b))
    surface=f'vinculo{idx}'
    for a,b in pos: out=bot.observe_concept_statement(f'{a} {surface} {b}')
    for a,b in neg: out=bot.observe_concept_statement(f'{a} no {surface} {b}')
    ok=sum(bot.query_concept(f'{a} {surface} {b}?').get('status')=='entailed' for a,b in held)
    return out,ok,len(held)

def run_treatment(n=50):
    bot=Bot();bot.concepts.max_relation_length=2
    rows=[]
    for i in range(n):
        t=time.perf_counter();out,ok,total=domain(bot,i);ms=(time.perf_counter()-t)*1000
        l=out.get('learning',{});rows.append({'domain':i,'attempts':l.get('invention_attempts'),
            'target_candidates':l.get('invention_total_target_candidates'),'ms':ms,
            'heldout':ok,'heldout_total':total,'policy':bot.concepts.invention_candidate_policy})
    return bot,rows

def run_control(n=50):
    bot=Bot();bot.concepts.max_relation_length=2
    rows=[]
    for i in range(n):
        bot.concepts.invention_candidate_policy='baseline'
        t=time.perf_counter();out,ok,total=domain(bot,1000+i);ms=(time.perf_counter()-t)*1000
        # prevent the learned policy from being deployed on the next domain
        bot.concepts.invention_candidate_policy='baseline'
        l=out.get('learning',{});rows.append({'domain':i,'attempts':l.get('invention_attempts'),
            'target_candidates':l.get('invention_total_target_candidates'),'ms':ms,
            'heldout':ok,'heldout_total':total})
    return bot,rows

def main():
    before=code_hash();tbot,t=run_treatment();c,tctrl=run_control();after=code_hash()
    result={'version':'V5.3-development','mechanism':'exact_history_replay_meta_exploration',
      'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
      'treatment':{'domains':len(t),'attempts_total':sum(x['attempts'] or 0 for x in t),
                   'target_candidates_total':sum(x['target_candidates'] or 0 for x in t),
                   'heldout_correct':sum(x['heldout'] for x in t),'heldout_total':sum(x['heldout_total'] for x in t),
                   'median_domain_ms':median(x['ms'] for x in t),
                   'final_policy':tbot.concepts.invention_candidate_policy,
                   'policy_updates':tbot.concepts.invention_candidate_policy_updates,
                   'first_five':t[:5]},
      'fixed_policy_control':{'domains':len(tctrl),'attempts_total':sum(x['attempts'] or 0 for x in tctrl),
                   'target_candidates_total':sum(x['target_candidates'] or 0 for x in tctrl),
                   'heldout_correct':sum(x['heldout'] for x in tctrl),'heldout_total':sum(x['heldout_total'] for x in tctrl),
                   'median_domain_ms':median(x['ms'] for x in tctrl),
                   'first_five':tctrl[:5]},
      'scope_note':'Replay is exact only over candidate branches actually observed in historical invention traces.'}
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

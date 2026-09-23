from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v68_meta_dsl.json'
STRATEGIES=['A','B']


def code_hash():
    h=hashlib.sha256()
    for base in (ROOT/'leobot',ROOT/'tests'):
        for p in sorted(base.rglob('*.py')):
            h.update(str(p.relative_to(ROOT)).encode()); h.update(b'\0')
            h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def observe_pair(bot: Bot, family: str, features, winner: str):
    for s in STRATEGIES:
        bot.meta_controller.observe(family,features,s,success=(s==winner),
                                    cost=(1 if s==winner else 9),failure_budget=2)


def train_order(bot: Bot, family='order'):
    # Every complete raw signature is unique.  The invariant is only f0<f1.
    for i in range(32):
        center=-500.0+i*41.0
        delta=-3.0 if i%2==0 else 4.0  # f0-f1; negative => A, positive => B
        f=(center+delta/2.0,center-delta/2.0,1000+i*13.0,2000+i*17.0)
        observe_pair(bot,family,f,'A' if delta<0 else 'B')


def train_delta(bot: Bot, family='delta'):
    # Signed difference threshold > 0.25 is required.  cmp alone is insufficient
    # because both +0.1 and +0.4 have the same ordering; abs-difference is also
    # insufficient because -0.4 belongs to B.
    for i in range(10):
        center=100.0+i*53.0
        for j,delta in enumerate((-0.4,0.1,0.4)):
            f=(center+delta/2.0,center-delta/2.0,5000+i*19+j,9000+i*23+j)
            observe_pair(bot,family,f,'A' if delta>0.25 else 'B')


def heldout_order(bot: Bot, family='order', count=400):
    correct=attempts=0; modes={}
    for i in range(count):
        delta=-7.0 if i%2==0 else 9.0
        center=1_000_000.0 + i*101.0
        f=(center+delta/2,center-delta/2,50_000+i*29,90_000+i*31)
        expected='A' if delta<0 else 'B'
        route=bot.meta_controller.rank(family,f,STRATEGIES)
        first=route['order'][0]
        correct+=int(first==expected); attempts+=1 if first==expected else 2
        modes[route['mode']]=modes.get(route['mode'],0)+1
    return {'correct_first_choice':correct,'total':count,'attempts':attempts,'modes':modes}


def heldout_delta(bot: Bot, family='delta', count=400):
    correct=attempts=0; modes={}
    deltas=(-5.0,0.02,0.7,0.2)
    for i in range(count):
        delta=deltas[i%len(deltas)]
        center=-2_000_000.0 + i*211.0
        f=(center+delta/2,center-delta/2,70_000+i*37,120_000+i*41)
        expected='A' if delta>0.25 else 'B'
        route=bot.meta_controller.rank(family,f,STRATEGIES)
        first=route['order'][0]
        correct+=int(first==expected); attempts+=1 if first==expected else 2
        modes[route['mode']]=modes.get(route['mode'],0)+1
    return {'correct_first_choice':correct,'total':count,'attempts':attempts,'modes':modes}


def main():
    before=code_hash(); start=time.perf_counter()
    treatment=Bot(); control=Bot()
    for b in (treatment,control):
        train_order(b); train_delta(b)
    invented=json.loads(json.dumps(treatment.meta_controller.invented_views))
    # Ablation keeps exact/RBF/AIKR evidence but removes only synthesized views.
    control.meta_controller.invented_views.clear()
    order_t=heldout_order(treatment); order_c=heldout_order(control)
    delta_t=heldout_delta(treatment); delta_c=heldout_delta(control)

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json'; treatment.save(p); loaded=Bot.load(p)
        persistence={
            'views_preserved': loaded.meta_controller.invented_views==treatment.meta_controller.invented_views,
            'order_after_reload': heldout_order(loaded,count=80),
            'delta_after_reload': heldout_delta(loaded,count=80),
        }

    # Contradict the order invariant with equally strong independent evidence.
    shifted=Bot(); train_order(shifted,'shift')
    before_shift=shifted.meta_controller.invented_views.get('shift')
    for i in range(32):
        center=10_000.0+i*47.0; delta=-3.0 if i%2==0 else 4.0
        f=(center+delta/2,center-delta/2,3000+i*5.0,4000+i*7.0)
        observe_pair(shifted,'shift',f,'B' if delta<0 else 'A')
    after_shift=shifted.meta_controller.invented_views.get('shift')

    total_t=order_t['attempts']+delta_t['attempts']; total_c=order_c['attempts']+delta_c['attempts']
    result={
        'version':'V6.8 meta-DSL derived observables',
        'code_hash_before':before,
        'invented_views':invented,
        'order_relation':{'treatment':order_t,'control_without_views':order_c},
        'learned_difference_threshold':{'treatment':delta_t,'control_without_views':delta_c},
        'combined_attempt_reduction_pct':100.0*(total_c-total_t)/total_c,
        'persistence':persistence,
        'rollback':{'view_before_contradiction':before_shift,'view_after_contradiction':after_shift},
        'elapsed_s':time.perf_counter()-start,
    }
    result['code_hash_after']=code_hash(); result['code_unchanged']=result['code_hash_before']==result['code_hash_after']
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

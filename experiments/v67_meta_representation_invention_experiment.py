from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v67_meta_representation_invention.json'
STRATEGIES=['role_cardinality','role_topology']


def code_hash():
    h=hashlib.sha256()
    for base in (ROOT/'leobot',ROOT/'tests'):
        for p in sorted(base.rglob('*.py')):
            h.update(str(p.relative_to(ROOT)).encode()); h.update(b'\0')
            h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def winner(a:int,b:int)->str:
    return 'role_cardinality' if a==b else 'role_topology'


def train(bot:Bot, *, reverse=False, start_rep=0, reps=4):
    idx=start_rep*4
    for rep in range(start_rep,start_rep+reps):
        for a,b in ((0,0),(0,1),(1,0),(1,1)):
            # The first two structural dimensions are predictive jointly.  The
            # remaining dimensions vary independently and make raw full-space
            # interpolation deliberately unreliable on distant held-out points.
            features=(float(a),float(b),(rep+1)/10.0,(idx+1)/100.0)
            w=winner(a,b)
            if reverse:
                w=STRATEGIES[1] if w==STRATEGIES[0] else STRATEGIES[0]
            for s in STRATEGIES:
                bot.meta_controller.observe('representation',features,s,
                    success=(s==w),cost=(1 if s==w else 10),failure_budget=2)
            idx+=1


def heldout(bot:Bot, *, count=400):
    correct=0; attempts=0; modes={}
    for i in range(count):
        a=(i//2)%2; b=i%2
        # Never seen as a complete signature.  Both irrelevant features are far
        # outside the training cloud but still in the normalized range.
        features=(float(a),float(b),0.91+(i%3)*0.02,0.87+(i%5)*0.02)
        expected=winner(a,b)
        route=bot.meta_controller.rank('representation',features,STRATEGIES)
        first=route['order'][0]
        correct += int(first==expected)
        attempts += 1 if first==expected else 2
        modes[route['mode']]=modes.get(route['mode'],0)+1
    return {'correct_first_choice':correct,'total':count,'attempts_to_reach_safe_fallback':attempts,
            'modes':modes}


def main():
    before=code_hash(); start=time.perf_counter()
    treatment=Bot(); control=Bot()
    train(treatment); train(control)
    invented=treatment.meta_controller.invented_views.get('representation')
    # Ablation: identical observations/RBF/budgets/history, but remove only the
    # newly synthesized representation.  No evidence is removed.
    control.meta_controller.invented_views.clear()
    tr=heldout(treatment); cr=heldout(control)

    # Persistence is part of the capability: the representation must survive a
    # normal bot checkpoint and still be shared by both learners.
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json'; treatment.save(p); loaded=Bot.load(p)
        persistence={
            'view_preserved':loaded.meta_controller.invented_views.get('representation')==invented,
            'procedure_shared':loaded.procedures.meta_controller is loaded.meta_controller,
            'symbolic_shared':loaded.symbolic.meta_controller is loaded.meta_controller,
            'heldout_after_reload':heldout(loaded,count=80),
        }

    # Rollback: a later independent regime with the inverse relation must make
    # the old view fail its own validation and be withdrawn rather than become a
    # dogma.  The safe RBF/default path remains.
    shifted=Bot(); train(shifted); before_shift=bool(shifted.meta_controller.invented_views.get('representation'))
    train(shifted,reverse=True,start_rep=4,reps=4)
    after_shift=shifted.meta_controller.invented_views.get('representation')
    shift_route=shifted.meta_controller.rank('representation',(0.0,1.0,.99,.99),STRATEGIES)

    result={
        'version':'V6.7 invented meta-representation',
        'code_hash_before':before,
        'invented_view':invented,
        'treatment':tr,
        'control_without_invented_view':cr,
        'first_choice_gain_pct':100.0*(tr['correct_first_choice']-cr['correct_first_choice'])/cr['total'],
        'attempt_reduction_pct':100.0*(cr['attempts_to_reach_safe_fallback']-tr['attempts_to_reach_safe_fallback'])/cr['attempts_to_reach_safe_fallback'],
        'persistence':persistence,
        'rollback':{'view_existed_before_shift':before_shift,'view_after_contradictory_regime':after_shift,
                    'route_mode_after_shift':shift_route['mode'],'safe_fallback_order':shift_route['order']},
        'elapsed_s':time.perf_counter()-start,
    }
    result['code_hash_after']=code_hash(); result['code_unchanged']=result['code_hash_before']==result['code_hash_after']
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

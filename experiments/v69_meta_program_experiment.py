from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v69_meta_program.json'
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


def train_parity(bot: Bot, family='parity', reverse=False, n=40):
    for i in range(n):
        left=i%2; right=(i//2)%2
        c1=10000.0+i*101.0; c2=1_000_000.0+i*137.0
        f0,f1=((c1+4,c1-4) if left else (c1-4,c1+4))
        f2,f3=((c2+7,c2-7) if right else (c2-7,c2+7))
        winner='A' if bool(left)^bool(right) else 'B'
        if reverse: winner='B' if winner=='A' else 'A'
        observe_pair(bot,family,(f0,f1,f2,f3),winner)


def heldout(bot: Bot, family='parity', count=400):
    correct=attempts=0; modes={}
    for i in range(count):
        left=i%2; right=(i//2)%2
        c1=-9_000_000.0+i*211.0; c2=7_000_000.0+i*307.0
        f0,f1=((c1+3,c1-3) if left else (c1-3,c1+3))
        f2,f3=((c2+5,c2-5) if right else (c2-5,c2+5))
        expected='A' if bool(left)^bool(right) else 'B'
        route=bot.meta_controller.rank(family,(f0,f1,f2,f3),STRATEGIES)
        first=route['order'][0]
        correct+=int(first==expected); attempts+=1 if first==expected else 2
        modes[route['mode']]=modes.get(route['mode'],0)+1
    return {'correct_first_choice':correct,'total':count,'attempts':attempts,'modes':modes}


def main():
    before=code_hash(); start=time.perf_counter()
    treatment=Bot(); train_parity(treatment)
    invented=json.loads(json.dumps(treatment.meta_controller.invented_views))

    control=Bot(); train_parity(control)
    # Preserve exact/RBF/AIKR/history, ablate only the newly synthesized program.
    if (control.meta_controller.invented_views.get('parity') or {}).get('kind')=='feature_program':
        control.meta_controller.invented_views.pop('parity',None)

    t=heldout(treatment); c=heldout(control)

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json'; treatment.save(p); loaded=Bot.load(p)
        persistence={'view_preserved':loaded.meta_controller.invented_views==treatment.meta_controller.invented_views,
                     'heldout_after_reload':heldout(loaded,count=80)}

    shifted=Bot(); train_parity(shifted,'shift',False,40)
    before_shift=json.loads(json.dumps(shifted.meta_controller.invented_views.get('shift')))
    train_parity(shifted,'shift',True,40)
    after_shift=shifted.meta_controller.invented_views.get('shift')

    result={
        'version':'V6.9 composed meta-program synthesis',
        'code_hash_before':before,
        'invented_views':invented,
        'parity_composition':{'treatment':t,'control_without_program':c},
        'attempt_reduction_pct':100.0*(c['attempts']-t['attempts'])/c['attempts'],
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

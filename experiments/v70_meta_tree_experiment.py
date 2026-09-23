from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v70_meta_tree.json'
STRATEGIES=['A','B']


def code_hash():
    h=hashlib.sha256()
    for base in (ROOT/'leobot',ROOT/'tests'):
        for p in sorted(base.rglob('*.py')):
            h.update(str(p.relative_to(ROOT)).encode());h.update(b'\0')
            h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def observe(bot: Bot,family,features,winner):
    for s in STRATEGIES:
        bot.meta_controller.observe(family,features,s,success=(s==winner),
                                    cost=(1 if s==winner else 9),failure_budget=2)


def train(bot: Bot,family='parity3',reverse=False,n=64):
    for i in range(n):
        bits=[(i>>k)&1 for k in range(3)]
        centers=[10_000.0+i*17.0,1_000_000.0+i*31.0,100_000_000.0+i*43.0]
        features=[]
        for bit,center,delta in zip(bits,centers,(3.0,5.0,7.0)):
            features.extend((center+delta,center-delta) if bit else (center-delta,center+delta))
        winner='A' if (bits[0]^bits[1]^bits[2]) else 'B'
        if reverse: winner='B' if winner=='A' else 'A'
        observe(bot,family,features,winner)


def heldout(bot: Bot,family='parity3',count=800):
    correct=attempts=0;modes={}
    for i in range(count):
        bits=[(i>>k)&1 for k in range(3)]
        centers=[-9_000_000.0+i*211.0,7_000_000.0+i*307.0,90_000_000.0+i*401.0]
        features=[]
        for bit,center,delta in zip(bits,centers,(2.0,4.0,6.0)):
            features.extend((center+delta,center-delta) if bit else (center-delta,center+delta))
        expected='A' if (bits[0]^bits[1]^bits[2]) else 'B'
        route=bot.meta_controller.rank(family,features,STRATEGIES)
        first=route['order'][0]
        correct+=int(first==expected);attempts+=1 if first==expected else 2
        modes[route['mode']]=modes.get(route['mode'],0)+1
    return {'correct_first_choice':correct,'total':count,'attempts':attempts,'modes':modes}


def main():
    before=code_hash(); started=time.perf_counter()
    treatment=Bot(); t0=time.perf_counter();train(treatment);acquisition_s=time.perf_counter()-t0
    view=json.loads(json.dumps(treatment.meta_controller.invented_views.get('parity3')))

    control=Bot();train(control)
    control.meta_controller.invented_views.pop('parity3',None)
    tasks=control.meta_controller._meta_tasks('parity3')
    depth2=control.meta_controller._invent_meta_program_from_tasks('parity3',tasks,max_program_size=2,force=True)

    t=heldout(treatment);c=heldout(control)

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json';treatment.save(p);loaded=Bot.load(p)
        persistence={
            'program_size':loaded.meta_controller.invented_views['parity3']['program_size'],
            'heldout_after_reload':heldout(loaded,count=160),
            'checkpoints_preserved':bool(loaded.meta_controller.program_search_checkpoints),
        }

    shifted=Bot();train(shifted,'shift3',False);before_shift=json.loads(json.dumps(shifted.meta_controller.invented_views.get('shift3')))
    train(shifted,'shift3',True);after_shift=shifted.meta_controller.invented_views.get('shift3')

    result={
        'version':'V7.0 bounded variable-depth meta-program synthesis',
        'code_hash_before':before,
        'learned_view':view,
        'depth2_control_status':depth2,
        'heldout':{'treatment':t,'depth2_control':c},
        'attempt_reduction_pct':100.0*(c['attempts']-t['attempts'])/c['attempts'],
        'acquisition_s':acquisition_s,
        'persistence':persistence,
        'rollback':{'view_before_contradiction':before_shift,'view_after_contradiction':after_shift},
        'elapsed_s':time.perf_counter()-started,
    }
    result['code_hash_after']=code_hash();result['code_unchanged']=result['code_hash_before']==result['code_hash_after']
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

"""Preregistered A-1 evaluation. Run only after tagging freeze-A-1.

The environment owns all outcomes. The engine sees observations, never this
generator or the held-out labels. See prereg/A-1-subregla-meta.md.
"""
from __future__ import annotations

import json
import random
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'a1_meta_abstraction.json'


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def vector(index,comparisons,scale=1,*,reserve_rng=None,proxy=None):
    bits=[(index>>k)&1 for k in range(comparisons)]
    values=[]
    for k,bit in enumerate(bits):
        if reserve_rng is None:
            center=scale*(10**(k+3)+index*(17+11*k))
            delta=scale*(2+k)
        else:
            center=reserve_rng.randint(-10_000_000,10_000_000)
            delta=reserve_rng.randint(2,9)
        values.extend((center+delta,center-delta) if bit
                      else (center-delta,center+delta))
    if proxy is not None:
        center=50_000_000+index*113
        values.extend((center+1,center-1) if proxy else (center-1,center+1))
    return tuple(values),bits


def winner(bits,labels,*,reverse=False):
    selected=labels[0] if sum(bits)%2 else labels[1]
    return labels[1] if reverse and selected==labels[0] else (
        labels[0] if reverse else selected)


def observe(controller,family,features,target,labels):
    for strategy in labels:
        controller.observe(family,features,strategy,success=strategy==target,
                           cost=1 if strategy==target else 9,failure_budget=2)


def teach_sources(controller,order,*,names=('source_one','source_two'),
                  labels=(('A','B'),('X','Y')),reverse_first=False):
    for k,(family,strategies) in enumerate(zip(names,labels)):
        indices=list(range(32));random.Random(order+101*k).shuffle(indices)
        for index in indices:
            features,bits=vector(index,2,scale=1 if k==0 else 7)
            target=winner(bits,strategies,reverse=reverse_first and k==0)
            observe(controller,family,features,target,strategies)


def teach_target(controller,order,*,family='target',labels=('left','right'),
                 confound=False):
    indices=list(range(64));random.Random(order+211).shuffle(indices)
    for index in indices:
        features,bits=vector(index,4,proxy=None)
        target=winner(bits,labels)
        if confound:
            features,_=vector(index,4,proxy=int(target==labels[0]))
        observe(controller,family,features,target,labels)


def reserve(seed,*,confound=False):
    rng=random.Random(seed)
    configs=list(range(16))*10
    rng.shuffle(configs)
    rows=[]
    for serial,index in enumerate(configs):
        features,bits=vector(index,4,reserve_rng=rng)
        if confound:
            features=tuple(features)+tuple(vector(serial,0,proxy=int(sum(bits)%2==0))[0])
        rows.append((features,bits))
    return rows


def evaluate(controller,family,rows,labels,*,incompatible=False):
    start=time.process_time();correct=confident_wrong=0; modes={}
    for features,bits in rows:
        if incompatible:
            target=labels[0] if sum(bits)>=3 else labels[1]
        else:
            target=winner(bits,labels)
        route=controller.rank(family,features,labels)
        prediction=route['order'][0]
        correct+=int(prediction==target)
        confident_wrong+=int(prediction!=target and route.get('mode')!='default')
        mode=route.get('mode');modes[mode]=modes.get(mode,0)+1
    return {'correct':correct,'total':len(rows),'confident_wrong':confident_wrong,
            'modes':modes,'inference_cpu_s':round(time.process_time()-start,5)}


def timed(action):
    wall=time.perf_counter();cpu=time.process_time()
    result=action()
    return result,{'wall_s':round(time.perf_counter()-wall,5),
                   'cpu_s':round(time.process_time()-cpu,5)}


def one_order(order,seed):
    labels=('left','right')
    controller=MetaController()
    _,source_cost=timed(lambda:teach_sources(controller,order))
    primitive_count=len(controller.meta_primitives)
    _,target_cost=timed(lambda:teach_target(controller,order))
    view=controller.invented_views.get('target') or {}
    heldout=reserve(seed)
    treatment=evaluate(controller,'target',heldout,labels)

    ablation=MetaController();ablation.enable_meta_primitives=False
    _,ablation_source_cost=timed(lambda:teach_sources(ablation,order))
    _,ablation_target_cost=timed(lambda:teach_target(ablation,order))
    ablation_result=evaluate(ablation,'target',heldout,labels)

    fresh=evaluate(MetaController(),'target',heldout,labels)
    memory=MetaController.from_dict(controller.as_dict())
    memory.invented_views.clear();memory.routers.clear();memory.meta_primitives.clear()
    memory_result=evaluate(memory,'target',heldout,labels)
    incompatible=evaluate(controller,'unseen_structure',heldout,labels,incompatible=True)

    renamed=MetaController()
    _,renamed_cost=timed(lambda:(teach_sources(renamed,order,
                                             names=('alpha_source','omega_source'),
                                             labels=(('p','q'),('r','s'))),
                                 teach_target(renamed,order,family='renamed_target',
                                              labels=('north','south'))))
    renamed_result=evaluate(renamed,'renamed_target',heldout,('north','south'))

    confounded=MetaController()
    _,confound_cost=timed(lambda:(teach_sources(confounded,order),
                                  teach_target(confounded,order,family='confound_target',
                                               confound=True)))
    confound_view=(confounded.invented_views.get('confound_target') or {}).get('kind')
    confound_result=evaluate(confounded,'confound_target',reserve(seed+73,confound=True),labels)

    restored=MetaController.from_dict(controller.as_dict())
    _,counter_cost=timed(lambda:teach_sources(restored,order,
                                             names=('source_one',),
                                             labels=(('A','B'),),
                                             reverse_first=True))
    withdrawn='target' not in restored.invented_views
    with tempfile.TemporaryDirectory() as directory:
        bot=Bot();bot.meta_controller=controller
        path=Path(directory)/'bot.json';bot.save(path)
        del bot
        reloaded=Bot.load(path)
        restart=evaluate(reloaded.meta_controller,'target',heldout,labels)
        persisted_bytes=path.stat().st_size

    return {
        'order_seed':order,'heldout_seed':seed,'source_primitive_count':primitive_count,
        'target_view_kind':view.get('kind'),'target_macro_candidates':view.get('candidates_evaluated'),
        'treatment':treatment,'ablation_same_information':ablation_result,
        'fresh':fresh,'memory_only':memory_result,'incompatible':incompatible,
        'renamed':renamed_result,'confounded':confound_result,
        'confounded_view_kind':confound_view,'counterevidence_withdrew_dependents':withdrawn,
        'restart':restart,'persisted_bytes':persisted_bytes,
        'source_acquisition':source_cost,'target_acquisition':target_cost,
        'ablation_source_acquisition':ablation_source_cost,
        'ablation_target_acquisition':ablation_target_cost,
        'renamed_acquisition':renamed_cost,'confounded_acquisition':confound_cost,
        'counterevidence_acquisition':counter_cost,
    }


def main():
    development='--development' in sys.argv
    if development:
        rows=[one_order(17,991)]
        print(json.dumps({'development_only':True,'orders':rows},indent=2))
        return
    frozen=git('rev-parse','freeze-A-1:leobot')
    if git('diff','--name-only','freeze-A-1','--','leobot'):
        raise RuntimeError('El motor de trabajo difiere del tag congelado.')
    start=time.perf_counter()
    rows=[one_order(order,int(frozen[:8],16)+offset)
          for offset,order in enumerate((17,53,97))]
    if git('diff','--name-only','freeze-A-1','--','leobot'):
        raise RuntimeError('El motor cambió durante el ensayo.')
    result={'preregistration':'prereg/A-1-subregla-meta.md','frozen_engine_tree':frozen,
            'engine_unchanged':True,'orders':rows,
            'total_wall_s':round(time.perf_counter()-start,4),
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()

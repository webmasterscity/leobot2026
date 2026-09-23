"""Supplementary frozen-engine controls preregistered in A-1b."""
from __future__ import annotations

import json
import random
import resource
import subprocess
import tempfile
import time
from math import comb
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController
from experiments.a1_meta_abstraction import (
    ROOT, evaluate, git, observe, reserve, teach_sources, teach_target,
    timed, vector, winner,
)


OUT=ROOT/'results_v3'/'a1b_controls.json'


def save_reload(controller):
    with tempfile.TemporaryDirectory() as directory:
        bot=Bot();bot.meta_controller=controller
        state=Path(directory)/'bot.json'
        bot.save(state)
        size=state.stat().st_size
        del bot
        loaded=Bot.load(state)
        return loaded.meta_controller,size


def teach_incompatible(controller,order,family='incompatible'):
    indices=list(range(64));random.Random(order+211).shuffle(indices)
    for index in indices:
        features,bits=vector(index,4)
        target='left' if sum(bits)>=3 else 'right'
        observe(controller,family,features,target,('left','right'))


def timed_methods(controller):
    """Record nested search/validation/consolidation costs without changing logic."""
    costs={'search_cpu_s':0.0,'macro_search_cpu_s':0.0,
           'temporal_validation_cpu_s':0.0,'consolidation_cpu_s':0.0,
           'flat_candidates':0}
    for name,key in (
        ('invent_view','search_cpu_s'),
        ('_invent_macro_view_from_tasks','macro_search_cpu_s'),
        ('_program_temporal_transfer','temporal_validation_cpu_s'),
        ('_reconcile_meta_primitives','consolidation_cpu_s'),
    ):
        original=getattr(controller,name)
        def wrapped(*args,_original=original,_key=key,**kwargs):
            start=time.process_time()
            result=_original(*args,**kwargs)
            costs[_key]+=time.process_time()-start
            return result
        setattr(controller,name,wrapped)
    original_program=controller._invent_meta_program_from_tasks
    def counted_program(family,tasks,**kwargs):
        before=dict(controller.program_search_checkpoints.get(family,{}))
        result=original_program(family,tasks,**kwargs)
        after=controller.program_search_checkpoints.get(family,{})
        if any(before.get(stage)!=after.get(stage) for stage in ('pair','deep')):
            n=len(controller._program_predicate_candidates(tasks,limit=128))
            if before.get('pair')!=after.get('pair') and n>=2:
                costs['flat_candidates']+=comb(n,2)
            if before.get('deep')!=after.get('deep') and n>=3:
                costs['flat_candidates']+=comb(min(n,32),3)
        return result
    controller._invent_meta_program_from_tasks=counted_program
    return costs


def one_order(order,seed):
    labels=('left','right')
    heldout=reserve(seed)
    controller=MetaController()
    nested=timed_methods(controller)
    _,source_cost=timed(lambda:teach_sources(controller,order))
    _,target_cost=timed(lambda:teach_target(controller,order))
    before=evaluate(controller,'target',heldout,labels)
    (control,size),control_save_cost=timed(lambda:save_reload(controller))
    control_after_restart=evaluate(control,'target',heldout,labels)

    challenged=MetaController.from_dict(controller.as_dict())
    _,counter_cost=timed(lambda:teach_sources(
        challenged,order,names=('source_one',),labels=(('A','B'),),
        reverse_first=True))
    view_after_counter=(challenged.invented_views.get('target') or {}).get('kind')
    (challenged_reloaded,challenged_size),challenged_save_cost=timed(
        lambda:save_reload(challenged))
    view_after_counter_restart=(challenged_reloaded.invented_views.get('target')
                                or {}).get('kind')
    after_counter=evaluate(challenged_reloaded,'target',heldout,labels)

    incompatible=MetaController()
    _,incompatible_source_cost=timed(lambda:teach_sources(incompatible,order))
    _,incompatible_target_cost=timed(lambda:teach_incompatible(incompatible,order))
    incompatible_view=(incompatible.invented_views.get('incompatible') or {}).get('kind')
    incompatible_result=evaluate(incompatible,'incompatible',heldout,labels,
                                 incompatible=True)

    ablation=MetaController();ablation.enable_meta_primitives=False
    ablation_nested=timed_methods(ablation)
    _,ablation_source_cost=timed(lambda:teach_sources(ablation,order))
    _,ablation_target_cost=timed(lambda:teach_target(ablation,order))

    confounded=MetaController()
    _,confounded_source_cost=timed(lambda:teach_sources(confounded,order))
    _,confounded_target_cost=timed(lambda:teach_target(
        confounded,order,family='confound_target',confound=True))
    confound_reserve=reserve(seed+73,confound=True)
    before_intervention=evaluate(confounded,'confound_target',confound_reserve,labels)
    aligned,bits=vector(7,4,proxy=1)
    inverted,_=vector(7,4,proxy=0)
    candidates=[{'features':aligned,'cost':1},
                {'features':inverted,'cost':1}]

    def intervention():
        proposal=confounded.propose_meta_probe('confound_target',candidates)
        # The environment, not the controller, evaluates the inverted case.
        observed=winner(bits,labels)
        observe(confounded,'confound_target',inverted,observed,labels)
        return proposal

    proposal,intervention_cost=timed(intervention)
    after_intervention=evaluate(confounded,'confound_target',confound_reserve,labels)

    return {
        'order_seed':order,'heldout_seed':seed,
        'before_counterevidence':before,
        'control_after_restart':control_after_restart,
        'view_after_counterevidence':view_after_counter,
        'view_after_counterevidence_restart':view_after_counter_restart,
        'after_counterevidence_restart':after_counter,
        'incompatible_view':incompatible_view,'incompatible':incompatible_result,
        'confounded_before_intervention':before_intervention,
        'confounded_after_intervention':after_intervention,
        'intervention_proposal_status':proposal.get('status'),
        'intervention_proposal_reason':proposal.get('reason'),
        'intervention_chosen_index':proposal.get('chosen_index'),
        'initial_examples':{'source':64,'target':64},
        'counterevidence_examples':32,'intervention_examples':1,
        'macro_candidates':(controller.invented_views.get('target') or {}).get('candidates_evaluated'),
        'flat_candidates_treatment':nested['flat_candidates'],
        'flat_candidates_ablation':ablation_nested['flat_candidates'],
        'source_acquisition':source_cost,'target_acquisition':target_cost,
        'nested_costs_nonadditive':{key:round(value,5) for key,value in nested.items()},
        'ablation_source_acquisition':ablation_source_cost,
        'ablation_target_acquisition':ablation_target_cost,
        'control_save_reload':control_save_cost,
        'counterevidence_acquisition':counter_cost,
        'challenged_save_reload':challenged_save_cost,
        'incompatible_source_acquisition':incompatible_source_cost,
        'incompatible_target_acquisition':incompatible_target_cost,
        'confounded_source_acquisition':confounded_source_cost,
        'confounded_target_acquisition':confounded_target_cost,
        'intervention_cost':intervention_cost,
        'saved_bytes':size,'challenged_saved_bytes':challenged_size,
    }


def main():
    frozen=git('rev-parse','freeze-A-1:leobot')
    if frozen!='644c55528a5fd97a8822f719f70e11cfae242783':
        raise RuntimeError('El tag de congelación no coincide con el preregistro.')
    if git('diff','--name-only','freeze-A-1','--','leobot'):
        raise RuntimeError('El motor difiere del tag congelado.')
    seed_base=int(frozen[:8],16)^0xA1B0
    start=time.perf_counter()
    rows=[one_order(order,seed_base+offset)
          for offset,order in enumerate((17,53,97))]
    if git('diff','--name-only','freeze-A-1','--','leobot'):
        raise RuntimeError('El motor cambió durante el ensayo.')
    controls={
        'counterevidence_restart':all(row['view_after_counterevidence_restart'] is None
                                      and row['after_counterevidence_restart']['confident_wrong']==0
                                      for row in rows),
        'untouched_restart':all(row['control_after_restart']['correct']>=144 for row in rows),
        'incompatible':all(row['incompatible_view']!='macro_program'
                           and row['incompatible']['confident_wrong']==0 for row in rows),
        'confound':all(row['confounded_after_intervention']['correct']>=144
                       and row['confounded_after_intervention']['confident_wrong']==0
                       for row in rows),
    }
    result={'preregistration':'prereg/A-1b-controles-pendientes.md',
            'frozen_engine_tree':frozen,'engine_unchanged':True,
            'controls':controls,'orders':rows,
            'total_wall_s':round(time.perf_counter()-start,4),
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()

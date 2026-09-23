"""C-1 frozen-engine parity and structural-reserve controls."""
from __future__ import annotations

import argparse
import json
import random
import resource
import subprocess
import time
from pathlib import Path

from leobot.metacontrol import MetaController
from experiments.b1_aggregate_operator import ROOT,git,teach
from experiments.b2_rival_views import one_order as b2_controls
from experiments.c1_parity import one_order as parity_order


def projection_trial(order,seed):
    labels=('alpha','beta')
    rows=[((float(index%2),float(1_000+13*index)),bool(index%2))
          for index in range(64)]
    random.Random(order).shuffle(rows)
    bot=MetaController()
    started=time.process_time();teach(bot,'projection',rows,labels)
    acquisition=time.process_time()-started
    rng=random.Random(seed)
    held=[]
    for index in range(128):
        held.append(((float(index%2),float(rng.randint(100_000,10_000_000))),
                     bool(index%2)))
    started=time.process_time()
    correct=sum(bot.rank('projection',features,labels)['order'][0]==
                (labels[0] if positive else labels[1])
                for features,positive in held)
    inference=time.process_time()-started

    ablated=MetaController()
    ablated._best_projection_view=lambda tasks,max_dims:None
    started=time.process_time();teach(ablated,'projection',rows,labels)
    ablation_cost=time.process_time()-started
    ablated_kind=(ablated.invented_views.get('projection') or {}).get('kind')

    incompatible=MetaController()
    different=[]
    for index in range(64):
        noise=(-1 if index%4<2 else 1)*(1_000+index)
        different.append(((float(index%2),float(noise)),noise>0))
    teach(incompatible,'incompatible_projection',different,labels)
    incompatible_kind=(incompatible.invented_views.get('incompatible_projection')
                       or {}).get('kind')
    return {'correct':correct,'total':len(held),'view_kind':(
                bot.invented_views.get('projection') or {}).get('kind'),
            'ablation_kind':ablated_kind,'incompatible_kind':incompatible_kind,
            'cpu_s':{'acquisition':round(acquisition,5),
                     'inference':round(inference,5),
                     'ablation':round(ablation_cost,5)},
            'examples':64}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--order',type=int,required=True)
    order=parser.parse_args().order
    if order not in (17,53,97):
        raise ValueError('Orden no preregistrado.')
    frozen=git('rev-parse','freeze-C-1:leobot')
    if git('diff','--name-only','freeze-C-1','--','leobot'):
        raise RuntimeError('El motor difiere del tag congelado.')
    seed=int(frozen[:8],16)+(17,53,97).index(order)
    start=time.perf_counter()
    projection=projection_trial(order,seed)
    b2=b2_controls(order,seed)
    reference=json.loads((ROOT/'results_v3'/'c1_reference.json').read_text())
    expected=next(row for row in reference['orders'] if row['order']==order)
    parity=parity_order(order)
    parity_keys=('projection_view','projection_routes','source_view',
                 'source_routes','target_view','target_routes','operators','candidates')
    equal=all(parity[key]==expected[key] for key in parity_keys)
    projection_budget=projection['cpu_s']['acquisition']<=1.5*max(
        0.01,expected['cpu_s']['projection'])
    previous=json.loads((ROOT/'results_v3'/f'b2_rivals_order{order}.json').read_text())
    source_budget=b2['costs']['source']['cpu_s']<=1.5*previous['costs']['source']['cpu_s']
    target_budget=b2['costs']['target']['cpu_s']<=1.5*previous['costs']['target']['cpu_s']
    controls={'development_parity':equal,'projection_heldout':projection['correct']>=116,
              'projection_ablation':projection['ablation_kind']!='feature_projection',
              'projection_incompatible':projection['incompatible_kind']!='feature_projection',
              'acquisition_cost':projection_budget and source_budget and target_budget,
              **{f'b2_{key}':value for key,value in b2['controls'].items()}}
    if git('rev-parse','freeze-C-1:leobot')!=frozen or git(
            'diff','--name-only','freeze-C-1','--','leobot'):
        raise RuntimeError('El motor cambió durante el ensayo.')
    result={'preregistration':'prereg/C-1-learners-declarativos.md',
            'frozen_engine_tree':frozen,'engine_unchanged':True,
            'order_seed':order,'reserve_seed':seed,
            'controls':controls,'projection':projection,'b2_controls':b2,
            'cost_ratios':{'projection':round(projection['cpu_s']['acquisition']/
                                               expected['cpu_s']['projection'],4),
                           'source':round(b2['costs']['source']['cpu_s']/
                                          previous['costs']['source']['cpu_s'],4),
                           'target':round(b2['costs']['target']['cpu_s']/
                                          previous['costs']['target']['cpu_s'],4)},
            'wall_s':round(time.perf_counter()-start,5),
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    output=ROOT/'results_v3'/f'c1_declarative_order{order}.json'
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'order':order,'controls':controls,
                      'cost_ratios':result['cost_ratios'],
                      'wall_s':result['wall_s']},ensure_ascii=False))


if __name__=='__main__':
    main()

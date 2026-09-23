"""C-1 reference captured before replacing two Python meta-learners."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

from leobot.metacontrol import MetaController
from experiments.b1_aggregate_operator import source_rows,target_rows,reserves,teach


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'c1_reference.json'


def routes(controller,family,rows,labels):
    return [controller.rank(family,features,labels)['order'][0]
            for features,_ in rows]


def one_order(order):
    projection=MetaController()
    rows=[((float(index%2),float(1_000+13*index)),bool(index%2))
          for index in range(64)]
    random.Random(order).shuffle(rows)
    start=time.process_time()
    teach(projection,'projection',rows,('p','q'))
    projection_cpu=time.process_time()-start
    held_projection=[((float(index%2),float(100_000+17*index)),bool(index%2))
                     for index in range(64)]

    main=MetaController()
    source=source_rows(order)
    target,remaining=target_rows(order)
    held_source,held_target=reserves(991,remaining.copy())
    start=time.process_time()
    teach(main,'source',source,('A','B'))
    source_cpu=time.process_time()-start
    start=time.process_time()
    teach(main,'target',target,('north','south'))
    target_cpu=time.process_time()-start
    return {
        'order':order,
        'projection_view':projection.invented_views.get('projection'),
        'projection_routes':routes(projection,'projection',held_projection,('p','q')),
        'source_view':main.invented_views.get('source'),
        'source_routes':routes(main,'source',held_source,('A','B')),
        'target_view':main.invented_views.get('target'),
        'target_routes':routes(main,'target',held_target,('north','south')),
        'operators':main.meta_operators,
        'candidates':main.aggregate_candidates_evaluated,
        'cpu_s':{'projection':round(projection_cpu,5),
                 'source':round(source_cpu,5),'target':round(target_cpu,5)},
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--record',action='store_true')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.record==args.check:
        parser.error('Indique solo --record o --check.')
    rows=[one_order(order) for order in (17,53,97)]
    if args.record:
        if OUT.exists():
            raise RuntimeError('La referencia C-1 ya existe; no se sobrescribe.')
        OUT.write_text(json.dumps({'engine_tag':'estable-B-2',
                                   'orders':rows},indent=2,ensure_ascii=False)+'\n',encoding='utf8')
        print('Referencia C-1 registrada para tres órdenes.')
    else:
        reference=json.loads(OUT.read_text(encoding='utf8'))
        for actual,expected in zip(rows,reference['orders']):
            for key in ('projection_view','projection_routes','source_view',
                        'source_routes','target_view','target_routes',
                        'operators','candidates'):
                if actual[key]!=expected[key]:
                    raise AssertionError((actual['order'],key,actual[key],expected[key]))
            for name,baseline in expected['cpu_s'].items():
                if actual['cpu_s'][name]>1.5*max(0.01,baseline):
                    raise AssertionError((actual['order'],'cpu',name,
                                          actual['cpu_s'][name],baseline))
        print('Paridad exacta de vistas, rutas, operadores y candidatos en tres órdenes.')


if __name__=='__main__':
    main()

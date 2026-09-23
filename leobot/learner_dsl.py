"""Finite declarative substrate for meta-view learners.

Learner programs are data, not Python callables. Candidate generation,
validation and promotion share one interpreter; only a small whitelist of
structural extractors can run here. Search never executes user code.
"""
from __future__ import annotations

from itertools import combinations
from math import isfinite
from time import process_time

from . import meta_operators


PROJECTION_LEARNER={
    'input_representation':'numeric_meta_tasks',
    'hypothesis_generator':'projection_subsets',
    'operators':['index'],
    'constraints':{'min_examples':8,'max_width':16,'max_depth':3},
    'search':{'order':'best_score'},
    'verifier':{'kind':'leave_one_out','temporal':'none'},
    'cost':{'kind':'weighted_fit','accuracy_weight':1.0,
            'gain_weight':0.5,'dimension_penalty':0.015},
    'promotion':{'min_covered_count':6,'min_covered_fraction':0.5,
                 'min_accuracy':0.85,'min_coverage':0.60,'min_gain':0.10,
                 'min_bucket_support':2,'min_bucket_confidence':0.75,
                 'required_buckets':0,'different_bucket_winners':False},
    'rollback':'withdraw_on_invalidated',
    'budget':{'max_candidates':1024,'max_tasks':384,'max_cpu_s':10.0},
}

AGGREGATE_LEARNER={
    'input_representation':'numeric_meta_tasks',
    'hypothesis_generator':'fold_cutpoints',
    'operators':['index','sub','gt','lt','sum','min','max'],
    'constraints':{'min_examples':24,'max_width':16,'max_depth':4},
    'search':{'order':'first_valid'},
    'verifier':{'kind':'leave_one_out','temporal':'halves',
                'min_temporal_coverage':0.8,'min_temporal_accuracy':0.95},
    'cost':{'kind':'grammar_order'},
    'promotion':{'min_covered_count':0,'min_covered_fraction':0.0,
                 'min_accuracy':0.90,'min_coverage':0.70,'min_gain':0.20,
                 'min_bucket_support':2,'min_bucket_confidence':0.80,
                 'required_buckets':2,'different_bucket_winners':True},
    'rollback':'withdraw_on_invalidated',
    'budget':{'max_candidates':32,'max_tasks':384,'max_cpu_s':10.0},
}


_OPERATORS=frozenset(('index','sub','gt','lt','sum','min','max'))


def validate(program: dict) -> None:
    """Reject unbounded, unknown or executable learner descriptions."""
    if not isinstance(program,dict):
        raise ValueError('El learner debe ser un registro.')
    required=('input_representation','hypothesis_generator','operators',
              'constraints','search','verifier','cost','promotion','rollback','budget')
    if set(program)!=set(required):
        raise ValueError('Campos de learner desconocidos o ausentes.')
    if program['input_representation']!='numeric_meta_tasks':
        raise ValueError('Representación de entrada no permitida.')
    generator=program['hypothesis_generator']
    if generator not in ('projection_subsets','fold_cutpoints'):
        raise ValueError('Generador no permitido.')
    operators=program['operators']
    if (not isinstance(operators,list) or not operators or
            any(not isinstance(name,str) for name in operators) or
            len(operators)!=len(set(operators)) or
            not set(operators)<=_OPERATORS):
        raise ValueError('Operadores no permitidos.')
    mandatory=({'index'} if generator=='projection_subsets' else
               {'index','sub','gt','lt','sum','min','max'})
    if not mandatory<=set(operators):
        raise ValueError('Faltan operadores para el generador.')
    if program['rollback']!='withdraw_on_invalidated':
        raise ValueError('Rollback no permitido.')
    constraints=program['constraints'];budget=program['budget']
    if not isinstance(constraints,dict) or not isinstance(budget,dict):
        raise ValueError('Restricciones o presupuesto inválidos.')
    if set(constraints)!=set(('min_examples','max_width','max_depth')):
        raise ValueError('Restricciones desconocidas.')
    if set(budget)!=set(('max_candidates','max_tasks','max_cpu_s')):
        raise ValueError('Presupuesto desconocido.')
    for field,upper in (('min_examples',384),('max_width',16),('max_depth',4)):
        value=constraints[field]
        if type(value) is not int or not 1<=value<=upper:
            raise ValueError('Límite estructural inválido.')
    for field,upper in (('max_candidates',1024),('max_tasks',384)):
        value=budget[field]
        if type(value) is not int or not 1<=value<=upper:
            raise ValueError('Presupuesto de búsqueda inválido.')
    seconds=budget['max_cpu_s']
    if type(seconds) not in (int,float) or not isfinite(seconds) or not 0<seconds<=30:
        raise ValueError('Presupuesto de CPU inválido.')
    search=program['search'];verifier=program['verifier'];cost=program['cost']
    promotion=program['promotion']
    if not all(isinstance(x,dict) for x in (search,verifier,cost,promotion)):
        raise ValueError('Ciclo de learner inválido.')
    if set(search)!=set(('order',)) or search['order'] not in ('best_score','first_valid'):
        raise ValueError('Búsqueda no permitida.')
    if verifier.get('kind')!='leave_one_out' or verifier.get('temporal') not in ('none','halves'):
        raise ValueError('Verificador no permitido.')
    if verifier['temporal']=='none':
        if set(verifier)!=set(('kind','temporal')):
            raise ValueError('Verificador desconocido.')
    else:
        if set(verifier)!=set(('kind','temporal','min_temporal_coverage',
                              'min_temporal_accuracy')):
            raise ValueError('Verificador desconocido.')
        for field in ('min_temporal_coverage','min_temporal_accuracy'):
            value=verifier[field]
            if type(value) not in (int,float) or not 0<=value<=1:
                raise ValueError('Umbral temporal inválido.')
    if cost.get('kind')=='grammar_order':
        if set(cost)!=set(('kind',)):
            raise ValueError('Costo desconocido.')
    elif cost.get('kind')=='weighted_fit':
        if set(cost)!=set(('kind','accuracy_weight','gain_weight',
                          'dimension_penalty')):
            raise ValueError('Costo desconocido.')
        if any(type(cost[field]) not in (int,float) or not isfinite(cost[field])
               or not 0<=cost[field]<=10 for field in
               ('accuracy_weight','gain_weight','dimension_penalty')):
            raise ValueError('Peso de costo inválido.')
    else:
        raise ValueError('Costo no permitido.')
    expected=('min_covered_count','min_covered_fraction','min_accuracy',
              'min_coverage','min_gain','min_bucket_support',
              'min_bucket_confidence','required_buckets','different_bucket_winners')
    if set(promotion)!=set(expected):
        raise ValueError('Promoción desconocida.')
    for field in ('min_covered_fraction','min_accuracy','min_coverage',
                  'min_gain','min_bucket_confidence'):
        value=promotion[field]
        if type(value) not in (int,float) or not isfinite(value) or not 0<=value<=1:
            raise ValueError('Umbral de promoción inválido.')
    for field,upper in (('min_covered_count',384),('min_bucket_support',384),
                        ('required_buckets',16)):
        value=promotion[field]
        if type(value) is not int or not 0<=value<=upper:
            raise ValueError('Apoyo de promoción inválido.')
    if type(promotion['different_bucket_winners']) is not bool:
        raise ValueError('Comparación de cubos inválida.')


def _winner(counts: dict) -> str | None:
    return min(counts,key=lambda label:(-counts[label],str(label))) if counts else None


def _projection_key(features, dims) -> str:
    return ','.join(f'{float(features[i]):.6g}' for i in dims)


def _judge(keys: list[str], labels: list[str], program: dict) -> dict | None:
    """Shared leave-one-out, temporal and support verification."""
    n=len(labels);p=program['promotion'];v=program['verifier']
    counts={}
    global_counts={}
    for key,label in zip(keys,labels):
        row=counts.setdefault(key,{})
        row[label]=row.get(label,0)+1
        global_counts[label]=global_counts.get(label,0)+1
    majority=_winner(global_counts)
    covered=correct=baseline_correct=0
    for key,label in zip(keys,labels):
        available={name:value-int(name==label) for name,value in counts[key].items()}
        available={name:value for name,value in available.items() if value>0}
        if not available:
            continue
        prediction=_winner(available)
        covered+=1;correct+=int(prediction==label)
        baseline_correct+=int(majority==label)
    if covered<max(p['min_covered_count'],int(p['min_covered_fraction']*n)):
        return None
    coverage=covered/n;accuracy=correct/max(1,covered)
    gain=accuracy-baseline_correct/max(1,covered)
    if (coverage<p['min_coverage'] or accuracy<p['min_accuracy'] or
            gain<p['min_gain']):
        return None
    if v['temporal']=='halves':
        split=n//2
        for train,test in ((range(split),range(split,n)),
                           (range(split,n),range(split))):
            local={}
            for i in train:
                row=local.setdefault(keys[i],{});label=labels[i]
                row[label]=row.get(label,0)+1
            seen=hits=0
            for i in test:
                row=local.get(keys[i])
                if row:
                    seen+=1;hits+=int(_winner(row)==labels[i])
            if (seen/max(1,len(test))<v['min_temporal_coverage'] or
                    hits/max(1,seen)<v['min_temporal_accuracy']):
                return None
    buckets={}
    for key,row in counts.items():
        selected=_winner(row)
        support=sum(row.values());confidence=row[selected]/support
        if support>=p['min_bucket_support'] and confidence>=p['min_bucket_confidence']:
            buckets[key]={'winner':selected,'support':support,'confidence':confidence}
    if (not buckets or len(buckets)<p['required_buckets'] or
            (p['different_bucket_winners'] and
             len({row['winner'] for row in buckets.values()})<2)):
        return None
    return {'accuracy':accuracy,'coverage':coverage,'gain_over_majority':gain,
            'buckets':buckets}


def fit(program: dict, tasks: list[dict], *, max_dims: int = 3,
        preferred_reducers=(), existing: dict | None = None) -> dict:
    """Interpret a bounded learner description over meta-experience."""
    validate(program)
    if not tasks:
        return {'status':'pending','candidates_evaluated':0}
    constraints=program['constraints'];budget=program['budget']
    if len(tasks)<constraints['min_examples']:
        return {'status':'pending','candidates_evaluated':0}
    width=len(tasks[0]['features'])
    if (not 2<=width<=constraints['max_width'] or
            len(tasks)>budget['max_tasks'] or
            any(len(row['features'])!=width for row in tasks)):
        return {'status':'invalid_input','candidates_evaluated':0}
    started=process_time();evaluated=0;chosen=None
    labels=[row['winner'] for row in tasks]

    def judge(candidate,keys):
        nonlocal chosen
        result=_judge(keys,labels,program)
        if result is None:
            return False
        kind=program['hypothesis_generator']
        if kind=='projection_subsets':
            dims=candidate['dims'];cost=program['cost']
            score=(cost['accuracy_weight']*result['accuracy']*result['coverage']+
                   cost['gain_weight']*result['gain_over_majority']-
                   cost['dimension_penalty']*len(dims))
            view={'kind':'feature_projection','dims':list(dims),'score':score,
                  **result,'tasks':len(tasks)}
            rank=(-score,len(dims),dims)
            if chosen is None or rank<chosen[0]:
                chosen=(rank,view)
            return False
        view={'kind':'aggregate_program','spec':candidate['spec'],
              'cut':candidate['cut'],**result,'tasks':len(tasks)}
        chosen=(None,view)
        return True

    kind=program['hypothesis_generator']
    if kind=='projection_subsets':
        top=min(max(1,int(max_dims)),constraints['max_depth'],width-1)
        for size in range(1,top+1):
            for dims in combinations(range(width),size):
                evaluated+=1
                if evaluated>budget['max_candidates'] or process_time()-started>budget['max_cpu_s']:
                    return {'status':'budget_exceeded','candidates_evaluated':evaluated}
                keys=[_projection_key(row['features'],dims) for row in tasks]
                judge({'dims':dims},keys)
    else:
        folds=([existing['spec']] if existing is not None else
               meta_operators.candidate_specs(width,preferred_reducers=preferred_reducers,
                                              limit=budget['max_candidates']))
        for fold in folds:
            if existing is None:
                evaluated+=1
            if evaluated>budget['max_candidates'] or process_time()-started>budget['max_cpu_s']:
                return {'status':'budget_exceeded','candidates_evaluated':evaluated}
            values=[meta_operators.evaluate(row['features'],fold) for row in tasks]
            if any(value is None for value in values):
                continue
            distinct=sorted(set(values))
            if len(distinct)<2:
                continue
            cuts=([float(existing['cut'])] if existing is not None else
                  [(low+high)/2.0 for low,high in zip(distinct,distinct[1:])])
            for cut in cuts:
                keys=[str(int(value>cut)) for value in values]
                if len(set(keys))<2:
                    continue
                if judge({'spec':fold,'cut':cut},keys):
                    return {'status':'fitted','view':chosen[1],
                            'candidates_evaluated':evaluated}
    if chosen is None:
        return {'status':'rejected','candidates_evaluated':evaluated,
                'rollback':program['rollback']}
    return {'status':'fitted','view':chosen[1],
            'candidates_evaluated':evaluated}

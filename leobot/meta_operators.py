"""Typed, bounded interpretation of acquired meta-operator programs.

The arithmetic mapper reuses the existing numeric Expr DSL. The only new
substrate is finite indexed iteration, boolean comparison, and reduction;
which combination is useful is chosen from experience by MetaController.
"""
from __future__ import annotations

import hashlib
import json
from itertools import combinations

from .programs import Expr, operate


def operator_key(spec: dict) -> str:
    skeleton={'op':'fold','reduce':spec['reduce'],'map_output':'boolean'}
    encoded=json.dumps(skeleton,sort_keys=True,separators=(',',':'))
    return 'op_'+hashlib.blake2b(encoded.encode(),digest_size=8).hexdigest()


def candidate_specs(width: int, *, preferred_reducers=(), limit: int = 32) -> list[dict]:
    """Enumerate small programs by structural complexity, never by task name."""
    reducers=list(dict.fromkeys([*preferred_reducers,'min','max','sum']))
    reducers=[name for name in reducers if name in ('min','max','sum')]
    specs=[]
    for stride in range(1,min(4,int(width))+1):
        if width%stride:
            continue
        layouts=[([offset],Expr('var',0)) for offset in range(stride)]
        for a,b in combinations(range(stride),2):
            layouts.append(([a,b],Expr('sub',children=(Expr('var',0),Expr('var',1)))))
            layouts.append(([b,a],Expr('sub',children=(Expr('var',0),Expr('var',1)))))
        for indices,mapper in layouts:
            for comparison in ('gt','lt'):
                for reducer in reducers:
                    specs.append({'op':'fold_bool','stride':stride,'indices':indices,
                                  'map_expr':mapper.as_dict(),
                                  'compare':comparison,'reduce':reducer})
                    if len(specs)>=limit:
                        return specs
    return specs


def evaluate(features, spec: dict) -> int | None:
    """Evaluate one declarative fold; malformed or over-budget inputs abstain."""
    if not isinstance(spec,dict) or spec.get('op')!='fold_bool':
        return None
    try:
        values=tuple(float(value) for value in features)
        stride=int(spec['stride']);indices=tuple(int(i) for i in spec['indices'])
        reducer=spec['reduce'];compare=spec['compare']
    except (TypeError,ValueError,KeyError,OverflowError):
        return None
    if (not 1<=len(values)<=16 or not 1<=stride<=4 or len(values)%stride or
            not 1<=len(indices)<=2 or len(set(indices))!=len(indices) or
            any(i<0 or i>=stride for i in indices) or
            reducer not in ('sum','min','max') or compare not in ('gt','lt')):
        return None
    # A persisted program is data from outside this interpreter.  Admit only
    # the finite mapper grammar that the generator can actually produce.
    allowed=(Expr('var',0) if len(indices)==1 else
             Expr('sub',children=(Expr('var',0),Expr('var',1))))
    if spec.get('map_expr')!=allowed.as_dict():
        return None
    accumulator=None
    for start in range(0,len(values),stride):
        args=tuple(values[start+i] for i in indices)
        mapped=allowed.run(args)
        if mapped is None:
            return None
        boolean=int(mapped>0 if compare=='gt' else mapped<0)
        accumulator=(boolean if accumulator is None else
                     operate('add' if reducer=='sum' else reducer,
                             accumulator,boolean))
        if accumulator is None:
            return None
    return int(accumulator) if accumulator is not None else None

"""Small auditable RBF/kernel interpolation helpers for meta-learning.

This is intentionally NOT a text generator and not a replacement for Leobot's
symbolic/program learners.  It is an auxiliary selector inspired by exact RBF
interpolation: observed task-structure -> observed strategy cost.  The output
can only reorder existing safe strategies; the ordinary fallbacks remain.

No neural networks, gradient descent, embeddings, numpy, or external libraries.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite


@dataclass
class _Node:
    x: tuple[float, ...]
    count: int = 0
    success: int = 0
    cost_sum: float = 0.0

    @property
    def mean_cost(self) -> float:
        return self.cost_sum / max(1, self.count)

    def as_dict(self) -> dict:
        return {'x': list(self.x), 'count': self.count, 'success': self.success,
                'cost_sum': self.cost_sum}

    @classmethod
    def from_dict(cls, data: dict) -> '_Node':
        return cls(tuple(float(v) for v in data.get('x', ())),
                   int(data.get('count', 0)), int(data.get('success', 0)),
                   float(data.get('cost_sum', 0.0)))


class RBFStrategyRouter:
    """Kernel interpolator over small structural feature vectors.

    The normalization follows Granville's core idea: positive kernel weights
    are normalized for each query.  Exact feature matches are returned exactly
    from their aggregated empirical node.  Otherwise a Gaussian RBF is used.

    Duplicate observations at the same feature point are *distilled* into one
    node by sufficient statistics; memory therefore grows with distinct task
    signatures, not repeated episodes.
    """

    VERSION = 1

    def __init__(self, tau: float = 10.0, max_nodes_per_strategy: int = 128,
                 max_distance: float = 0.55) -> None:
        self.tau = max(0.01, float(tau))
        self.max_nodes_per_strategy = max(4, int(max_nodes_per_strategy))
        self.max_distance = max(0.0, float(max_distance))
        self.nodes: dict[str, dict[str, _Node]] = {}
        self.observations = 0
        self.distilled = 0

    @staticmethod
    def _key(x: tuple[float, ...]) -> str:
        return ','.join(f'{v:.9g}' for v in x)

    @staticmethod
    def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        if len(a) != len(b) or not a:
            return float('inf')
        # Features supplied by callers are already scaled to roughly [0, 1].
        return sum((x-y)*(x-y) for x,y in zip(a,b)) / len(a)

    def observe(self, x, strategy: str, *, success: bool, candidates: int,
                failure_budget: int) -> dict:
        point = tuple(float(v) for v in x)
        if not point or any(not isfinite(v) for v in point):
            return {'status': 'rbf_observation_ignored', 'reason': 'invalid_features'}
        strategy = str(strategy)
        table = self.nodes.setdefault(strategy, {})
        key = self._key(point)
        node = table.get(key)
        if node is None:
            node = table[key] = _Node(point)
        else:
            self.distilled += 1
        cand = max(0, int(candidates or 0))
        budget = max(1, int(failure_budget or 1))
        # Failed searches are not free: charge the observed exploration plus one
        # budget unit.  This lets the router learn to put repeatedly exhausted
        # strategies later while preserving them as fallbacks.
        effective = float(cand + (0 if success else budget))
        node.count += 1
        node.success += int(bool(success))
        node.cost_sum += effective
        self.observations += 1
        self._distill(strategy)
        return {'status': 'rbf_observation_recorded', 'strategy': strategy,
                'features': list(point), 'effective_cost': effective,
                'node_count': len(table)}

    def _distill(self, strategy: str) -> None:
        table = self.nodes.get(strategy, {})
        if len(table) <= self.max_nodes_per_strategy:
            return
        # Conservative auto-distillation: remove only the least-supported node;
        # ties prefer the oldest lexical key deterministically.  Repeated task
        # signatures have already been aggregated and therefore survive.
        victim = min(table.items(), key=lambda kv: (kv[1].count, kv[0]))[0]
        del table[victim]
        self.distilled += 1

    def predict(self, x, strategy: str) -> dict | None:
        point = tuple(float(v) for v in x)
        table = self.nodes.get(str(strategy), {})
        if not table:
            return None
        exact = table.get(self._key(point))
        if exact is not None:
            return {'strategy': str(strategy), 'cost': exact.mean_cost,
                    'confidence': 1.0, 'nearest_distance': 0.0,
                    'support': exact.count, 'mode': 'exact'}
        rows=[]
        nearest=float('inf')
        for node in table.values():
            d=self._distance(point,node.x); nearest=min(nearest,d)
            if d > self.max_distance:
                continue
            w=exp(-self.tau*d) * max(1, node.count)
            rows.append((w,node))
        if not rows:
            return None
        denom=sum(w for w,_ in rows)
        if denom <= 0:
            return None
        pred=sum(w*n.mean_cost for w,n in rows)/denom
        total_support=sum(n.count for _,n in rows)
        # Confidence is explicit and heuristic; it only gates reordering, never
        # correctness.  Safe fallbacks remain available after the first choice.
        confidence=(exp(-self.tau*nearest) * min(1.0, total_support/3.0))
        return {'strategy': str(strategy), 'cost': pred,
                'confidence': confidence, 'nearest_distance': nearest,
                'support': total_support, 'mode': 'interpolated'}

    def rank(self, x, strategies, *, min_confidence: float = 0.15) -> dict:
        default=list(strategies)
        scored=[]
        for s in default:
            p=self.predict(x,s)
            if p is not None:
                scored.append(p)
        # To reorder, every candidate strategy must have evidence and at least
        # one estimate must be sufficiently local. Otherwise keep deterministic
        # historical order.
        if len(scored) != len(default) or max((p['confidence'] for p in scored),default=0.0) < min_confidence:
            return {'order':default,'used':False,'scores':scored}
        scored.sort(key=lambda p:(p['cost'],-p['confidence'],default.index(p['strategy'])))
        return {'order':[p['strategy'] for p in scored],'used':True,'scores':scored}

    def as_dict(self) -> dict:
        return {'version':self.VERSION,'tau':self.tau,
                'max_nodes_per_strategy':self.max_nodes_per_strategy,
                'max_distance':self.max_distance,
                'observations':self.observations,'distilled':self.distilled,
                'nodes':{s:{k:n.as_dict() for k,n in rows.items()} for s,rows in self.nodes.items()}}

    @classmethod
    def from_dict(cls, data: dict | None) -> 'RBFStrategyRouter':
        data=data or {}
        obj=cls(data.get('tau',10.0),data.get('max_nodes_per_strategy',128),data.get('max_distance',0.55))
        obj.observations=int(data.get('observations',0));obj.distilled=int(data.get('distilled',0))
        for strategy,rows in (data.get('nodes',{}) or {}).items():
            obj.nodes[str(strategy)]={str(k):_Node.from_dict(v) for k,v in (rows or {}).items()}
        return obj

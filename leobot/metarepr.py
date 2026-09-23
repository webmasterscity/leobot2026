"""Cross-mechanism structural representation memory.

This module stores only domain-neutral role-flow hypotheses.  A role flow says
which input roles survive into an output representation, e.g. ``3 -> (0, 2)``.
It never stores predicate names, utterance tokens, entities, benchmark ids or
answers.  Producers may come from language schemas, numeric procedures or
symbolic actions.  Consumers must still confirm the mapping against their own
observations before it can affect a learned hypothesis.
"""
from __future__ import annotations
from copy import deepcopy
from itertools import permutations


class MetaRepresentationLibrary:
    VERSION = 3

    def __init__(self) -> None:
        self.projections: dict[str, dict] = {}
        self.role_sets: dict[str, dict] = {}
        self.role_cardinalities: dict[str, dict] = {}
        self.role_topologies: dict[str, dict] = {}

    @staticmethod
    def projection_key(input_arity: int, mapping) -> str:
        n = int(input_arity)
        m = tuple(int(x) for x in mapping)
        return f"proj:{n}:" + ','.join(map(str, m))

    @staticmethod
    def _valid(input_arity: int, mapping) -> tuple[int, tuple[int, ...]] | None:
        n = int(input_arity)
        m = tuple(int(x) for x in mapping)
        if n < 2 or n > 8 or not m or len(m) > 8:
            return None
        if any(i < 0 or i >= n for i in m):
            return None
        # Identity carries no compression/structural information.
        if len(m) == n and m == tuple(range(n)):
            return None
        return n, m

    @staticmethod
    def role_set_key(input_arity: int, roles) -> str:
        n=int(input_arity); vals=tuple(sorted(set(int(x) for x in roles)))
        return f"roles:{n}:" + ','.join(map(str,vals))

    @staticmethod
    def role_cardinality_key(cardinality: int) -> str:
        return f"card:{int(cardinality)}"

    def register_role_cardinality(self, cardinality: int, *, family: str, source: str,
                                  support: int = 1) -> dict:
        k=int(cardinality); fam=str(family).strip().lower(); src=str(source).strip()
        if k < 1 or k > 7:
            return {'status':'meta_representation_ignored','reason':'invalid_role_cardinality'}
        if not fam or not src:
            return {'status':'meta_representation_ignored','reason':'missing_provenance'}
        key=self.role_cardinality_key(k)
        row=self.role_cardinalities.setdefault(key,{'kind':'role_cardinality','cardinality':k,
                                                     'sources':{},'families':{},'support':0})
        amount=max(1,int(support)); prev=row['sources'].get(src)
        if not isinstance(prev,dict) or amount>int(prev.get('support',0)):
            row['sources'][src]={'family':fam,'support':amount}
        families={}
        for info in row['sources'].values():
            f=str(info.get('family','unknown'));families[f]=families.get(f,0)+max(1,int(info.get('support',1)))
        row['families']=families;row['support']=sum(families.values())
        return {'status':'meta_representation_registered','schema':key,'kind':'role_cardinality',
                'cardinality':k,'support':row['support'],'source_count':len(row['sources']),
                'families':sorted(row['families'])}

    def register_role_set(self, input_arity: int, roles, *, family: str,
                          source: str, support: int = 1) -> dict:
        n=int(input_arity); vals=tuple(sorted(set(int(x) for x in roles)))
        if n < 2 or n > 8 or not vals or len(vals) >= n or any(i<0 or i>=n for i in vals):
            return {'status':'meta_representation_ignored','reason':'invalid_role_set'}
        fam=str(family).strip().lower(); src=str(source).strip()
        if not fam or not src:
            return {'status':'meta_representation_ignored','reason':'missing_provenance'}
        key=self.role_set_key(n,vals)
        row=self.role_sets.setdefault(key,{'kind':'role_set','input_arity':n,'roles':list(vals),
                                           'sources':{},'families':{},'support':0})
        amount=max(1,int(support)); prev=row['sources'].get(src)
        if not isinstance(prev,dict) or amount>int(prev.get('support',0)):
            row['sources'][src]={'family':fam,'support':amount}
        families={}
        for info in row['sources'].values():
            f=str(info.get('family','unknown'));families[f]=families.get(f,0)+max(1,int(info.get('support',1)))
        row['families']=families;row['support']=sum(families.values())
        card=self.register_role_cardinality(len(vals),family=fam,source=src,support=amount)
        return {'status':'meta_representation_registered','schema':key,'kind':'role_set',
                'input_arity':n,'roles':list(vals),'support':row['support'],
                'source_count':len(row['sources']),'families':sorted(row['families']),
                'cardinality_schema':card.get('schema')}

    def register_projection(self, input_arity: int, mapping, *, family: str,
                            source: str, support: int = 1) -> dict:
        checked = self._valid(input_arity, mapping)
        if checked is None:
            return {'status': 'meta_representation_ignored', 'reason': 'invalid_or_identity_projection'}
        n, m = checked
        fam = str(family).strip().lower()
        src = str(source).strip()
        if not fam or not src:
            return {'status': 'meta_representation_ignored', 'reason': 'missing_provenance'}
        key = self.projection_key(n, m)
        kind = ('permutation' if len(m) == n and tuple(sorted(m)) == tuple(range(n))
                else 'projection')
        row = self.projections.setdefault(key, {
            'kind': kind, 'input_arity': n, 'mapping': list(m), 'sources': {},
            'families': {}, 'support': 0,
        })
        amount = max(1, int(support))
        prev = row['sources'].get(src)
        if not isinstance(prev, dict) or amount > int(prev.get('support', 0)):
            row['sources'][src] = {'family': fam, 'support': amount}
        families: dict[str, int] = {}
        for info in row['sources'].values():
            f = str(info.get('family', 'unknown'))
            families[f] = families.get(f, 0) + max(1, int(info.get('support', 1)))
        row['families'] = families
        row['support'] = sum(families.values())
        return {
            'status': 'meta_representation_registered', 'schema': key,
            'kind': row['kind'], 'input_arity': n, 'mapping': list(m),
            'support': row['support'], 'source_count': len(row['sources']),
            'families': sorted(row['families']),
        }



    @staticmethod
    def canonical_role_topology(input_arity: int, edges):
        """Canonical directed role-incidence topology, invariant to role renaming.

        Each edge is the ordered role tuple used by one relation/precondition.
        Predicate names and domain labels are deliberately absent.  Role labels
        are canonically renamed by exhaustive permutation (bounded to arity <= 8).
        """
        n=int(input_arity)
        try:
            clean=tuple(tuple(int(x) for x in edge) for edge in edges)
        except Exception:
            return None
        if n < 2 or n > 8 or not clean or len(clean) > 8:
            return None
        if any(not edge or len(edge)>4 or any(i<0 or i>=n for i in edge) for edge in clean):
            return None
        # Every role in the declared arity must participate; otherwise this is a
        # role-subset prior rather than a topology over the whole representation.
        if set(i for edge in clean for i in edge) != set(range(n)):
            return None
        best=None
        for rename in permutations(range(n)):
            candidate=tuple(sorted(tuple(rename[i] for i in edge) for edge in clean))
            if best is None or candidate < best:
                best=candidate
        return best

    @classmethod
    def role_topology_key(cls, input_arity: int, edges) -> str | None:
        canon=cls.canonical_role_topology(input_arity,edges)
        if canon is None:
            return None
        encoded=';'.join(','.join(map(str,edge)) for edge in canon)
        return f"topo:{int(input_arity)}:{encoded}"

    def register_role_topology(self, input_arity: int, edges, *, family: str,
                               source: str, support: int = 1) -> dict:
        n=int(input_arity); canon=self.canonical_role_topology(n,edges)
        fam=str(family).strip().lower(); src=str(source).strip()
        if canon is None:
            return {'status':'meta_representation_ignored','reason':'invalid_role_topology'}
        if not fam or not src:
            return {'status':'meta_representation_ignored','reason':'missing_provenance'}
        key=self.role_topology_key(n,canon)
        row=self.role_topologies.setdefault(key,{'kind':'role_topology','input_arity':n,
                                                  'edges':[list(x) for x in canon],
                                                  'sources':{},'families':{},'support':0})
        amount=max(1,int(support)); prev=row['sources'].get(src)
        if not isinstance(prev,dict) or amount>int(prev.get('support',0)):
            row['sources'][src]={'family':fam,'support':amount}
        families={}
        for info in row['sources'].values():
            f=str(info.get('family','unknown'));families[f]=families.get(f,0)+max(1,int(info.get('support',1)))
        row['families']=families;row['support']=sum(families.values())
        return {'status':'meta_representation_registered','schema':key,'kind':'role_topology',
                'input_arity':n,'edges':[list(x) for x in canon],
                'support':row['support'],'source_count':len(row['sources']),
                'families':sorted(row['families'])}

    def has_source(self, source: str) -> bool:
        src=str(source).strip()
        return any(src in row.get('sources',{}) for table in (self.projections,self.role_sets,self.role_cardinalities,self.role_topologies) for row in table.values())

    def withdraw_source(self, source: str) -> dict:
        """Withdraw every structural prior contributed by one provenance source."""
        src=str(source).strip(); removed=[]
        for table in (self.projections,self.role_sets,self.role_cardinalities,self.role_topologies):
            for key in list(table):
                row=table[key]
                if src not in row.get('sources',{}):
                    continue
                row['sources'].pop(src,None); removed.append(key)
                if not row['sources']:
                    table.pop(key,None); continue
                families={}
                for info in row['sources'].values():
                    fam=str(info.get('family','unknown'))
                    families[fam]=families.get(fam,0)+max(1,int(info.get('support',1)))
                row['families']=families; row['support']=sum(families.values())
        return {'status':'meta_representation_source_withdrawn','source':src,'schemas':sorted(removed)}

    def rows(self) -> list[dict]:
        out=[deepcopy(self.projections[k]) | {'schema': k} for k in sorted(self.projections)]
        out += [deepcopy(self.role_sets[k]) | {'schema': k} for k in sorted(self.role_sets)]
        out += [deepcopy(self.role_cardinalities[k]) | {'schema': k} for k in sorted(self.role_cardinalities)]
        out += [deepcopy(self.role_topologies[k]) | {'schema': k} for k in sorted(self.role_topologies)]
        return out

    def as_dict(self) -> dict:
        return {'version': self.VERSION, 'projections': deepcopy(self.projections), 'role_sets': deepcopy(self.role_sets), 'role_cardinalities': deepcopy(self.role_cardinalities), 'role_topologies': deepcopy(self.role_topologies)}

    @classmethod
    def from_dict(cls, data: dict | None) -> 'MetaRepresentationLibrary':
        obj = cls()
        if not isinstance(data, dict):
            return obj
        rows = data.get('projections', {})
        if not isinstance(rows, dict):
            return obj
        # Re-register rather than trust derived totals from persistence.
        for _key, row in rows.items():
            if not isinstance(row, dict):
                continue
            n = row.get('input_arity'); mapping = row.get('mapping', ())
            for source, info in (row.get('sources') or {}).items():
                family = info.get('family','unknown') if isinstance(info,dict) else 'unknown'
                support = info.get('support',1) if isinstance(info,dict) else info
                obj.register_projection(n,mapping,family=str(family),source=str(source),support=int(support))
        for _key,row in (data.get('role_sets',{}) or {}).items():
            if not isinstance(row,dict): continue
            n=row.get('input_arity'); roles=row.get('roles',())
            for source,info in (row.get('sources') or {}).items():
                family=info.get('family','unknown') if isinstance(info,dict) else 'unknown'
                support=info.get('support',1) if isinstance(info,dict) else info
                obj.register_role_set(n,roles,family=str(family),source=str(source),support=int(support))
        # Cardinality rows are normally derivable from role sets. Load any
        # additional future rows whose provenance was not represented above.
        for _key,row in (data.get('role_cardinalities',{}) or {}).items():
            if not isinstance(row,dict): continue
            k=row.get('cardinality')
            for source,info in (row.get('sources') or {}).items():
                if obj.role_cardinalities.get(obj.role_cardinality_key(k),{}).get('sources',{}).get(str(source)):
                    continue
                family=info.get('family','unknown') if isinstance(info,dict) else 'unknown'
                support=info.get('support',1) if isinstance(info,dict) else info
                obj.register_role_cardinality(k,family=str(family),source=str(source),support=int(support))
        for _key,row in (data.get('role_topologies',{}) or {}).items():
            if not isinstance(row,dict): continue
            n=row.get('input_arity'); edges=row.get('edges',())
            for source,info in (row.get('sources') or {}).items():
                family=info.get('family','unknown') if isinstance(info,dict) else 'unknown'
                support=info.get('support',1) if isinstance(info,dict) else info
                obj.register_role_topology(n,edges,family=str(family),source=str(source),support=int(support))
        return obj

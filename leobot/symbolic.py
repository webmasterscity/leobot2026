"""Induce symbolic action/goal schemas from natural language and factual state change.

No action names, semantic frames, or hand-authored STRIPS operators are supplied to
this learner.  A training episode is only:

    natural-language cue + set(facts before) + set(facts after)

Constants that are mentioned in the cue and occur in the factual state are
replaced by role variables according to textual occurrence.  Repeated successful
episodes induce add/delete effects and candidate preconditions.  No-change
attempts act as contrastive counterexamples: the learner chooses a smallest set
of candidate preconditions that separates every observed failure from successes.

This is deliberately a bounded, explicit symbolic experiment.  It does not claim
open-world language understanding, stochastic planning, or unrestricted AGI.
"""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from itertools import combinations, product, permutations
import hashlib
import json
import re
from typing import Iterable

from .language import normalize
from .metarepr import MetaRepresentationLibrary

Fact = tuple[str, ...]
TemplateFact = tuple[str, ...]
_MARKER_RE = re.compile(r'<e(\d+)>')


def _canon_fact(fact: Iterable[str]) -> Fact:
    parts = tuple(normalize(str(x)) for x in fact)
    if len(parts) < 2 or not parts[0] or any(not x for x in parts[1:]):
        raise ValueError('Cada hecho simbólico requiere predicado y al menos un argumento no vacío.')
    if len(parts) > 7:
        raise ValueError('La aridad factual excede el límite experimental.')
    return parts


def _canon_state(state: Iterable[Iterable[str]]) -> frozenset[Fact]:
    out = frozenset(_canon_fact(f) for f in state)
    if len(out) > 20_000:
        raise ValueError('El estado simbólico excede el límite experimental de 20.000 hechos.')
    return out


def _entities(state: Iterable[Fact]) -> set[str]:
    return {arg for fact in state for arg in fact[1:]}


def _mentioned_mapping(text: str, entities: Iterable[str]) -> tuple[str, dict[str, str]] | None:
    """Delexicalize uniquely mentioned state constants in left-to-right order."""
    norm = normalize(text)
    hits = []
    for entity in sorted(set(entities), key=lambda x: (-len(x), x)):
        matches = list(re.finditer(r'(?<!\w)' + re.escape(entity) + r'(?!\w)', norm))
        if len(matches) == 1:
            m = matches[0]
            hits.append((m.start(), m.end(), entity))
    # Overlapping names are unsafe (e.g. "san" and "san jose"). Keep the
    # longest span and reject a second overlapping semantic entity.
    hits.sort(key=lambda x: (x[0], -(x[1]-x[0]), x[2]))
    selected = []
    occupied: list[tuple[int,int]] = []
    for start, end, entity in hits:
        if any(not (end <= a or start >= b) for a,b in occupied):
            continue
        selected.append((start,end,entity)); occupied.append((start,end))
    selected.sort()
    if not selected:
        return None
    mapping: dict[str,str] = {}
    pieces=[]; cursor=0
    for i,(start,end,entity) in enumerate(selected):
        marker=f'<e{i}>'
        pieces.extend((norm[cursor:start], marker))
        mapping[entity]=marker
        cursor=end
    pieces.append(norm[cursor:])
    return ''.join(pieces), mapping


def _template_fact(fact: Fact, mapping: dict[str,str], require_all_mapped: bool = True) -> TemplateFact | None:
    args=[]
    for arg in fact[1:]:
        if arg in mapping:
            args.append(mapping[arg])
        elif require_all_mapped:
            return None
        else:
            args.append(arg)
    return (fact[0], *args)


def _instantiate(template: TemplateFact, binding: dict[str,str]) -> Fact | None:
    args=[]
    for arg in template[1:]:
        if _MARKER_RE.fullmatch(arg):
            value=binding.get(arg)
            if value is None:
                return None
            args.append(value)
        else:
            args.append(arg)
    return (template[0], *args)


def _template_sort_key(f: TemplateFact):
    return (f[0], len(f), f)


def _pattern_regex(pattern: str) -> re.Pattern:
    # Non-greedy captures between escaped literal spans permit multi-word entities.
    pieces=[]; pos=0
    for m in _MARKER_RE.finditer(pattern):
        pieces.append(re.escape(pattern[pos:m.start()]))
        pieces.append(f'(?P<e{m.group(1)}>.+?)')
        pos=m.end()
    pieces.append(re.escape(pattern[pos:]))
    return re.compile('^' + ''.join(pieces) + '$')


def _binding_from_text(pattern: str, text: str) -> dict[str,str] | None:
    m=_pattern_regex(pattern).fullmatch(normalize(text))
    if not m:
        return None
    out={f'<{name}>': normalize(value) for name,value in m.groupdict().items()}
    if len(set(out.values())) != len(out.values()):
        # Same concrete entity can legitimately fill two roles in some domains,
        # but accepting it silently can collapse source/destination roles.  The
        # current experiment stays conservative.
        return None
    return out


def _surface_from_goal(text: str, goal: frozenset[Fact]):
    return _mentioned_mapping(text, _entities(goal))


class _MutableFactIndex:
    """Small explicit mutable index used by the deterministic hierarchy fast path."""
    def __init__(self, facts: Iterable[Fact]):
        self.facts:set[Fact]=set()
        self.by_sig=defaultdict(set);self.by_arg=defaultdict(set);self.entities:set[str]=set()
        for fact in facts:self.add(fact)

    def add(self, fact: Fact) -> None:
        if fact in self.facts:return
        self.facts.add(fact);sig=(fact[0],len(fact));self.by_sig[sig].add(fact)
        for pos,value in enumerate(fact[1:],start=1):
            self.by_arg[(sig,pos,value)].add(fact);self.entities.add(value)

    def remove(self, fact: Fact) -> None:
        if fact not in self.facts:return
        self.facts.remove(fact);sig=(fact[0],len(fact));self.by_sig[sig].discard(fact)
        for pos,value in enumerate(fact[1:],start=1):self.by_arg[(sig,pos,value)].discard(fact)

    def candidates(self, template: TemplateFact, binding: dict[str,str]):
        sig=(template[0],len(template));constraints=[]
        for pos,want in enumerate(template[1:],start=1):
            if _MARKER_RE.fullmatch(want):
                value=binding.get(want)
                if value is not None:constraints.append((pos,value))
            else:constraints.append((pos,want))
        if not constraints:return self.by_sig.get(sig,())
        pools=[self.by_arg.get((sig,pos,value),()) for pos,value in constraints]
        if any(not p for p in pools):return ()
        base=min(pools,key=len)
        return [f for f in base if all(f[pos]==value for pos,value in constraints)]


class SymbolicWorldLearner:
    """Ground symbolic operators and goal schemas, then plan over learned models."""

    def __init__(self, min_support: int = 3, goal_min_support: int = 2, alias_min_support: int = 2,
                 max_precondition_candidates: int = 24,
                 max_action_bindings: int = 10_000, macro_min_support: int = 3, iterative_min_support: int = 3) -> None:
        self.min_support=max(2,int(min_support))
        self.goal_min_support=max(2,int(goal_min_support))
        self.alias_min_support=max(2,int(alias_min_support))
        self.max_precondition_candidates=max(1,int(max_precondition_candidates))
        self.max_action_bindings=max(1,int(max_action_bindings))
        self.macro_min_support=max(2,int(macro_min_support))
        self.iterative_min_support=max(3,int(iterative_min_support))
        self.sessions: dict[str,dict] = {}
        self.goal_sessions: dict[str,dict] = {}
        self.alias_sessions: dict[str,dict] = {}
        self.macro_sessions: dict[str,dict] = {}
        self.iterative_sessions: dict[str,dict] = {}
        # V4.1: explicit learned meta-schemas group structurally analogous
        # operators.  New domains consult one live representative per schema
        # instead of rescanning every concrete operator ever learned.
        self.analogy_schemas: dict[str,dict] = {}
        self.analogy_schema_by_pattern: dict[str,str] = {}
        self.analogy_unclustered: set[str] = set()
        # Cross-representation transformation priors.  These do not encode domain
        # predicates or answers: they store only structural permutations learned
        # in another representation (e.g. a numeric tuple procedure).
        self.external_permutation_schemas: dict[str,dict] = {}
        self.external_projection_schemas: dict[str,dict] = {}
        self.external_role_sets: dict[str,dict] = {}
        self.external_role_cardinalities: dict[str,dict] = {}
        self.external_role_topologies: dict[str,dict] = {}
        # Shared bot-level MetaController; Bot owns/persists the single instance.
        self.meta_controller = None
        self.audit: list[dict] = []

    @staticmethod
    def _episode_id(text: str, before: frozenset[Fact], after: frozenset[Fact]) -> str:
        return json.dumps({'text':normalize(text),'before':sorted(before),'after':sorted(after)},
                          ensure_ascii=False,sort_keys=True,separators=(',',':'))

    def _encode_episode(self, text: str, before: frozenset[Fact], after: frozenset[Fact]):
        aligned=_mentioned_mapping(text, _entities(before | after))
        if aligned is None:
            return None
        pattern,mapping=aligned
        # Every changed constant must be grounded in the language cue.  Otherwise
        # parameter roles would be inserted by the developer/evaluator rather than learned.
        changed=(before-after) | (after-before)
        changed_entities=_entities(changed)
        if not changed_entities.issubset(mapping):
            return None
        before_t={t for f in before if (t:=_template_fact(f,mapping,True)) is not None}
        add_t={t for f in after-before if (t:=_template_fact(f,mapping,True)) is not None}
        del_t={t for f in before-after if (t:=_template_fact(f,mapping,True)) is not None}
        if changed and (not add_t and not del_t):
            return None
        return pattern,mapping,before_t,add_t,del_t

    @staticmethod
    def _pattern_role_count(pattern: str) -> int:
        roles=[int(m.group(1)) for m in _MARKER_RE.finditer(pattern)]
        return (max(roles)+1) if roles else 0

    @staticmethod
    def _fact_role_edge(template: TemplateFact) -> tuple[int, ...] | None:
        roles=[]
        for arg in template[1:]:
            m=_MARKER_RE.fullmatch(arg)
            if m is not None:
                roles.append(int(m.group(1)))
        if not roles:
            return None
        return tuple(roles)

    def register_external_role_topology(self, input_arity: int, edges, source: str, support: int = 1) -> dict:
        n=int(input_arity); canon=MetaRepresentationLibrary.canonical_role_topology(n,edges)
        if canon is None:
            return {'status':'cross_modal_schema_ignored','reason':'invalid_role_topology'}
        key=MetaRepresentationLibrary.role_topology_key(n,canon)
        row=self.external_role_topologies.setdefault(key,{'kind':'role_topology','input_arity':n,
                                                           'edges':[list(x) for x in canon],
                                                           'sources':{},'support':0})
        src=normalize(str(source)); old=int(row['sources'].get(src,0));
        row['sources'][src]=max(old,max(1,int(support))); row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],
                'sources':len(row['sources'])}

    @staticmethod
    def _minimal_hitting_set(candidates: set[TemplateFact], failures: list[set[TemplateFact]], limit: int):
        ordered=sorted(candidates,key=_template_sort_key)
        if len(ordered)>limit:
            return None,'too_many_precondition_candidates'
        missing_sets=[]
        for fail in failures:
            missing=set(ordered)-fail
            if not missing:
                return None,'indistinguishable_failure'
            missing_sets.append(missing)
        if not missing_sets:
            return set(ordered),'positive_only'
        for size in range(1,len(ordered)+1):
            winners=[]
            for combo in combinations(ordered,size):
                s=set(combo)
                if all(s & missing for missing in missing_sets):
                    winners.append(combo)
                    if len(winners)>1:
                        break
            if len(winners)==1:
                return set(winners[0]),'contrastive_unique'
            if len(winners)>1:
                # Ambiguous minimal preconditions: preserve uncertainty rather
                # than selecting lexicographically and fabricating causality.
                return None,'ambiguous_minimal_preconditions'
        return None,'no_separating_preconditions'

    @staticmethod
    def _map_template_markers(template: TemplateFact, marker_map: dict[str,str]) -> TemplateFact:
        return (template[0], *(marker_map.get(x, x) for x in template[1:]))

    @staticmethod
    def _effect_alignment(source: dict, target_add: tuple[TemplateFact, ...],
                          target_delete: tuple[TemplateFact, ...],
                          marker_map: dict[str,str]) -> dict[str,str] | None:
        """Align effect predicates while preserving role topology.

        Predicate names may change across domains, but equality relations among
        source predicates are preserved: one source predicate cannot silently map
        to two target predicates, and two source predicates cannot collapse into
        one target predicate.  This keeps the analogy structural rather than a
        bag-of-arities match.
        """
        src_add=[tuple(x) for x in source.get('add',())]
        src_del=[tuple(x) for x in source.get('delete',())]
        if len(src_add)!=len(target_add) or len(src_del)!=len(target_delete):
            return None

        def aligned_args(src: TemplateFact, tgt: TemplateFact) -> bool:
            if len(src)!=len(tgt): return False
            mapped=SymbolicWorldLearner._map_template_markers(src,marker_map)
            return mapped[1:]==tgt[1:]

        # Effect sets are intentionally small in the current symbolic learner.
        # Backtracking over their permutations avoids privileging predicate names.
        for add_perm in permutations(target_add):
            if not all(aligned_args(a,b) for a,b in zip(src_add,add_perm)): continue
            for del_perm in permutations(target_delete):
                if not all(aligned_args(a,b) for a,b in zip(src_del,del_perm)): continue
                pmap={}; reverse={};ok=True
                for a,b in [*zip(src_add,add_perm),*zip(src_del,del_perm)]:
                    sp,tp=a[0],b[0]
                    if sp in pmap and pmap[sp]!=tp: ok=False;break
                    if tp in reverse and reverse[tp]!=sp: ok=False;break
                    pmap[sp]=tp;reverse[tp]=sp
                if ok:return pmap
        return None


    @staticmethod
    def _permutation_key(perm) -> str:
        perm=tuple(int(x) for x in perm)
        return f"perm:{len(perm)}:" + ','.join(map(str,perm))

    def register_external_permutation(self, perm, source: str, support: int = 1) -> dict:
        """Register a representation-independent permutation hypothesis.

        The schema stores only the mapping between mutable slots.  It carries no
        predicate names, language cues, entities or domain labels.  Registration
        is idempotent per source and is therefore auditable/persistable.
        """
        perm=tuple(int(x) for x in perm)
        if len(perm)<2 or tuple(sorted(perm))!=tuple(range(len(perm))) or perm==tuple(range(len(perm))):
            return {'status':'cross_modal_schema_ignored','reason':'not_nontrivial_permutation'}
        key=self._permutation_key(perm)
        row=self.external_permutation_schemas.setdefault(key,{'kind':'permutation','perm':list(perm),'sources':{},'support':0})
        src=normalize(str(source))
        old=int(row['sources'].get(src,0)); new=max(old,max(1,int(support)))
        row['sources'][src]=new; row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],'sources':len(row['sources'])}

    @staticmethod
    def _projection_key(input_arity: int, mapping) -> str:
        mapping=tuple(int(x) for x in mapping)
        return f"proj:{int(input_arity)}:" + ','.join(map(str,mapping))

    def register_external_projection(self, input_arity: int, mapping, source: str, support: int = 1) -> dict:
        n=int(input_arity);mapping=tuple(int(x) for x in mapping)
        if n<2 or not mapping or any(i<0 or i>=n for i in mapping):
            return {'status':'cross_modal_schema_ignored','reason':'invalid_projection'}
        if len(mapping)==n and mapping==tuple(range(n)):
            return {'status':'cross_modal_schema_ignored','reason':'identity_projection'}
        # Bijective same-arity projections are represented by the permutation
        # family to avoid duplicate priors for the same structural hypothesis.
        if len(mapping)==n and tuple(sorted(mapping))==tuple(range(n)):
            return self.register_external_permutation(mapping,source,support)
        key=self._projection_key(n,mapping)
        row=self.external_projection_schemas.setdefault(key,{'kind':'projection','input_arity':n,'mapping':list(mapping),'sources':{},'support':0})
        src=normalize(str(source));old=int(row['sources'].get(src,0));row['sources'][src]=max(old,max(1,int(support)))
        row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],'sources':len(row['sources'])}

    @staticmethod
    def _role_set_key(input_arity: int, roles) -> str:
        vals=tuple(sorted(set(int(x) for x in roles)))
        return f"roles:{int(input_arity)}:" + ','.join(map(str,vals))

    def register_external_role_set(self, input_arity: int, roles, source: str, support: int = 1) -> dict:
        n=int(input_arity); vals=tuple(sorted(set(int(x) for x in roles)))
        if n<2 or not vals or len(vals)>=n or any(i<0 or i>=n for i in vals):
            return {'status':'cross_modal_schema_ignored','reason':'invalid_role_set'}
        key=self._role_set_key(n,vals)
        row=self.external_role_sets.setdefault(key,{'kind':'role_set','input_arity':n,'roles':list(vals),'sources':{},'support':0})
        src=normalize(str(source));old=int(row['sources'].get(src,0));row['sources'][src]=max(old,max(1,int(support)))
        row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],'sources':len(row['sources'])}

    @staticmethod
    def _role_cardinality_key(cardinality: int) -> str:
        return f"card:{int(cardinality)}"

    def register_external_role_cardinality(self, cardinality: int, source: str, support: int = 1) -> dict:
        k=int(cardinality)
        if k<1:
            return {'status':'cross_modal_schema_ignored','reason':'invalid_role_cardinality'}
        key=self._role_cardinality_key(k)
        row=self.external_role_cardinalities.setdefault(
            key,{'kind':'role_cardinality','cardinality':k,'sources':{},'support':0})
        src=normalize(str(source));old=int(row['sources'].get(src,0));row['sources'][src]=max(old,max(1,int(support)))
        row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],'sources':len(row['sources'])}

    @staticmethod
    def _effect_projection_signature(pattern: str, add: tuple[TemplateFact, ...], delete: tuple[TemplateFact, ...]):
        """Infer role-flow for a single relational replacement.

        Example: ``at(<e0>,<e1>) -> at(<e0>,<e2>)`` under a three-role
        instruction becomes ``proj:3:0,2``.  Predicate names are intentionally
        absent from the signature.
        """
        if len(add)!=1 or len(delete)!=1:return None
        a,d=tuple(add[0]),tuple(delete[0])
        if a[0]!=d[0] or len(a)!=len(d) or a==d:return None
        vals=(*a[1:],*d[1:])
        if any(_MARKER_RE.fullmatch(x) is None for x in vals):return None
        marker_ids=[int(x[2:-1]) for x in re.findall(r'<e\d+>',pattern)]
        if not marker_ids:return None
        n=max(marker_ids)+1
        mapping=tuple(int(x[2:-1]) for x in a[1:])
        if any(i>=n for i in mapping):return None
        return n,mapping

    def _fit_by_cross_modal_projection(self, pattern: str) -> dict | None:
        session=self.sessions[pattern]
        successes=[o for o in session['observations'] if o['success']]
        failures=[o for o in session['observations'] if not o['success']]
        if len(successes)<2 or not failures:return None
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:return None
        add=tuple(tuple(x) for x in successes[0]['add']);delete=tuple(tuple(x) for x in successes[0]['delete'])
        sig=self._effect_projection_signature(pattern,add,delete)
        if sig is None:return None
        n,mapping=sig;key=self._projection_key(n,mapping);prior=self.external_projection_schemas.get(key)
        if prior is None:return None
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]:common &= set(tuple(x) for x in o['before'])
        mandatory=set(delete);context_candidates=common-mandatory;residual=[]
        for o in failures:
            fail=set(tuple(x) for x in o['before'])
            if mandatory.issubset(fail):residual.append(fail-mandatory)
        if residual:
            extra,mode=self._minimal_hitting_set(context_candidates,residual,self.max_precondition_candidates)
            if extra is None or mode!='contrastive_unique':return None
        else:
            extra=set();mode='mandatory_delete_contrast'
        pre=mandatory|set(extra)
        if not pre:return None
        session.update({'promoted':True,'status':'operator_learned',
                        'preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                        'add':[list(x) for x in sorted(add,key=_template_sort_key)],
                        'delete':[list(x) for x in sorted(delete,key=_template_sort_key)],
                        'support':len(successes),'failures':len(failures),
                        'precondition_mode':'cross_modal_projection_transfer',
                        'cross_modal_schema':key,'cross_modal_sources':sorted(prior.get('sources',{}))})
        self._mark_unclustered(pattern)
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':session['preconditions'],'add':session['add'],'delete':session['delete'],
                'precondition_mode':'cross_modal_projection_transfer','cross_modal_schema':key,
                'cross_modal_sources':session['cross_modal_sources']}

    def _fit_by_meta_role_set(self, pattern: str) -> dict | None:
        session=self.sessions[pattern]
        successes=[o for o in session['observations'] if o['success']]
        failures=[o for o in session['observations'] if not o['success']]
        if len(successes)<2 or not failures:return None
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:return None
        add=tuple(tuple(x) for x in successes[0]['add']);delete=tuple(tuple(x) for x in successes[0]['delete'])
        sig=self._effect_projection_signature(pattern,add,delete)
        if sig is None:return None
        n,mapping=sig; key=self._role_set_key(n,mapping); prior=self.external_role_sets.get(key)
        if prior is None:return None
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]:common &= set(tuple(x) for x in o['before'])
        mandatory=set(delete); context_candidates=common-mandatory; residual=[]
        for o in failures:
            fail=set(tuple(x) for x in o['before'])
            if mandatory.issubset(fail):residual.append(fail-mandatory)
        if residual:
            extra,mode=self._minimal_hitting_set(context_candidates,residual,self.max_precondition_candidates)
            if extra is None or mode!='contrastive_unique':return None
        else:
            extra=set()
        pre=mandatory|set(extra)
        if not pre:return None
        session.update({'promoted':True,'status':'operator_learned',
                        'preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                        'add':[list(x) for x in sorted(add,key=_template_sort_key)],
                        'delete':[list(x) for x in sorted(delete,key=_template_sort_key)],
                        'support':len(successes),'failures':len(failures),
                        'precondition_mode':'meta_role_set_transfer','cross_modal_schema':key,
                        'cross_modal_sources':sorted(prior.get('sources',{}))})
        self._mark_unclustered(pattern)
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':session['preconditions'],'add':session['add'],'delete':session['delete'],
                'precondition_mode':'meta_role_set_transfer','cross_modal_schema':key,
                'cross_modal_sources':session['cross_modal_sources']}

    def _fit_by_meta_role_cardinality(self, pattern: str) -> dict | None:
        """Transfer only the *number* of relevant roles across representations.

        The prior never identifies which roles or what predicates/preconditions mean.
        The target action's own observed effect determines the concrete role flow; target
        failures still have to identify any contextual preconditions.  At least two
        independent sources are required so a single earlier task cannot impose a
        cardinality on an unrelated domain.
        """
        session=self.sessions[pattern]
        successes=[o for o in session['observations'] if o['success']]
        failures=[o for o in session['observations'] if not o['success']]
        if len(successes)<2 or not failures:return None
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:return None
        add=tuple(tuple(x) for x in successes[0]['add']);delete=tuple(tuple(x) for x in successes[0]['delete'])
        sig=self._effect_projection_signature(pattern,add,delete)
        if sig is None:return None
        n,mapping=sig
        k=len(set(mapping))
        key=self._role_cardinality_key(k)
        prior=self.external_role_cardinalities.get(key)
        if prior is None or len(prior.get('sources',{}))<2:return None
        # The prior says only k.  The concrete mapping above came entirely from the
        # target action's observed add/delete effect, so this also works across arity.
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]:common &= set(tuple(x) for x in o['before'])
        mandatory=set(delete); context_candidates=common-mandatory; residual=[]
        for o in failures:
            fail=set(tuple(x) for x in o['before'])
            if mandatory.issubset(fail):residual.append(fail-mandatory)
        if residual:
            extra,mode=self._minimal_hitting_set(context_candidates,residual,self.max_precondition_candidates)
            if extra is None or mode!='contrastive_unique':return None
        else:
            extra=set();mode='mandatory_delete_contrast'
        pre=mandatory|set(extra)
        if not pre:return None
        session.update({'promoted':True,'status':'operator_learned',
                        'preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                        'add':[list(x) for x in sorted(add,key=_template_sort_key)],
                        'delete':[list(x) for x in sorted(delete,key=_template_sort_key)],
                        'support':len(successes),'failures':len(failures),
                        'precondition_mode':'meta_role_cardinality_transfer',
                        'cross_modal_schema':key,
                        'target_role_mapping':list(mapping),
                        'cross_modal_sources':sorted(prior.get('sources',{}))})
        self._mark_unclustered(pattern)
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':session['preconditions'],'add':session['add'],'delete':session['delete'],
                'precondition_mode':'meta_role_cardinality_transfer','cross_modal_schema':key,
                'target_role_mapping':list(mapping),'cross_modal_sources':session['cross_modal_sources']}

    def _fit_by_meta_role_topology(self, pattern: str) -> dict | None:
        """Use a domain-neutral directed role topology as a conservative prior.

        The source topology contains only ordered role incidences, never predicate
        names.  The target must provide two independent successful transitions,
        a consistent effect, and exactly one subset of its own observed facts that
        matches a topology supported by >=2 independent sources.  Any observed
        failure containing all selected preconditions vetoes the transfer.
        """
        session=self.sessions[pattern]
        successes=[o for o in session['observations'] if o['success']]
        failures=[o for o in session['observations'] if not o['success']]
        if len(successes)<2:
            return None
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:
            return None
        add=tuple(tuple(x) for x in successes[0]['add']); delete=tuple(tuple(x) for x in successes[0]['delete'])
        if not add and not delete:
            return None
        n=self._pattern_role_count(pattern)
        if n < 2:
            return None
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]:
            common &= set(tuple(x) for x in o['before'])
        mandatory=set(delete)
        if not mandatory.issubset(common):
            return None
        usable=[]
        for fact in sorted(common,key=_template_sort_key):
            edge=self._fact_role_edge(fact)
            if edge is not None:
                usable.append((fact,edge))
        if len(usable)>self.max_precondition_candidates:
            return None
        matches=[]
        for key,row in sorted(self.external_role_topologies.items()):
            if int(row.get('input_arity',0))!=n or len(row.get('sources',{}))<2:
                continue
            edges=tuple(tuple(int(x) for x in e) for e in row.get('edges',()))
            width=len(edges)
            if width<1 or width>len(usable):
                continue
            # Bound structural subset search independently of domain size.
            checked=0
            for combo in combinations(usable,width):
                checked+=1
                if checked>20_000:
                    break
                facts={fact for fact,_edge in combo}
                if not mandatory.issubset(facts):
                    continue
                topo=MetaRepresentationLibrary.canonical_role_topology(n,[edge for _fact,edge in combo])
                if topo != edges:
                    continue
                # A target failure with every proposed precondition present is
                # direct counterevidence against this transfer.
                contradicted=False
                for obs in failures:
                    fail=set(tuple(x) for x in obs['before'])
                    if facts.issubset(fail):
                        contradicted=True; break
                if contradicted:
                    continue
                matches.append((key,row,facts))
        # Multiple structural embeddings remain uncertainty; do not select one
        # lexicographically just to make the task pass.
        unique={}
        for key,row,facts in matches:
            sig=tuple(sorted(facts,key=_template_sort_key))
            unique[(key,sig)]=(key,row,facts)
        if len(unique)!=1:
            return None
        key,row,pre=next(iter(unique.values()))
        session.update({'promoted':True,'status':'operator_learned',
                        'preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                        'add':[list(x) for x in sorted(add,key=_template_sort_key)],
                        'delete':[list(x) for x in sorted(delete,key=_template_sort_key)],
                        'support':len(successes),'failures':len(failures),
                        'precondition_mode':'meta_role_topology_transfer',
                        'cross_modal_schema':key,
                        'cross_modal_sources':sorted(row.get('sources',{}))})
        self._mark_unclustered(pattern)
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':session['preconditions'],'add':session['add'],'delete':session['delete'],
                'precondition_mode':'meta_role_topology_transfer','cross_modal_schema':key,
                'cross_modal_sources':session['cross_modal_sources']}

    @staticmethod
    def _effect_permutation_signature(add: tuple[TemplateFact, ...], delete: tuple[TemplateFact, ...]):
        """Return a pure row-payload permutation, or None.

        A compatible symbolic effect deletes N tuples and adds N tuples of one
        predicate.  Exactly one argument position is allowed to change; all other
        positions identify the row.  The changed values must be permuted, not
        invented or destroyed.  This makes the signature independent of domain
        predicate names and compatible with tuple projections learned elsewhere.
        """
        if len(add)<2 or len(add)!=len(delete): return None
        preds={f[0] for f in (*add,*delete)}
        arities={len(f) for f in (*add,*delete)}
        if len(preds)!=1 or len(arities)!=1: return None
        arity=next(iter(arities))
        if arity<3: return None
        dels=list(delete); adds=list(add)
        for changed in range(1,arity):
            # All non-changing arguments form a unique row key.
            def key(f): return tuple(v for i,v in enumerate(f[1:],start=1) if i!=changed)
            dkeys=[key(f) for f in dels]; akeys=[key(f) for f in adds]
            if len(set(dkeys))!=len(dels) or set(dkeys)!=set(akeys): continue
            by_key={key(f):f for f in adds}
            source_values=[f[changed] for f in dels]
            if len(set(source_values))!=len(source_values): continue
            out_values=[by_key[key(f)][changed] for f in dels]
            if set(out_values)!=set(source_values): continue
            index={v:i for i,v in enumerate(source_values)}
            perm=tuple(index[v] for v in out_values)
            if perm==tuple(range(len(perm))): continue
            return perm
        return None

    def _fit_by_cross_modal_permutation(self, pattern: str) -> dict | None:
        """Use a learned cross-representation permutation as a conservative prior.

        The prior can lower target positive support from three to two, but never
        supplies target predicates or preconditions.  Preconditions must still be
        uniquely identified by contrastive target failures.  Thus the prior says
        only "this effect topology has been useful before", not "this action means
        X".
        """
        session=self.sessions[pattern]
        successes=[o for o in session['observations'] if o['success']]
        failures=[o for o in session['observations'] if not o['success']]
        if len(successes)<2 or not failures: return None
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:return None
        add=tuple(tuple(x) for x in successes[0]['add']); delete=tuple(tuple(x) for x in successes[0]['delete'])
        perm=self._effect_permutation_signature(add,delete)
        if perm is None:return None
        key=self._permutation_key(perm); prior=self.external_permutation_schemas.get(key)
        if not prior:return None
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]:common &= set(tuple(x) for x in o['before'])
        # Delete effects are safe mandatory preconditions: every successful target
        # episode proves those facts existed immediately before the transition.
        # Contrastive failures only need to identify *additional* context.
        mandatory=set(delete)
        context_candidates=common-mandatory
        residual_failures=[]
        for o in failures:
            fail=set(tuple(x) for x in o['before'])
            if mandatory.issubset(fail):
                residual_failures.append(fail-mandatory)
        if residual_failures:
            extra,mode=self._minimal_hitting_set(context_candidates,residual_failures,self.max_precondition_candidates)
            if extra is None or mode!='contrastive_unique':return None
        else:
            extra=set();mode='mandatory_delete_contrast'
        pre=mandatory|set(extra)
        if not pre:return None
        session.update({'promoted':True,'status':'operator_learned',
                        'preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                        'add':[list(x) for x in sorted(add,key=_template_sort_key)],
                        'delete':[list(x) for x in sorted(delete,key=_template_sort_key)],
                        'support':len(successes),'failures':len(failures),
                        'precondition_mode':'cross_modal_permutation_transfer',
                        'cross_modal_schema':key,
                        'cross_modal_sources':sorted(prior.get('sources',{}))})
        self._mark_unclustered(pattern)
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':session['preconditions'],'add':session['add'],'delete':session['delete'],
                'precondition_mode':'cross_modal_permutation_transfer','cross_modal_schema':key,
                'cross_modal_sources':session['cross_modal_sources']}

    def _operator_for_pattern(self, pattern: str) -> dict | None:
        state=self.sessions.get(pattern)
        if not state or not state.get('promoted'):
            return None
        return {'pattern':pattern,
                'preconditions':tuple(tuple(x) for x in state.get('preconditions',())),
                'add':tuple(tuple(x) for x in state.get('add',())),
                'delete':tuple(tuple(x) for x in state.get('delete',())),
                'support':state.get('support',0),'failures':state.get('failures',0),
                'precondition_mode':state.get('precondition_mode'),
                'analogy_sources':tuple(state.get('analogy_sources',())),
                'analogy_schema_id':state.get('analogy_schema_id')}

    def _mark_unclustered(self, pattern: str) -> None:
        if pattern not in self.analogy_schema_by_pattern and self._operator_for_pattern(pattern) is not None:
            self.analogy_unclustered.add(pattern)

    def _drop_from_analogy_indexes(self, pattern: str) -> None:
        self.analogy_unclustered.discard(pattern)
        sid=self.analogy_schema_by_pattern.pop(pattern,None)
        if sid is None:return
        schema=self.analogy_schemas.get(sid)
        if not schema:return
        members=[p for p in schema.get('members',[]) if p!=pattern and self._operator_for_pattern(p) is not None]
        if len(members)<2:
            self.analogy_schemas.pop(sid,None)
            for p in members:
                self.analogy_schema_by_pattern.pop(p,None);self.analogy_unclustered.add(p)
            return
        schema['members']=sorted(members);schema['representative']=schema['members'][0];schema['support']=len(members)

    def _analogy_source_representatives(self) -> list[dict]:
        """Return one live representative per learned meta-schema plus unclustered operators.

        The bookkeeping is incremental, so the steady-state cost depends on the
        number of distinct structural schemas, not on every historical operator.
        """
        out=[]
        for sid,schema in sorted(self.analogy_schemas.items()):
            members=schema.get('members',[])
            rep=schema.get('representative')
            op=self._operator_for_pattern(rep) if rep else None
            if op is None:
                live=[p for p in members if self._operator_for_pattern(p) is not None]
                if len(live)<2:continue
                rep=live[0];schema['representative']=rep;schema['members']=live;schema['support']=len(live);op=self._operator_for_pattern(rep)
            evidence=members[:2] if len(members)>=2 else members
            out.append({'operator':op,'evidence_members':evidence,'support_count':int(schema.get('support',len(members))),
                        'schema_id':sid})
        stale=[]
        for pattern in sorted(self.analogy_unclustered):
            op=self._operator_for_pattern(pattern)
            if op is None:stale.append(pattern);continue
            out.append({'operator':op,'evidence_members':[pattern],'support_count':1,'schema_id':None})
        for pattern in stale:self.analogy_unclustered.discard(pattern)
        return out

    def _register_analogy_schema(self, source_patterns: Iterable[str], target_pattern: str) -> str:
        sources=list(dict.fromkeys(source_patterns));matching=[]
        for pattern in sources:
            sid=self.analogy_schema_by_pattern.get(pattern)
            if sid and sid not in matching:matching.append(sid)
        if matching:
            sid=matching[0];schema=self.analogy_schemas[sid]
            # The common path is incremental: one established schema gains one
            # new operator.  No full member scan/sort is needed.
            if len(matching)==1:
                if target_pattern not in self.analogy_schema_by_pattern:
                    schema.setdefault('members',[]).append(target_pattern)
                    schema['support']=int(schema.get('support',len(schema['members'])-1))+1
                members=schema['members']
            else:
                merged=[];seen=set()
                for old in matching:
                    for pattern in self.analogy_schemas.get(old,{}).get('members',[]):
                        if pattern not in seen:seen.add(pattern);merged.append(pattern)
                for pattern in [*sources,target_pattern]:
                    if pattern not in seen:seen.add(pattern);merged.append(pattern)
                for old in matching[1:]:self.analogy_schemas.pop(old,None)
                schema={'id':sid,'members':merged,'representative':merged[0],'support':len(merged)}
                self.analogy_schemas[sid]=schema;members=merged
        else:
            members=[];seen=set()
            for pattern in [*sources,target_pattern]:
                if pattern not in seen:seen.add(pattern);members.append(pattern)
            seed='|'.join(sorted(members));sid='schema:'+hashlib.blake2b(seed.encode('utf8'),digest_size=8).hexdigest()
            schema={'id':sid,'members':members,'representative':members[0],'support':len(members)}
            self.analogy_schemas[sid]=schema
        for pattern in members:
            # Existing members already have the mapping; avoid rewriting their
            # sessions on every incremental addition.
            if self.analogy_schema_by_pattern.get(pattern)==sid:continue
            self.analogy_schema_by_pattern[pattern]=sid;self.analogy_unclustered.discard(pattern)
            state=self.sessions.get(pattern)
            if state is not None:state['analogy_schema_id']=sid
        return sid

    def structural_schemas(self) -> list[dict]:
        out=[]
        for sid,schema in sorted(self.analogy_schemas.items()):
            members=[p for p in schema.get('members',[]) if self._operator_for_pattern(p) is not None]
            if len(members)>=2:
                out.append({'id':sid,'representative':schema.get('representative'),'members':tuple(members),'support':len(members)})
        return out

    def _fit_by_structural_analogy(self, pattern: str) -> dict | None:
        """Transfer an already learned operator topology to a new domain.

        This is a bounded, conservative meta-transfer experiment.  It needs two
        independent successful target episodes with consistent effects.  Existing
        operators provide only *structural* guidance: predicate names may be
        completely different.  Context preconditions are accepted only when the
        target successes contain a unique fact with the corresponding role shape.
        Observed failures must violate at least one transferred precondition.

        The method deliberately refuses ambiguous analogies instead of selecting
        the first source operator.  A later counterexample automatically removes
        the promotion because every observation re-runs this validation.
        """
        session=self.sessions[pattern]
        successes=[o for o in session['observations'] if o['success']]
        failures=[o for o in session['observations'] if not o['success']]
        if not successes:return None
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:return None
        target_add=tuple(tuple(x) for x in successes[0]['add'])
        target_delete=tuple(tuple(x) for x in successes[0]['delete'])
        if not target_add and not target_delete:return None
        target_markers=sorted({a for f in (*target_add,*target_delete) for a in f[1:] if _MARKER_RE.fullmatch(a)})
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]:common &= set(tuple(x) for x in o['before'])
        failure_sets=[set(tuple(x) for x in o['before']) for o in failures]
        proposals={}
        for source_entry in self._analogy_source_representatives():
            source=source_entry['operator']
            if source.get('pattern')==pattern:continue
            source_markers=self._markers_in_operator(source)
            # Every role must be visible in target effects; otherwise the analogy
            # would need to invent an ungrounded hidden argument.
            if len(source_markers)!=len(target_markers):continue
            if any(m not in {a for f in (*source.get('add',()),*source.get('delete',())) for a in f[1:]}
                   for m in source_markers):
                continue
            for perm in permutations(target_markers):
                mmap=dict(zip(source_markers,perm))
                pmap=self._effect_alignment(source,target_add,target_delete,mmap)
                if pmap is None:continue
                # Same-predicate effects are ordinary language aliases; keep the
                # older evidence-intersection mechanism authoritative for those.
                if pmap and all(sp==tp for sp,tp in pmap.items()):continue
                mapped_pre=[];local_pmap=dict(pmap);reverse={v:k for k,v in local_pmap.items()};valid=True
                for src_pre in source.get('preconditions',()):
                    src_pre=tuple(src_pre); mapped_args=self._map_template_markers(src_pre,mmap)[1:]
                    sp=src_pre[0]
                    if sp in local_pmap:
                        candidate=(local_pmap[sp],*mapped_args)
                        if candidate not in common:valid=False;break
                    else:
                        candidates=[f for f in common if len(f)==len(src_pre) and f[1:]==mapped_args]
                        # Exclude predicates already structurally assigned to a
                        # different source predicate.
                        candidates=[f for f in candidates if f[0] not in reverse or reverse[f[0]]==sp]
                        preds=sorted({f[0] for f in candidates})
                        if len(preds)!=1:valid=False;break
                        tp=preds[0];local_pmap[sp]=tp;reverse[tp]=sp;candidate=(tp,*mapped_args)
                    mapped_pre.append(candidate)
                if not valid:continue
                pre=frozenset(mapped_pre)
                if not pre:continue
                # A recorded failure that satisfies all transferred preconditions
                # refutes this analogy.
                if any(pre.issubset(fail) for fail in failure_sets):continue
                key=json.dumps({'pre':[list(x) for x in sorted(pre,key=_template_sort_key)],
                                'add':[list(x) for x in sorted(target_add,key=_template_sort_key)],
                                'delete':[list(x) for x in sorted(target_delete,key=_template_sort_key)]},
                               sort_keys=True,separators=(',',':'))
                proposals.setdefault(key,{'pre':pre,'sources':set(),'source_support':0,'source_entries':set(),'marker_maps':[],'predicate_maps':[]})
                entry_id=source_entry.get('schema_id') or ('operator:'+source['pattern'])
                if entry_id not in proposals[key]['source_entries']:
                    proposals[key]['source_entries'].add(entry_id)
                    proposals[key]['source_support']+=int(source_entry.get('support_count',1))
                    proposals[key]['sources'].update(source_entry.get('evidence_members',[source['pattern']]))
                proposals[key]['marker_maps'].append(dict(mmap));proposals[key]['predicate_maps'].append(dict(local_pmap))
        if len(proposals)!=1:return None
        proposal=next(iter(proposals.values()));pre=proposal['pre']
        sources=sorted(proposal['sources']);source_support=int(proposal.get('source_support',len(sources)))
        # One target success is accepted only after the same structural schema
        # has independently survived in at least two learned source operators.
        # With a single source schema we still require two target successes.
        if len(successes)<2 and source_support<2:
            return None
        session.update({'promoted':True,'status':'operator_learned','preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                        'add':[list(x) for x in sorted(target_add,key=_template_sort_key)],
                        'delete':[list(x) for x in sorted(target_delete,key=_template_sort_key)],
                        'support':len(successes),'failures':len(failures),'precondition_mode':'analogical_transfer',
                        'analogy_sources':sources})
        schema_id=self._register_analogy_schema(sources,pattern)
        session['analogy_schema_id']=schema_id
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':session['preconditions'],'add':session['add'],'delete':session['delete'],
                'precondition_mode':'analogical_transfer','analogy_sources':sources,
                'analogy_source_count':source_support,'analogy_alternatives':1,'analogy_schema_id':schema_id}

    def _fit(self, pattern: str) -> dict:
        s=self.sessions[pattern]
        successes=[o for o in s['observations'] if o['success']]
        failures=[o for o in s['observations'] if not o['success']]
        if len(successes)<self.min_support:
            s.update({'promoted':False,'status':'pending_support'})
            return {'status':'pending_support','support':len(successes),'required':self.min_support,'pattern':pattern}
        effect_keys={(tuple(map(tuple,o['add'])),tuple(map(tuple,o['delete']))) for o in successes}
        if len(effect_keys)!=1:
            s.update({'promoted':False,'status':'inconsistent_effects'})
            return {'status':'inconsistent_effects','pattern':pattern,'effect_variants':len(effect_keys)}
        add=tuple(tuple(x) for x in successes[0]['add']); delete=tuple(tuple(x) for x in successes[0]['delete'])
        if not add and not delete:
            s.update({'promoted':False,'status':'no_effect'})
            return {'status':'no_effect','pattern':pattern}
        common=set(tuple(x) for x in successes[0]['before'])
        for o in successes[1:]: common &= set(tuple(x) for x in o['before'])
        pre,mode=self._minimal_hitting_set(common,[set(tuple(x) for x in o['before']) for o in failures],self.max_precondition_candidates)
        if pre is None:
            s.update({'promoted':False,'status':mode,'candidate_preconditions':[list(x) for x in sorted(common,key=_template_sort_key)]})
            return {'status':mode,'pattern':pattern,'support':len(successes),'failures':len(failures)}
        s.update({'promoted':True,'status':'operator_learned','preconditions':[list(x) for x in sorted(pre,key=_template_sort_key)],
                  'add':[list(x) for x in sorted(add,key=_template_sort_key)],
                  'delete':[list(x) for x in sorted(delete,key=_template_sort_key)],
                  'support':len(successes),'failures':len(failures),'precondition_mode':mode})
        self._mark_unclustered(pattern)
        return {'status':'operator_learned','pattern':pattern,'support':len(successes),'failures':len(failures),
                'preconditions':s['preconditions'],'add':s['add'],'delete':s['delete'],'precondition_mode':mode}

    @staticmethod
    def _markers_in_operator(op: dict) -> list[str]:
        return sorted({a for t in (*op['preconditions'],*op['add'],*op['delete']) for a in t[1:] if _MARKER_RE.fullmatch(a)})

    def _alias_candidates(self, pattern: str, mapping: dict[str,str], before: frozenset[Fact], after: frozenset[Fact]):
        alias_values={marker:entity for entity,marker in mapping.items()}
        alias_markers=sorted(alias_values)
        candidates={}
        for op in self.operators():
            if op['pattern']==pattern:continue
            op_markers=self._markers_in_operator(op)
            if len(op_markers)!=len(alias_markers):continue
            for alias_perm in permutations(alias_markers):
                op_binding={op_marker:alias_values[alias_marker] for op_marker,alias_marker in zip(op_markers,alias_perm)}
                nxt=self._apply_operator(before,op,op_binding)
                if nxt!=after:continue
                alias_to_op={alias_marker:op_marker for op_marker,alias_marker in zip(op_markers,alias_perm)}
                detail={'operator_pattern':op['pattern'],'alias_to_operator':alias_to_op}
                key=json.dumps(detail,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                candidates[key]=detail
        return candidates

    def _record_alias(self, pattern: str, mapping: dict[str,str], before: frozenset[Fact], after: frozenset[Fact], episode_id: str) -> dict | None:
        if before==after:return None
        current=self._alias_candidates(pattern,mapping,before,after)
        if not current:
            state=self.alias_sessions.get(pattern)
            if state and state.get('promoted'):
                state['possible']=[];state['promoted']=False;state['status']='alias_withdrawn_by_counterevidence'
                return {'status':'alias_withdrawn_by_counterevidence','pattern':pattern}
            return None
        state=self.alias_sessions.setdefault(pattern,{'possible':sorted(current),'observations':[],'promoted':False})
        if any(o['episode_id']==episode_id for o in state['observations']):
            return {'status':'duplicate_alias_episode','pattern':pattern,'support':len(state['observations'])}
        previous=set(state.get('possible',[]));now=set(current)
        possible=now if not state['observations'] else previous & now
        state['observations'].append({'episode_id':episode_id,'candidates':sorted(now)})
        state['possible']=sorted(possible)
        if not possible:
            state['promoted']=False;state['status']='alias_conflict'
            return {'status':'alias_conflict','pattern':pattern,'support':len(state['observations'])}
        if len(possible)==1 and len(state['observations'])>=self.alias_min_support:
            winner=next(iter(possible));state['promoted']=True;state['status']='alias_learned';state['winner']=json.loads(winner)
            return {'status':'alias_learned','pattern':pattern,'support':len(state['observations']),**state['winner']}
        state['status']='alias_pending'
        return {'status':'alias_pending','pattern':pattern,'support':len(state['observations']),
                'required':self.alias_min_support,'alternatives':len(possible)}

    def aliases(self) -> list[dict]:
        out=[]
        for pattern,state in sorted(self.alias_sessions.items()):
            if state.get('promoted') and state.get('winner'):
                out.append({'pattern':pattern,**deepcopy(state['winner']),'support':len(state.get('observations',[]))})
        return out

    def _meta_representation_features(self, pattern: str) -> tuple[float, ...]:
        """Domain-neutral structural signature shared with ProcedureGrounder."""
        session=self.sessions.get(pattern,{})
        obs=list(session.get('observations',()))
        successes=[o for o in obs if o.get('success')]
        failures=[o for o in obs if not o.get('success')]
        n=max(1,self._pattern_role_count(pattern))
        effect=0
        if successes:
            effect=len(successes[0].get('add',()))+len(successes[0].get('delete',()))
        rs=sum(1 for row in self.external_role_sets.values() if int(row.get('input_arity',0))==n)
        card=sum(1 for row in self.external_role_cardinalities.values() if 0<int(row.get('cardinality',0))<n)
        proj=(sum(1 for row in self.external_projection_schemas.values() if int(row.get('input_arity',0))==n)
              +sum(1 for row in self.external_permutation_schemas.values() if len(row.get('perm',()))==n))
        topo=sum(1 for row in self.external_role_topologies.values() if int(row.get('input_arity',0))==n)
        total=max(1,len(obs))
        return (min(n,8)/8.0,min(len(successes),8)/8.0,min(len(failures)/total,1.0),
                min(effect,8)/8.0,min(rs,8)/8.0,min(card,8)/8.0,
                min(proj,8)/8.0,min(topo,8)/8.0)

    def _meta_representation_order(self, pattern: str, strategies) -> tuple[list[str], dict]:
        default=list(strategies)
        if self.meta_controller is None:
            return default,{'used':False,'mode':'disabled','order':default}
        route=self.meta_controller.rank('representation',self._meta_representation_features(pattern),default)
        return list(route.get('order',default)),route

    def _record_meta_representation(self, pattern: str, strategy: str, success: bool, cost: float = 1.0) -> None:
        if self.meta_controller is None:
            return
        self.meta_controller.observe('representation',self._meta_representation_features(pattern),strategy,
                                     success=bool(success),cost=max(0.001,float(cost)),failure_budget=2.0)

    def _meta_evidence_request(self, pattern: str) -> dict:
        session=self.sessions.get(pattern,{})
        obs=list(session.get('observations',()))
        successes=[o for o in obs if o.get('success')]
        failures=[o for o in obs if not o.get('success')]
        if len(successes)<2:
            return {'kind':'independent_success','reason':'need_effect_invariance',
                    'message':'Observe otra ejecución exitosa independiente con entidades distintas.'}
        if not failures:
            return {'kind':'contrastive_failure','reason':'need_precondition_discrimination',
                    'message':'Observe un intento comparable que no produzca el efecto para discriminar precondiciones.'}
        return {'kind':'controlled_intervention','reason':'known_representations_unresolved',
                'message':'Varíe un solo hecho o rol contextual por vez y observe si el efecto cambia.'}

    def observe(self, text: str, before, after) -> dict:
        b,a=_canon_state(before),_canon_state(after)
        encoded=self._encode_episode(text,b,a)
        if encoded is None:
            result={'status':'ungrounded_transition','reason':'changed entities must be explicitly mentioned'}
            self.audit.append({'event':'observe','text':text,**result});return result
        pattern,mapping,before_t,add_t,del_t=encoded
        eid=self._episode_id(text,b,a)
        session=self.sessions.setdefault(pattern,{'observations':[],'promoted':False})
        was_promoted=bool(session.get('promoted'))
        if any(o['episode_id']==eid for o in session['observations']):
            return {'status':'duplicate_episode','pattern':pattern,'support':sum(o['success'] for o in session['observations'])}
        success=b!=a
        obs={'episode_id':eid,'success':success,'before':[list(x) for x in sorted(before_t,key=_template_sort_key)],
             'add':[list(x) for x in sorted(add_t,key=_template_sort_key)],
             'delete':[list(x) for x in sorted(del_t,key=_template_sort_key)]}
        session['observations'].append(obs)
        report=self._fit(pattern)
        meta_route={'used':False,'mode':'direct_fit_succeeded' if report.get('status')=='operator_learned' else 'unavailable'}
        meta_attempts=[]
        if report.get('status')!='operator_learned':
            strategy_fns={
                'structural_analogy':self._fit_by_structural_analogy,
                'projection':self._fit_by_cross_modal_projection,
                'permutation':self._fit_by_cross_modal_permutation,
                'role_set':self._fit_by_meta_role_set,
                'role_topology':self._fit_by_meta_role_topology,
                'role_cardinality':self._fit_by_meta_role_cardinality,
            }
            default=['structural_analogy','projection','permutation','role_set','role_topology','role_cardinality']
            order,meta_route=self._meta_representation_order(pattern,default)
            for strategy in order:
                fn=strategy_fns[strategy]
                trial=fn(pattern)
                learned=bool(trial is not None and trial.get('status')=='operator_learned')
                self._record_meta_representation(pattern,strategy,learned)
                meta_attempts.append({'strategy':strategy,'learned':learned})
                if learned:
                    report=trial
                    break
        if meta_attempts:
            report={**report,'meta_controller_route':meta_route,
                    'meta_controller_representation_attempts':meta_attempts,
                    'meta_controller_representation_strategy':next((x['strategy'] for x in meta_attempts if x['learned']),None)}
        alias_report=None
        if report.get('status')!='operator_learned':
            alias_report=self._record_alias(pattern,mapping,b,a,eid)
        chosen=alias_report if alias_report is not None else report
        if (self.meta_controller is not None and chosen.get('status') not in ('operator_learned','alias_learned')
                and meta_attempts):
            gap=self.meta_controller.record_gap(
                'representation',self._meta_representation_features(pattern),meta_attempts,
                reason='known_representation_strategies_unresolved',
                evidence_request=self._meta_evidence_request(pattern))
            chosen={**chosen,'meta_controller_gap':gap,
                    'meta_controller_route':meta_route,
                    'meta_controller_representation_attempts':meta_attempts}
        if was_promoted and not session.get('promoted'):
            self._drop_from_analogy_indexes(pattern)
        self.audit.append({'event':'observe','text':text,'pattern':pattern,'success':success,'report':deepcopy(chosen)})
        return chosen

    def operators(self) -> list[dict]:
        out=[]
        for pattern,s in sorted(self.sessions.items()):
            if s.get('promoted'):
                out.append({'pattern':pattern,
                            'preconditions':tuple(tuple(x) for x in s['preconditions']),
                            'add':tuple(tuple(x) for x in s['add']),
                            'delete':tuple(tuple(x) for x in s['delete']),
                            'support':s.get('support',0),'failures':s.get('failures',0),
                            'precondition_mode':s.get('precondition_mode'),
                            'analogy_sources':tuple(s.get('analogy_sources',())),
                            'analogy_schema_id':s.get('analogy_schema_id'),
                            'cross_modal_schema':s.get('cross_modal_schema'),
                            'cross_modal_sources':tuple(s.get('cross_modal_sources',()))})
        return out


    @staticmethod
    def _operator_fingerprint(op: dict) -> str:
        payload={'pattern':op['pattern'],
                 'preconditions':[list(x) for x in op['preconditions']],
                 'add':[list(x) for x in op['add']],
                 'delete':[list(x) for x in op['delete']]}
        raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return hashlib.blake2b(raw.encode('utf8'),digest_size=16).hexdigest()

    @staticmethod
    def _abstract_plan_steps(steps: list[dict]):
        if len(steps)<2:
            return None
        value_to_marker={}; sequence=[]; role_values={}
        for step in steps:
            # Hierarchies are learned from verified primitive traces.  This avoids
            # recursively crediting a macro for evidence generated by itself.
            if step.get('kind')=='macro' or 'operator' not in step or 'binding' not in step:
                return None
            abstract={}
            for op_marker,value in sorted(step['binding'].items()):
                value=normalize(str(value))
                if value not in value_to_marker:
                    marker=f'<e{len(value_to_marker)}>'
                    value_to_marker[value]=marker;role_values[marker]=value
                abstract[op_marker]=value_to_marker[value]
            sequence.append({'operator':step['operator'],'map':abstract})
        signature=json.dumps(sequence,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        role_key=tuple(role_values[f'<e{i}>'] for i in range(len(role_values)))
        return signature,sequence,role_values,role_key

    @staticmethod
    def _macro_substitute(template: Iterable[str], marker_map: dict[str,str]) -> TemplateFact:
        out=[template[0]]
        for arg in template[1:]:
            out.append(marker_map.get(arg,arg))
        return tuple(out)

    def _compose_macro(self, signature: str, sequence: list[dict], support: int) -> dict | None:
        lookup={op['pattern']:op for op in self.operators()}
        required:set[TemplateFact]=set();net_add:set[TemplateFact]=set();net_delete:set[TemplateFact]=set()
        dependencies={}
        for step in sequence:
            op=lookup.get(step['operator'])
            if op is None:return None
            dependencies[op['pattern']]=self._operator_fingerprint(op)
            marker_map=step['map']
            pre={self._macro_substitute(t,marker_map) for t in op['preconditions']}
            adds={self._macro_substitute(t,marker_map) for t in op['add']}
            deletes={self._macro_substitute(t,marker_map) for t in op['delete']}
            for fact in pre:
                if fact not in net_add:required.add(fact)
            for fact in deletes:
                if fact in net_add:net_add.remove(fact)
                else:net_delete.add(fact)
            for fact in adds:
                if fact in net_delete:net_delete.remove(fact)
                else:net_add.add(fact)
        # Adding a fact already guaranteed by the initial precondition is not a
        # net effect.  Keeping only semantic changes reduces spurious bindings.
        net_add-=required
        if not net_add and not net_delete:return None
        macro_id='macro:'+hashlib.blake2b(signature.encode('utf8'),digest_size=8).hexdigest()
        return {'id':macro_id,'pattern':macro_id,
                'preconditions':tuple(sorted(required,key=_template_sort_key)),
                'add':tuple(sorted(net_add,key=_template_sort_key)),
                'delete':tuple(sorted(net_delete,key=_template_sort_key)),
                'sequence':deepcopy(sequence),'dependencies':dependencies,
                'support':support,'primitive_length':len(sequence)}

    def observe_plan(self, state, goal, plan_report: dict) -> dict:
        """Learn a parameterized macro only from a verified primitive solution trace."""
        start,target=_canon_state(state),_canon_state(goal)
        if plan_report.get('status')!='plan_found':return {'status':'macro_rejected','reason':'plan_not_found'}
        abstracted=self._abstract_plan_steps(list(plan_report.get('steps',[])))
        if abstracted is None:return {'status':'macro_rejected','reason':'requires_two_or_more_primitive_steps'}
        signature,sequence,role_values,role_key=abstracted
        lookup={op['pattern']:op for op in self.operators()}
        # Re-execute the supplied trace against the current model; plan metadata is
        # not trusted as proof that a sequence is valid.
        current=start
        for step in plan_report['steps']:
            op=lookup.get(step['operator'])
            if op is None:return {'status':'macro_rejected','reason':'unknown_dependency'}
            current=self._apply_operator(current,op,{str(k):normalize(str(v)) for k,v in step['binding'].items()})
            if current is None:return {'status':'macro_rejected','reason':'invalid_trace'}
        if not target.issubset(current):return {'status':'macro_rejected','reason':'trace_does_not_achieve_goal'}
        session=self.macro_sessions.setdefault(signature,{'sequence':deepcopy(sequence),'observations':[],'promoted':False})
        if any(tuple(o['role_key'])==role_key for o in session['observations']):
            return {'status':'duplicate_macro_episode','support':len(session['observations'])}
        session['observations'].append({'role_key':list(role_key),'roles':role_values})
        support=len(session['observations'])
        if support<self.macro_min_support:
            session.update({'promoted':False,'status':'macro_pending'})
            return {'status':'macro_pending','support':support,'required':self.macro_min_support,
                    'primitive_length':len(sequence)}
        macro=self._compose_macro(signature,sequence,support)
        if macro is None:
            session.update({'promoted':False,'status':'macro_uncomposable'})
            return {'status':'macro_uncomposable','support':support}
        session.update({'promoted':True,'status':'macro_learned','macro':deepcopy(macro)})
        self.audit.append({'event':'macro_learned','macro':macro['id'],'support':support,'primitive_length':len(sequence)})
        return {'status':'macro_learned','macro':macro['id'],'support':support,
                'primitive_length':len(sequence),'preconditions':[list(x) for x in macro['preconditions']],
                'add':[list(x) for x in macro['add']],'delete':[list(x) for x in macro['delete']]}

    def macros(self) -> list[dict]:
        current={op['pattern']:op for op in self.operators()};out=[]
        for session in self.macro_sessions.values():
            if not session.get('promoted') or not session.get('macro'):continue
            macro=session['macro'];valid=True
            for pattern,expected in macro.get('dependencies',{}).items():
                op=current.get(pattern)
                if op is None or self._operator_fingerprint(op)!=expected:
                    valid=False;break
            if not valid:
                session['promoted']=False;session['status']='macro_invalidated_dependency'
                continue
            out.append(deepcopy(macro))
        return sorted(out,key=lambda m:(-m.get('primitive_length',0),m['id']))

    @staticmethod
    def _transition_roles(op: dict):
        # Iterative closure is only promoted for a pure one-fact state transition.
        # This prevents silently ignoring side effects while repeating an action.
        if len(op.get('add',()))!=1 or len(op.get('delete',()))!=1:return None
        delete_t=tuple(op['delete'][0]);add_t=tuple(op['add'][0])
        if delete_t[0]!=add_t[0] or len(delete_t)!=len(add_t):return None
        diffs=[i for i in range(1,len(delete_t)) if delete_t[i]!=add_t[i]]
        if len(diffs)!=1:return None
        pos=diffs[0];src,dst=delete_t[pos],add_t[pos]
        if not (_MARKER_RE.fullmatch(src) and _MARKER_RE.fullmatch(dst)) or src==dst:return None
        for i in range(1,len(delete_t)):
            if i!=pos and delete_t[i]!=add_t[i]:return None
        markers=SymbolicWorldLearner._markers_in_operator(op)
        invariants=[m for m in markers if m not in (src,dst)]
        transition_markers={a for a in delete_t[1:] if _MARKER_RE.fullmatch(a)}
        # Invariant roles must be recoverable from the changing state fact itself;
        # otherwise execution would need an ungrounded hidden parameter.
        if any(m not in transition_markers for m in invariants):return None
        return {'delete':delete_t,'add':add_t,'source_marker':src,'destination_marker':dst,
                'invariant_markers':tuple(sorted(invariants))}

    def observe_iterative_plan(self, plan_report: dict) -> dict:
        """Induce a variable-length repeated-operator skill from a primitive trace."""
        if plan_report.get('status')!='plan_found':return {'status':'iteration_rejected','reason':'plan_not_found'}
        steps=list(plan_report.get('steps',[]))
        if len(steps)<2 or any(st.get('kind')=='macro' or 'operator' not in st for st in steps):
            return {'status':'iteration_rejected','reason':'requires_repeated_primitive_trace'}
        patterns={st['operator'] for st in steps}
        if len(patterns)!=1:return {'status':'iteration_rejected','reason':'operator_not_repeated'}
        pattern=next(iter(patterns));lookup={op['pattern']:op for op in self.operators()};op=lookup.get(pattern)
        if op is None:return {'status':'iteration_rejected','reason':'unknown_operator'}
        roles=self._transition_roles(op)
        if roles is None:return {'status':'iteration_rejected','reason':'operator_not_pure_chain_transition'}
        src,dst=roles['source_marker'],roles['destination_marker'];invariants=roles['invariant_markers']
        for left,right in zip(steps,steps[1:]):
            if left['binding'].get(dst)!=right['binding'].get(src):
                return {'status':'iteration_rejected','reason':'broken_chain_flow'}
        for marker in invariants:
            vals={st['binding'].get(marker) for st in steps}
            if None in vals or len(vals)!=1:return {'status':'iteration_rejected','reason':'noninvariant_role'}
        key=json.dumps({'operator':pattern,'source':src,'destination':dst},sort_keys=True,ensure_ascii=False,separators=(',',':'))
        concrete=tuple(tuple(sorted((k,normalize(str(v))) for k,v in st['binding'].items())) for st in steps)
        session=self.iterative_sessions.setdefault(key,{'observations':[],'promoted':False,'operator':pattern,'roles':roles})
        if any(tuple(tuple(tuple(x) for x in step) for step in o['concrete'])==concrete for o in session['observations']):
            return {'status':'duplicate_iteration_episode','support':len(session['observations']),'lengths':sorted({o['length'] for o in session['observations']})}
        session['observations'].append({'length':len(steps),'concrete':[[list(x) for x in step] for step in concrete]})
        support=len(session['observations']);lengths=sorted({o['length'] for o in session['observations']})
        if support<self.iterative_min_support or len(lengths)<2:
            session.update({'promoted':False,'status':'iteration_pending'})
            return {'status':'iteration_pending','support':support,'required':self.iterative_min_support,'lengths':lengths}
        raw=key;skill_id='iterate:'+hashlib.blake2b(raw.encode('utf8'),digest_size=8).hexdigest()
        skill={'id':skill_id,'operator_pattern':pattern,**deepcopy(roles),'support':support,'training_lengths':lengths,
               'dependency':self._operator_fingerprint(op)}
        session.update({'promoted':True,'status':'iteration_learned','skill':deepcopy(skill)})
        self.audit.append({'event':'iteration_learned','skill':skill_id,'support':support,'lengths':lengths})
        return {'status':'iteration_learned','skill':skill_id,'support':support,'lengths':lengths,
                'source_marker':src,'destination_marker':dst}

    def iterative_skills(self) -> list[dict]:
        lookup={op['pattern']:op for op in self.operators()};out=[]
        for session in self.iterative_sessions.values():
            if not session.get('promoted') or not session.get('skill'):continue
            skill=session['skill'];op=lookup.get(skill['operator_pattern'])
            if op is None or self._operator_fingerprint(op)!=skill.get('dependency'):
                session['promoted']=False;session['status']='iteration_invalidated_dependency';continue
            out.append(deepcopy(skill))
        return sorted(out,key=lambda x:x['id'])

    def _apply_macro_partitioned(self, dynamic: frozenset[Fact], static: frozenset[Fact], macro: dict,
                                 binding: dict[str,str], lookup: dict[str,dict]):
        current=dynamic;expanded=[]
        for spec in macro['sequence']:
            op=lookup.get(spec['operator'])
            if op is None:return None,None
            op_binding={op_marker:binding[macro_marker] for op_marker,macro_marker in spec['map'].items()
                        if macro_marker in binding}
            # Every role required by a step must have been grounded by the macro.
            if len(op_binding)!=len(spec['map']):return None,None
            nxt=self._apply_partitioned(current,static,op,op_binding)
            if nxt is None:return None,None
            expanded.append({'kind':'primitive','operator':op['pattern'],
                             'action':self._render_action(op['pattern'],op_binding),'binding':dict(op_binding),
                             'added':sorted(nxt-current),'removed':sorted(current-nxt)})
            current=nxt
        return current,expanded

    @staticmethod
    def _apply_operator(state: frozenset[Fact], op: dict, binding: dict[str,str]) -> frozenset[Fact] | None:
        pre=[]
        for t in op['preconditions']:
            f=_instantiate(tuple(t),binding)
            if f is None:return None
            pre.append(f)
        if not set(pre).issubset(state):return None
        deletes=[];adds=[]
        for t in op['delete']:
            f=_instantiate(tuple(t),binding)
            if f is None:return None
            deletes.append(f)
        for t in op['add']:
            f=_instantiate(tuple(t),binding)
            if f is None:return None
            adds.append(f)
        return frozenset((set(state)-set(deletes))|set(adds))

    def execute(self, text: str, state) -> dict:
        current=_canon_state(state); matches=[]
        operators={op['pattern']:op for op in self.operators()}
        for op in operators.values():
            binding=_binding_from_text(op['pattern'],text)
            if binding is None:continue
            nxt=self._apply_operator(current,op,binding)
            if nxt is not None:matches.append((op,binding,nxt,op['pattern']))
        for alias in self.aliases():
            alias_binding=_binding_from_text(alias['pattern'],text)
            if alias_binding is None:continue
            op=operators.get(alias['operator_pattern'])
            if op is None:continue
            mapping=alias['alias_to_operator']
            op_binding={op_marker:alias_binding[alias_marker] for alias_marker,op_marker in mapping.items() if alias_marker in alias_binding}
            nxt=self._apply_operator(current,op,op_binding)
            if nxt is not None:matches.append((op,op_binding,nxt,alias['pattern']))
        if not matches:
            return {'status':'unknown_or_inapplicable_action','result':current}
        distinct={m[2] for m in matches}
        if len(distinct)!=1:
            return {'status':'ambiguous_action','result':current,'alternatives':len(distinct)}
        op,binding,nxt,surface=matches[0]
        return {'status':'executed_symbolic_action','result':nxt,'operator':op['pattern'],'surface':surface,'binding':binding,
                'added':sorted(nxt-current),'removed':sorted(current-nxt)}

    @staticmethod
    def _unify_template(template: TemplateFact, fact: Fact, binding: dict[str,str]) -> dict[str,str] | None:
        if template[0]!=fact[0] or len(template)!=len(fact):return None
        out=dict(binding)
        for want,actual in zip(template[1:],fact[1:]):
            if _MARKER_RE.fullmatch(want):
                known=out.get(want)
                if known is not None and known!=actual:return None
                out[want]=actual
            elif want!=actual:return None
        return out

    def _bindings(self, op: dict, state: frozenset[Fact], goal: frozenset[Fact], by_sig=None, arg_index=None, seed_bindings=None):
        if by_sig is None:
            by_sig=defaultdict(list)
            for fact in state:by_sig[(fact[0],len(fact))].append(fact)
        if arg_index is None:arg_index={}

        def indexed_candidates(template: TemplateFact, binding: dict[str,str]):
            sig=(template[0],len(template));base=by_sig.get(sig,())
            constraints=[]
            for pos,want in enumerate(template[1:],start=1):
                if _MARKER_RE.fullmatch(want):
                    value=binding.get(want)
                    if value is not None:constraints.append((pos,value))
                else:constraints.append((pos,want))
            if not constraints:return base
            # Build a positional hash index lazily once per predicate/ariety for
            # this search node.  This turns relational joins with many irrelevant
            # facts from repeated full scans into indexed probes.
            if sig not in arg_index:
                idx=defaultdict(list)
                for fact in base:
                    for pos,value in enumerate(fact[1:],start=1):idx[(pos,value)].append(fact)
                arg_index[sig]=idx
            idx=arg_index[sig]
            pools=[idx.get((pos,value),()) for pos,value in constraints]
            if any(not pool for pool in pools):return ()
            candidates=min(pools,key=len)
            return [fact for fact in candidates if all(fact[pos]==value for pos,value in constraints)]

        bindings=[dict(b) for b in seed_bindings] if seed_bindings else [{}]
        remaining=[tuple(t) for t in op['preconditions']]
        # Re-plan the join after each binding expansion.  A predicate with a large
        # global table can become the most selective one once one of its role
        # variables is bound; using only global cardinality caused quadratic scans.
        while remaining:
            def score(template):
                total=0
                for b in bindings:
                    total+=len(indexed_candidates(template,b))
                    if total>self.max_action_bindings:return total
                return total
            template=min(remaining,key=lambda t:(score(t),_template_sort_key(t)))
            remaining.remove(template);nxt=[]
            for b in bindings:
                for fact in indexed_candidates(template,b):
                    u=self._unify_template(template,fact,b)
                    if u is not None:nxt.append(u)
                    if len(nxt)>=self.max_action_bindings:break
                if len(nxt)>=self.max_action_bindings:break
            bindings=nxt
            if not bindings:return []
        markers=sorted({a for t in (*op['preconditions'],*op['add'],*op['delete']) for a in t[1:] if _MARKER_RE.fullmatch(a)})
        expanded=[]; entities=None
        for b in bindings or [{}]:
            missing=[m for m in markers if m not in b]
            if not missing:
                expanded.append(b);continue
            if entities is None:entities=sorted(_entities(state|goal))
            for vals in product(entities,repeat=len(missing)):
                if len(set(vals))<len(vals):continue
                nb=dict(b);nb.update(zip(missing,vals));expanded.append(nb)
                if len(expanded)>=self.max_action_bindings:return expanded
        return expanded

    def _goal_seed_bindings(self, model: dict, unsatisfied_goal: frozenset[Fact]) -> list[dict[str,str]]:
        """Bind action/macro roles backwards from desired effects.

        This is an explicit symbolic relevance heuristic, not a neural attention
        mechanism.  Only facts an action can add are unified against currently
        unsatisfied goals; duplicates are removed deterministically.
        """
        out={}
        for template in model.get('add',()):
            t=tuple(template)
            for fact in unsatisfied_goal:
                b=self._unify_template(t,fact,{})
                if b is None:continue
                key=json.dumps(b,sort_keys=True,ensure_ascii=False,separators=(',',':'))
                out[key]=b
        return list(out.values())

    def _bindings_fact_index(self, model: dict, index: _MutableFactIndex, goal: frozenset[Fact], seed_bindings=None):
        bindings=[dict(b) for b in seed_bindings] if seed_bindings else [{}];remaining=[tuple(t) for t in model['preconditions']]
        while remaining:
            def score(template):
                total=0
                for binding in bindings:
                    total+=len(index.candidates(template,binding))
                    if total>self.max_action_bindings:return total
                return total
            template=min(remaining,key=lambda t:(score(t),_template_sort_key(t)))
            remaining.remove(template);nxt=[]
            for binding in bindings:
                for fact in index.candidates(template,binding):
                    u=self._unify_template(template,fact,binding)
                    if u is not None:nxt.append(u)
                    if len(nxt)>=self.max_action_bindings:break
                if len(nxt)>=self.max_action_bindings:break
            bindings=nxt
            if not bindings:return []
        markers=sorted({a for t in (*model['preconditions'],*model['add'],*model['delete'])
                        for a in t[1:] if _MARKER_RE.fullmatch(a)})
        expanded=[]
        for binding in bindings or [{}]:
            missing=[m for m in markers if m not in binding]
            if not missing:expanded.append(binding);continue
            entities=sorted(index.entities|_entities(goal))
            for vals in product(entities,repeat=len(missing)):
                if len(set(vals))<len(vals):continue
                nb=dict(binding);nb.update(zip(missing,vals));expanded.append(nb)
                if len(expanded)>=self.max_action_bindings:return expanded
        return expanded

    def _execute_macro_indexed(self, index: _MutableFactIndex, macro: dict, binding: dict[str,str], lookup: dict[str,dict]):
        expanded=[]
        for spec in macro['sequence']:
            op=lookup.get(spec['operator'])
            if op is None:return None
            op_binding={op_marker:binding[macro_marker] for op_marker,macro_marker in spec['map'].items()
                        if macro_marker in binding}
            if len(op_binding)!=len(spec['map']):return None
            pre=[]
            for t in op['preconditions']:
                f=_instantiate(tuple(t),op_binding)
                if f is None or f not in index.facts:return None
                pre.append(f)
            deletes=[];adds=[]
            for t in op['delete']:
                f=_instantiate(tuple(t),op_binding)
                if f is None:return None
                deletes.append(f)
            for t in op['add']:
                f=_instantiate(tuple(t),op_binding)
                if f is None:return None
                adds.append(f)
            actually_removed=[f for f in deletes if f in index.facts]
            actually_added=[f for f in adds if f not in index.facts]
            for f in deletes:index.remove(f)
            for f in adds:index.add(f)
            expanded.append({'kind':'primitive','operator':op['pattern'],
                             'action':self._render_action(op['pattern'],op_binding),'binding':dict(op_binding),
                             'added':sorted(actually_added),'removed':sorted(actually_removed)})
        return expanded

    def _try_hierarchical_rollout(self, start: frozenset[Fact], target: frozenset[Fact], macros: list[dict],
                                  max_steps: int, ops: list[dict]):
        """Fast exact rollout for unambiguous monotonic subgoal progress.

        It is deliberately conservative: a macro must add at least one currently
        unsatisfied final-goal fact, must not remove a satisfied goal fact, and the
        best resulting effect set must be unique.  Any ambiguity returns ``None``
        so the complete explicit planner remains the fallback.
        """
        if not macros or max_steps<=0:return None
        index=_MutableFactIndex(start);lookup={op['pattern']:op for op in ops};path=[];transitions=0
        target_set=set(target);unsatisfied=target_set-index.facts
        for _ in range(max_steps):
            if not unsatisfied:break
            candidates={}
            for macro in macros:
                for binding in self._bindings_fact_index(macro,index,target):
                    transitions+=1
                    adds=[];deletes=[];valid=True
                    for t in macro['add']:
                        f=_instantiate(tuple(t),binding)
                        if f is None:valid=False;break
                        adds.append(f)
                    if not valid:continue
                    for t in macro['delete']:
                        f=_instantiate(tuple(t),binding)
                        if f is None:valid=False;break
                        deletes.append(f)
                    if not valid:continue
                    gain=tuple(sorted(f for f in adds if f in unsatisfied))
                    if not gain:continue
                    # A satisfied goal is exactly a target fact no longer present
                    # in ``unsatisfied``.  Avoid rebuilding the whole satisfied set.
                    if any(f in target_set and f not in unsatisfied for f in deletes):continue
                    key=(len(gain),tuple(sorted(adds)),tuple(sorted(deletes)))
                    candidates[(macro['id'],json.dumps(binding,sort_keys=True,ensure_ascii=False))]=(key,macro,binding,adds,deletes)
            if not candidates:return None
            best_score=max(v[0][0] for v in candidates.values())
            best=[v for v in candidates.values() if v[0][0]==best_score]
            distinct_effects={(v[0][1],v[0][2]) for v in best}
            if len(distinct_effects)!=1:return None
            _,macro,binding,adds,deletes=best[0]
            before_changes={f for f in (*adds,*deletes) if f in index.facts}
            expanded=self._execute_macro_indexed(index,macro,binding,lookup)
            if expanded is None:return None
            previous=len(unsatisfied)
            for f in deletes:
                if f in target_set:unsatisfied.add(f)
            for f in adds:
                if f in target_set and f in index.facts:unsatisfied.discard(f)
            if len(unsatisfied)>=previous:return None
            # Net changes are derived from macro effects, avoiding a full-state copy.
            added=sorted(f for f in adds if f in index.facts and f not in before_changes)
            removed=sorted(f for f in deletes if f not in index.facts and f in before_changes)
            path.append({'kind':'macro','operator':macro['id'],'action':macro['id'],'binding':dict(binding),
                         'added':added,'removed':removed,'expanded_steps':expanded,
                         'primitive_length':macro['primitive_length']})
        if unsatisfied:return None
        primitive_steps=sum(st.get('primitive_length',1) for st in path)
        return {'status':'plan_found','result':frozenset(index.facts),'steps':path,'nodes':len(path),
                'transitions':transitions,'operators':len(ops),'macros':len(macros),
                'hierarchical_steps':len(path),'primitive_steps':primitive_steps,'macro_steps':len(path),
                'strategy':'hierarchical_rollout'}

    def _try_iterative_direct(self, start: frozenset[Fact], target: frozenset[Fact], skills: list[dict],
                              ops: list[dict], max_internal_steps: int = 10_000,
                              max_internal_nodes: int = 50_000):
        if not skills:return None
        lookup={op['pattern']:op for op in ops};index=_MutableFactIndex(start);solutions=[]
        for skill in skills:
            op=lookup.get(skill['operator_pattern'])
            if op is None:continue
            add_t=tuple(skill['add']);delete_t=tuple(skill['delete']);src=skill['source_marker'];dst=skill['destination_marker']
            matching_goals=[g for g in target if self._unify_template(add_t,g,{}) is not None]
            for goal_fact in matching_goals:
                goal_binding=self._unify_template(add_t,goal_fact,{})
                if goal_binding is None or dst not in goal_binding:continue
                invariant={m:goal_binding[m] for m in skill['invariant_markers'] if m in goal_binding}
                if len(invariant)!=len(skill['invariant_markers']):continue
                starts=[]
                for fact in index.by_sig.get((delete_t[0],len(delete_t)),()):
                    b=self._unify_template(delete_t,fact,invariant)
                    if b is not None and src in b:starts.append(b[src])
                starts=sorted(set(starts))
                if len(starts)!=1:continue
                start_value=starts[0];target_value=goal_binding[dst]
                if start_value==target_value:continue
                # Remove the dynamic state fact from the edge model. Other
                # preconditions define legal edges; the current node supplies src.
                edge_pre=tuple(t for t in op['preconditions'] if tuple(t)!=delete_t)
                edge_model={'preconditions':edge_pre,'add':op['add'],'delete':op['delete']}
                queue=deque([(start_value,[])]);visited={start_value};nodes=0;transitions=0;found=None
                while queue and nodes<max_internal_nodes:
                    value,path=queue.popleft();nodes+=1
                    if len(path)>=max_internal_steps:continue
                    seed=dict(invariant);seed[src]=value
                    bindings=self._bindings_fact_index(edge_model,index,target,seed_bindings=[seed])
                    for binding in bindings:
                        transitions+=1
                        nxt=binding.get(dst)
                        if nxt is None or nxt==value:continue
                        new_path=path+[dict(binding)]
                        if nxt==target_value:
                            found=new_path;queue.clear();break
                        if nxt not in visited:
                            visited.add(nxt);queue.append((nxt,new_path))
                if found is None:continue
                # Independently execute every primitive step on a fresh mutable
                # state index; the closure search itself never mutates the world.
                run=_MutableFactIndex(start);expanded=[];valid=True
                for binding in found:
                    pre=[]
                    for t in op['preconditions']:
                        f=_instantiate(tuple(t),binding)
                        if f is None or f not in run.facts:valid=False;break
                        pre.append(f)
                    if not valid:break
                    deletes=[];adds=[]
                    for t in op['delete']:
                        f=_instantiate(tuple(t),binding)
                        if f is None:valid=False;break
                        deletes.append(f)
                    if not valid:break
                    for t in op['add']:
                        f=_instantiate(tuple(t),binding)
                        if f is None:valid=False;break
                        adds.append(f)
                    if not valid:break
                    removed=[f for f in deletes if f in run.facts];added=[f for f in adds if f not in run.facts]
                    for f in deletes:run.remove(f)
                    for f in adds:run.add(f)
                    expanded.append({'kind':'primitive','operator':op['pattern'],'action':self._render_action(op['pattern'],binding),
                                     'binding':dict(binding),'added':sorted(added),'removed':sorted(removed)})
                if not valid or not target.issubset(run.facts):continue
                solutions.append({'skill':skill,'result':frozenset(run.facts),'expanded':expanded,
                                  'internal_nodes':nodes,'internal_transitions':transitions})
        if not solutions:return None
        distinct={s['result'] for s in solutions}
        if len(distinct)!=1:return None
        chosen=min(solutions,key=lambda s:(len(s['expanded']),s['skill']['id']))
        step={'kind':'iterative','operator':chosen['skill']['id'],'action':chosen['skill']['id'],'binding':{},
              'added':sorted(chosen['result']-start),'removed':sorted(start-chosen['result']),
              'expanded_steps':chosen['expanded'],'primitive_length':len(chosen['expanded'])}
        return {'status':'plan_found','result':chosen['result'],'steps':[step],'nodes':1,'transitions':1,
                'operators':len(ops),'macros':0,'iterative_skills':len(skills),'hierarchical_steps':1,
                'primitive_steps':len(chosen['expanded']),'macro_steps':0,'iterative_steps':1,
                'iterative_search_nodes':chosen['internal_nodes'],'iterative_search_transitions':chosen['internal_transitions'],
                'strategy':'iterative_closure'}

    @staticmethod
    def _render_action(pattern: str, binding: dict[str,str]) -> str:
        out=pattern
        for marker,value in binding.items():out=out.replace(marker,value)
        return out

    @staticmethod
    def _apply_partitioned(dynamic: frozenset[Fact], static: frozenset[Fact], op: dict,
                           binding: dict[str,str]) -> frozenset[Fact] | None:
        for t in op['preconditions']:
            f=_instantiate(tuple(t),binding)
            if f is None or (f not in dynamic and f not in static):return None
        deletes=[];adds=[]
        for t in op['delete']:
            f=_instantiate(tuple(t),binding)
            if f is None:return None
            deletes.append(f)
        for t in op['add']:
            f=_instantiate(tuple(t),binding)
            if f is None:return None
            adds.append(f)
        # Predicates changed by an operator are dynamic by construction.
        return frozenset((set(dynamic)-set(deletes))|set(adds))

    def plan(self, state, goal, max_steps: int = 8, max_nodes: int = 20_000,
             use_macros: bool = True, prefer_macros: bool = True, goal_directed_macros: bool = True,
             use_iterations: bool = True, max_iterative_steps: int = 10_000, max_iterative_nodes: int = 50_000) -> dict:
        start,target=_canon_state(state),_canon_state(goal)
        if target.issubset(start):return {'status':'plan_found','result':start,'steps':[],'nodes':0,
                                          'hierarchical_steps':0,'primitive_steps':0,'macro_steps':0}
        ops=self.operators();macros=self.macros() if use_macros else [];iterations=self.iterative_skills() if use_iterations else []
        if not ops:return {'status':'goal_unreached','result':None,'steps':[],'nodes':0,'reason':'no_learned_operators'}
        if iterations:
            iterative=self._try_iterative_direct(start,target,iterations,ops,max_iterative_steps,max_iterative_nodes)
            if iterative is not None:
                self.audit.append({'event':'plan','strategy':'iterative_closure','primitive_steps':iterative['primitive_steps'],
                                   'internal_nodes':iterative['iterative_search_nodes']})
                return iterative
        if macros and prefer_macros:
            fast=self._try_hierarchical_rollout(start,target,macros,max_steps,ops)
            if fast is not None:
                self.audit.append({'event':'plan','strategy':'hierarchical_rollout','steps':fast['hierarchical_steps'],
                                   'primitive_steps':fast['primitive_steps'],'nodes':fast['nodes'],'transitions':fast['transitions']})
                return fast
        all_models=ops+macros
        dynamic_preds={t[0] for op in all_models for t in (*op['add'],*op['delete'])}
        static=frozenset(f for f in start if f[0] not in dynamic_preds)
        dynamic_start=frozenset(f for f in start if f[0] in dynamic_preds)
        static_goal=frozenset(f for f in target if f[0] not in dynamic_preds)
        dynamic_goal=frozenset(f for f in target if f[0] in dynamic_preds)
        if not static_goal.issubset(static):
            return {'status':'goal_unreached','result':None,'steps':[],'nodes':0,'reason':'unreachable_static_goal'}
        needed={(t[0],len(t)) for op in all_models for t in op['preconditions']}
        static_index=defaultdict(list)
        for fact in static:
            key=(fact[0],len(fact))
            if key in needed:static_index[key].append(fact)
        queue=deque([(dynamic_start,[])]);visited={dynamic_start};nodes=0;transitions=0
        lookup={op['pattern']:op for op in ops}
        sources=(macros+ops) if prefer_macros else (ops+macros)
        macro_ids={m['id'] for m in macros}
        while queue and nodes<max_nodes:
            current,path=queue.popleft();nodes+=1
            if len(path)>=max_steps:continue
            by_sig={key:list(values) for key,values in static_index.items()}
            for fact in current:
                key=(fact[0],len(fact))
                if key in needed:by_sig.setdefault(key,[]).append(fact)
            arg_index={}
            unsatisfied=frozenset(dynamic_goal-current)
            for model in sources:
                is_macro=model.get('id') in macro_ids
                seeds=self._goal_seed_bindings(model,unsatisfied) if (is_macro and goal_directed_macros) else None
                for binding in self._bindings(model,current,dynamic_goal,by_sig=by_sig,arg_index=arg_index,seed_bindings=seeds):
                    transitions+=1
                    if is_macro:
                        nxt,expanded=self._apply_macro_partitioned(current,static,model,binding,lookup)
                    else:
                        nxt=self._apply_partitioned(current,static,model,binding);expanded=None
                    if nxt is None or nxt==current or nxt in visited:continue
                    if is_macro:
                        step={'kind':'macro','operator':model['id'],'action':model['id'],'binding':dict(binding),
                              'added':sorted(nxt-current),'removed':sorted(current-nxt),'expanded_steps':expanded,
                              'primitive_length':model['primitive_length']}
                    else:
                        step={'kind':'primitive','operator':model['pattern'],'action':self._render_action(model['pattern'],binding),
                              'binding':dict(binding),'added':sorted(nxt-current),'removed':sorted(current-nxt)}
                    new_path=path+[step]
                    if dynamic_goal.issubset(nxt):
                        result_state=frozenset(set(static)|set(nxt))
                        primitive_steps=sum(st.get('primitive_length',1) if st.get('kind')=='macro' else 1 for st in new_path)
                        macro_steps=sum(st.get('kind')=='macro' for st in new_path)
                        report={'status':'plan_found','result':result_state,'steps':new_path,'nodes':nodes,
                                'transitions':transitions,'operators':len(ops),'macros':len(macros),
                                'hierarchical_steps':len(new_path),'primitive_steps':primitive_steps,'macro_steps':macro_steps,
                                'static_facts':len(static),'dynamic_facts':len(nxt)}
                        self.audit.append({'event':'plan','steps':len(new_path),'primitive_steps':primitive_steps,
                                           'macro_steps':macro_steps,'nodes':nodes,'transitions':transitions,
                                           'static_facts':len(static),'dynamic_facts':len(nxt)})
                        return report
                    visited.add(nxt)
                    if is_macro and prefer_macros:queue.appendleft((nxt,new_path))
                    else:queue.append((nxt,new_path))
        return {'status':'goal_unreached','result':None,'steps':[],'nodes':nodes,'transitions':transitions,
                'operators':len(ops),'macros':len(macros),'static_facts':len(static),'dynamic_facts':len(dynamic_start)}

    def observe_goal(self, text: str, goal) -> dict:
        target=_canon_state(goal)
        aligned=_surface_from_goal(text,target)
        if aligned is None:return {'status':'ungrounded_goal'}
        pattern,mapping=aligned
        templated={t for f in target if (t:=_template_fact(f,mapping,True)) is not None}
        if not templated:return {'status':'ungrounded_goal'}
        eid=json.dumps({'text':normalize(text),'goal':sorted(target)},ensure_ascii=False,sort_keys=True,separators=(',',':'))
        s=self.goal_sessions.setdefault(pattern,{'observations':[],'promoted':False})
        if any(o['episode_id']==eid for o in s['observations']):return {'status':'duplicate_goal_episode','pattern':pattern}
        s['observations'].append({'episode_id':eid,'goal':[list(x) for x in sorted(templated,key=_template_sort_key)]})
        variants={tuple(tuple(x) for x in o['goal']) for o in s['observations']}
        if len(variants)>1:
            s.update({'promoted':False,'status':'inconsistent_goals'})
            return {'status':'inconsistent_goals','pattern':pattern}
        if len(s['observations'])<self.goal_min_support:
            return {'status':'pending_goal_support','pattern':pattern,'support':len(s['observations']),'required':self.goal_min_support}
        s.update({'promoted':True,'status':'goal_schema_learned','goal':s['observations'][0]['goal'],'support':len(s['observations'])})
        return {'status':'goal_schema_learned','pattern':pattern,'support':len(s['observations']),'goal':s['goal']}

    def resolve_goal(self, text: str) -> dict:
        matches=[]
        for pattern,s in sorted(self.goal_sessions.items()):
            if not s.get('promoted'):continue
            binding=_binding_from_text(pattern,text)
            if binding is None:continue
            facts=[]
            for t in s['goal']:
                f=_instantiate(tuple(t),binding)
                if f is None:break
                facts.append(f)
            else:matches.append((pattern,binding,frozenset(facts)))
        if not matches:return {'status':'unknown_symbolic_goal'}
        distinct={m[2] for m in matches}
        if len(distinct)!=1:return {'status':'ambiguous_symbolic_goal','alternatives':len(distinct)}
        pattern,binding,goal=matches[0]
        return {'status':'symbolic_goal_resolved','pattern':pattern,'binding':binding,'goal':goal}

    def plan_goal(self, text: str, state, max_steps: int = 8, max_nodes: int = 20_000, use_macros: bool = True, use_iterations: bool = True) -> dict:
        resolved=self.resolve_goal(text)
        if resolved['status']!='symbolic_goal_resolved':return resolved
        report=self.plan(state,resolved['goal'],max_steps=max_steps,max_nodes=max_nodes,use_macros=use_macros,use_iterations=use_iterations)
        report['resolved_goal']=resolved['goal'];report['goal_pattern']=resolved['pattern']
        return report

    def as_dict(self) -> dict:
        return {'version':11,'min_support':self.min_support,'goal_min_support':self.goal_min_support,'alias_min_support':self.alias_min_support,
                'max_precondition_candidates':self.max_precondition_candidates,'max_action_bindings':self.max_action_bindings,
                'macro_min_support':self.macro_min_support,'iterative_min_support':self.iterative_min_support,
                'sessions':deepcopy(self.sessions),'goal_sessions':deepcopy(self.goal_sessions),
                'alias_sessions':deepcopy(self.alias_sessions),'macro_sessions':deepcopy(self.macro_sessions),
                'iterative_sessions':deepcopy(self.iterative_sessions),
                'analogy_schemas':deepcopy(self.analogy_schemas),
                'analogy_schema_by_pattern':deepcopy(self.analogy_schema_by_pattern),
                'analogy_unclustered':sorted(self.analogy_unclustered),
                'external_permutation_schemas':deepcopy(self.external_permutation_schemas),
                'external_projection_schemas':deepcopy(self.external_projection_schemas),
                'external_role_sets':deepcopy(self.external_role_sets),
                'external_role_cardinalities':deepcopy(self.external_role_cardinalities),
                'external_role_topologies':deepcopy(self.external_role_topologies),
                'audit':deepcopy(self.audit)}

    @classmethod
    def from_dict(cls,data: dict) -> 'SymbolicWorldLearner':
        if not data:return cls()
        version=data.get('version',1)
        if version not in (1,2,3,4,5,6,7,8,9,10,11):raise ValueError('Estado simbólico no compatible.')
        obj=cls(data.get('min_support',3),data.get('goal_min_support',2),data.get('alias_min_support',2),
                data.get('max_precondition_candidates',24),data.get('max_action_bindings',10_000),
                data.get('macro_min_support',3),data.get('iterative_min_support',3))
        obj.sessions=deepcopy(data.get('sessions',{}));obj.goal_sessions=deepcopy(data.get('goal_sessions',{}))
        obj.alias_sessions=deepcopy(data.get('alias_sessions',{})) if version>=2 else {}
        obj.macro_sessions=deepcopy(data.get('macro_sessions',{})) if version>=3 else {}
        obj.iterative_sessions=deepcopy(data.get('iterative_sessions',{})) if version>=4 else {}
        obj.analogy_schemas=deepcopy(data.get('analogy_schemas',{})) if version>=5 else {}
        if version>=6:
            obj.analogy_schema_by_pattern=deepcopy(data.get('analogy_schema_by_pattern',{}))
            obj.analogy_unclustered=set(data.get('analogy_unclustered',[]))
        else:
            obj.analogy_schema_by_pattern={}
            for sid,schema in obj.analogy_schemas.items():
                for pattern in schema.get('members',[]):obj.analogy_schema_by_pattern[pattern]=sid
            obj.analogy_unclustered={p for p,state in obj.sessions.items() if state.get('promoted') and p not in obj.analogy_schema_by_pattern}
        obj.external_permutation_schemas=deepcopy(data.get('external_permutation_schemas',{})) if version>=7 else {}
        obj.external_projection_schemas=deepcopy(data.get('external_projection_schemas',{})) if version>=8 else {}
        obj.external_role_sets=deepcopy(data.get('external_role_sets',{})) if version>=9 else {}
        obj.external_role_cardinalities=deepcopy(data.get('external_role_cardinalities',{})) if version>=10 else {}
        obj.external_role_topologies=deepcopy(data.get('external_role_topologies',{})) if version>=11 else {}
        obj.audit=deepcopy(data.get('audit',[]))
        return obj

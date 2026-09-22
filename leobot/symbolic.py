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

    def observe(self, text: str, before, after) -> dict:
        b,a=_canon_state(before),_canon_state(after)
        encoded=self._encode_episode(text,b,a)
        if encoded is None:
            result={'status':'ungrounded_transition','reason':'changed entities must be explicitly mentioned'}
            self.audit.append({'event':'observe','text':text,**result});return result
        pattern,mapping,before_t,add_t,del_t=encoded
        eid=self._episode_id(text,b,a)
        session=self.sessions.setdefault(pattern,{'observations':[],'promoted':False})
        if any(o['episode_id']==eid for o in session['observations']):
            return {'status':'duplicate_episode','pattern':pattern,'support':sum(o['success'] for o in session['observations'])}
        success=b!=a
        obs={'episode_id':eid,'success':success,'before':[list(x) for x in sorted(before_t,key=_template_sort_key)],
             'add':[list(x) for x in sorted(add_t,key=_template_sort_key)],
             'delete':[list(x) for x in sorted(del_t,key=_template_sort_key)]}
        session['observations'].append(obs)
        report=self._fit(pattern)
        alias_report=None
        if report.get('status')!='operator_learned':
            alias_report=self._record_alias(pattern,mapping,b,a,eid)
        chosen=alias_report if alias_report is not None else report
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
                            'precondition_mode':s.get('precondition_mode')})
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
        return {'version':4,'min_support':self.min_support,'goal_min_support':self.goal_min_support,'alias_min_support':self.alias_min_support,
                'max_precondition_candidates':self.max_precondition_candidates,'max_action_bindings':self.max_action_bindings,
                'macro_min_support':self.macro_min_support,'iterative_min_support':self.iterative_min_support,
                'sessions':deepcopy(self.sessions),'goal_sessions':deepcopy(self.goal_sessions),
                'alias_sessions':deepcopy(self.alias_sessions),'macro_sessions':deepcopy(self.macro_sessions),
                'iterative_sessions':deepcopy(self.iterative_sessions),
                'audit':deepcopy(self.audit)}

    @classmethod
    def from_dict(cls,data: dict) -> 'SymbolicWorldLearner':
        if not data:return cls()
        version=data.get('version',1)
        if version not in (1,2,3,4):raise ValueError('Estado simbólico no compatible.')
        obj=cls(data.get('min_support',3),data.get('goal_min_support',2),data.get('alias_min_support',2),
                data.get('max_precondition_candidates',24),data.get('max_action_bindings',10_000),
                data.get('macro_min_support',3),data.get('iterative_min_support',3))
        obj.sessions=deepcopy(data.get('sessions',{}));obj.goal_sessions=deepcopy(data.get('goal_sessions',{}))
        obj.alias_sessions=deepcopy(data.get('alias_sessions',{})) if version>=2 else {}
        obj.macro_sessions=deepcopy(data.get('macro_sessions',{})) if version>=3 else {}
        obj.iterative_sessions=deepcopy(data.get('iterative_sessions',{})) if version>=4 else {}
        obj.audit=deepcopy(data.get('audit',[]))
        return obj

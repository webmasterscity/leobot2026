"""Ground natural-language action cues in observed numeric state transitions.

This module does not parse action words into hand-authored semantic frames.  It
uses the utterance only as an auditable cue that groups independent episodes;
the executable meaning is synthesized from state-before -> state-after pairs by
ProgramLearner.  Integer literals in the utterance become extra program inputs,
so a learned construction can transfer to unseen numeric parameters.

The current state representation is deliberately small (integer tuples) because
this is an experiment about acquisition/transfer, not a claim of open-world
planning.  Unsupported state types are rejected rather than silently coerced.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Iterable
from collections import defaultdict, deque
from difflib import SequenceMatcher
from itertools import combinations

from .language import normalize
from .programs import ProgramLearner, LIMIT, Expr, COMMUTATIVE
from .rbf import RBFStrategyRouter

_NUM = re.compile(r'(?<!\w)-?\d+(?!\w)')
_WORD = re.compile(r'[a-záéíóúüñ]+', re.IGNORECASE)
_STOP = {
    'el','la','los','las','un','una','unos','unas','de','del','al','a','y','o','en','por','para',
    'con','sin','que','se','lo','le','cada','valor','valores','numero','numeros','estado','resultado'
}
_SEQUENCE_SPLIT = re.compile(r'\s*(?:[;,]|\by\s+luego\b|\by\s+despues\b|\bluego\b|\bdespues\b|\bentonces\b|\by\b)\s*')


def _surface(text: str) -> tuple[str, tuple[int, ...]]:
    """Return normalized numeric-parameterized surface and literal parameters."""
    norm = normalize(text)
    params: list[int] = []
    pieces: list[str] = []
    pos = 0
    for i, match in enumerate(_NUM.finditer(norm)):
        pieces.append(norm[pos:match.start()])
        pieces.append(f'<n{i}>')
        params.append(int(match.group()))
        pos = match.end()
    pieces.append(norm[pos:])
    return ''.join(pieces), tuple(params)


def _concepts(pattern: str) -> set[str]:
    return {w for w in _WORD.findall(pattern) if len(w) > 2 and w not in _STOP}


def _skill_prefix(pattern: str) -> str:
    # Pattern is persisted next to the id, so collisions are detectable rather
    # than being accepted as semantic identity.
    return 'proc_' + hashlib.blake2s(pattern.encode('utf8'), digest_size=8).hexdigest()


class ProcedureGrounder:
    """Induce executable procedures from language + observable transitions."""

    def __init__(self, programs: ProgramLearner, min_support: int = 3,
                 semantic_rewrites: bool = True, sequence_composition: bool = True,
                 max_rewrite_states: int = 64, max_rewrite_steps: int = 3) -> None:
        self.programs = programs
        self.min_support = max(2, int(min_support))
        self.semantic_rewrites_enabled = bool(semantic_rewrites)
        self.sequence_composition_enabled = bool(sequence_composition)
        self.max_rewrite_states = max(1, int(max_rewrite_states))
        self.max_rewrite_steps = max(0, int(max_rewrite_steps))
        self.sessions: dict[str, dict] = {}
        self.audit: list[dict] = []
        # family_id -> independently grounded surface patterns with the same
        # executable behaviour on a fixed, label-free probe set.  Families are
        # hypotheses, not proofs of synonymy.
        self.semantic_families: dict[str, set[str]] = defaultdict(set)
        # pair-of-pattern evidence -> small lexical/phrase rewrite hypotheses.
        self.rewrite_evidence: dict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]] = {}
        self.semantic_rewrites: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        # Natural-language goal constructions are learned separately from action
        # cues so behavioural equivalence cannot accidentally conflate goals
        # with transitions.
        self.goal_sessions: dict[str, dict] = {}
        # Representation-independent transformation priors learned elsewhere.
        # Only structural permutations are stored; no language/domain labels.
        self.external_permutation_schemas: dict[str, dict] = {}
        self.external_projection_schemas: dict[str, dict] = {}
        self.external_role_sets: dict[str, dict] = {}
        self.external_role_cardinalities: dict[str, dict] = {}
        # Learned meta-policy for dependency-restricted program synthesis.
        # Keys are structural classes only (input arity + number of relevant
        # roles); no task names or answers are stored here.
        self.dependency_search_stats: dict[str, dict] = {}
        # V6.4: non-neural RBF meta-router. It only reorders the two existing
        # dependency-search strategies from structural task features; it never
        # generates answers or removes the completeness fallback.
        self.rbf_strategy_enabled = True
        self.rbf_strategy_router = RBFStrategyRouter()
        # Shared bot-level MetaController. It is intentionally not persisted here;
        # Bot owns the single auditable controller and reattaches it on load.
        self.meta_controller = None

    @staticmethod
    def _pattern_tokens(pattern: str) -> tuple[str, ...]:
        return tuple(pattern.split())

    @staticmethod
    def _pair_key(a: str, b: str) -> str:
        return '\n'.join(sorted((a, b)))

    def _canonical_program(self, program, seen: tuple[str, ...] = ()) -> str:
        if not isinstance(program, Expr):
            return str(program)
        if program.op == 'var':
            return f'x{program.value}'
        if program.op == 'const':
            return str(program.value)
        if program.op == 'call':
            skill=str(program.value)
            bodies=self.programs.solutions.get(skill, ())
            if skill not in seen and len(bodies)==1:
                return self._canonical_program(bodies[0], seen + (skill,))
            return '@' + skill
        if program.op == 'pcall':
            return '@' + str(program.value) + '(' + ','.join(self._canonical_program(x,seen) for x in program.children) + ')'
        children=[self._canonical_program(x,seen) for x in program.children]
        if program.op in COMMUTATIVE:
            children.sort()
        return program.op + '(' + ','.join(children) + ')'

    def _behaviour_family(self, session: dict) -> str | None:
        if not session.get('promoted'):
            return None
        arity = int(session['input_arity']) + int(session['parameter_count'])
        probes = tuple(self.programs.probes(arity))
        rows = []
        for args in probes:
            values = []
            for skill in session['output_skills']:
                pred = self.programs.predict(skill, args)
                if pred.get('status') != 'hypothesis':
                    return None
                values.append(pred.get('value'))
            rows.append(tuple(values))
        programs = tuple(tuple(sorted(self._canonical_program(p) for p in self.programs.solutions.get(skill, ())))
                         for skill in session['output_skills'])
        # Behavioural probes are paired with the learned executable structure.
        # This is deliberately conservative: two distinct programs that merely
        # collide on the finite probes are not promoted as lexical synonyms.
        payload = repr((session['input_arity'], session['parameter_count'], session['output_arity'], programs, rows))
        return hashlib.blake2s(payload.encode('utf8'), digest_size=12).hexdigest()

    def _rewrite_rules_between(self, a_pattern: str, b_pattern: str):
        a, b = self._pattern_tokens(a_pattern), self._pattern_tokens(b_pattern)
        out = []
        matcher = SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != 'replace':
                continue
            left, right = a[i1:i2], b[j1:j2]
            if not left or not right:
                continue
            # Placeholders carry argument roles; rewriting them would silently
            # change procedure arity/order rather than paraphrase the cue.
            if any(tok.startswith('<n') for tok in (*left, *right)):
                continue
            if len(left) <= 4 and len(right) <= 4:
                pair = (left, right) if left <= right else (right, left)
                out.append(pair)
        return out

    def _rebuild_rewrite_union(self) -> None:
        merged = set()
        for rules in self.rewrite_evidence.values():
            merged.update((tuple(a), tuple(b)) for a, b in rules)
        self.semantic_rewrites = merged

    def _register_semantics(self, pattern: str) -> None:
        session = self.sessions[pattern]
        old_family = session.get('semantic_family')
        if old_family:
            self.semantic_families[old_family].discard(pattern)
            if not self.semantic_families[old_family]:
                self.semantic_families.pop(old_family, None)
        # Evidence involving a re-fit pattern is withdrawn and recomputed.
        for key in list(self.rewrite_evidence):
            if pattern in key.split('\n'):
                self.rewrite_evidence.pop(key, None)
        family = self._behaviour_family(session)
        session['semantic_family'] = family
        if family is None:
            self._rebuild_rewrite_union()
            return
        peers = list(self.semantic_families.get(family, ()))
        for other in peers:
            rules = self._rewrite_rules_between(pattern, other)
            if rules:
                self.rewrite_evidence[self._pair_key(pattern, other)] = rules
        self.semantic_families[family].add(pattern)
        self._rebuild_rewrite_union()

    @staticmethod
    def _replace_phrase(tokens: tuple[str, ...], old: tuple[str, ...], new: tuple[str, ...]):
        n = len(old)
        for i in range(len(tokens) - n + 1):
            if tokens[i:i+n] == old:
                yield tokens[:i] + new + tokens[i+n:]

    def _rewrite_variants(self, pattern: str):
        start = self._pattern_tokens(pattern)
        yield pattern
        if not self.semantic_rewrites_enabled or not self.semantic_rewrites or self.max_rewrite_steps <= 0:
            return
        queue = deque([(start, 0)])
        seen = {start}
        while queue and len(seen) < self.max_rewrite_states:
            tokens, depth = queue.popleft()
            if depth >= self.max_rewrite_steps:
                continue
            for left, right in sorted(self.semantic_rewrites):
                for old, new in ((left, right), (right, left)):
                    for nxt in self._replace_phrase(tokens, old, new):
                        if nxt in seen:
                            continue
                        seen.add(nxt)
                        yield ' '.join(nxt)
                        queue.append((nxt, depth + 1))
                        if len(seen) >= self.max_rewrite_states:
                            return

    @staticmethod
    def _validate_state(values: Iterable[int], label: str) -> tuple[int, ...]:
        out = tuple(values)
        if not 1 <= len(out) <= 4:
            raise ValueError(f'{label}: se requieren de 1 a 4 enteros.')
        if any(type(v) is not int or abs(v) > LIMIT for v in out):
            raise ValueError(f'{label}: solo enteros con magnitud máxima 10^12.')
        return out

    @staticmethod
    def _permutation_key(perm) -> str:
        perm=tuple(int(x) for x in perm)
        return f"perm:{len(perm)}:" + ','.join(map(str,perm))

    def register_external_permutation(self, perm, source: str, support: int = 1) -> dict:
        perm=tuple(int(x) for x in perm)
        if len(perm)<2 or tuple(sorted(perm))!=tuple(range(len(perm))) or perm==tuple(range(len(perm))):
            return {'status':'cross_modal_schema_ignored','reason':'not_nontrivial_permutation'}
        key=self._permutation_key(perm)
        row=self.external_permutation_schemas.setdefault(key,{'kind':'permutation','perm':list(perm),'sources':{},'support':0})
        src=normalize(str(source));old=int(row['sources'].get(src,0));row['sources'][src]=max(old,max(1,int(support)))
        row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],'sources':len(row['sources'])}

    @staticmethod
    def observed_projection_signature(session: dict):
        """Infer a pure role projection directly from independent transitions.

        This deliberately does not inspect the syntactic form of synthesized
        programs.  A projection is accepted only when, for every output role,
        exactly one input position agrees with that output in *all* observed
        supports.  If two input columns remain observationally indistinguishable
        the result is ambiguous and no cross-representation prior is exported.
        Parameters are excluded: this signature describes only state-role flow.
        """
        if int(session.get('parameter_count', 0)) != 0:
            return None
        n=int(session.get('input_arity',0)); m=int(session.get('output_arity',0))
        supports=list(session.get('supports',()))
        if n < 1 or m < 1 or not supports:
            return None
        mapping=[]
        for out_pos in range(m):
            candidates=[]
            for in_pos in range(n):
                ok=True
                for row in supports:
                    before=tuple(row.get('before',()))
                    after=tuple(row.get('after',()))
                    if len(before)!=n or len(after)!=m or before[in_pos] != after[out_pos]:
                        ok=False; break
                if ok:
                    candidates.append(in_pos)
            if len(candidates) != 1:
                return None
            mapping.append(candidates[0])
        return n, tuple(mapping)

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

    def _matching_external_role_set(self, session: dict):
        if int(session.get('parameter_count',0))!=0:return None
        supports=list(session.get('supports',()))
        if len(supports)<2:return None
        sig=self.observed_projection_signature(session)
        if sig is None:return None
        n,mapping=sig; roles=tuple(sorted(set(mapping))); key=self._role_set_key(n,roles)
        prior=self.external_role_sets.get(key)
        return (key,mapping,prior) if prior is not None else None

    def register_external_role_cardinality(self, cardinality: int, source: str, support: int = 1) -> dict:
        k=int(cardinality)
        if k < 1 or k > 7:
            return {'status':'cross_modal_schema_ignored','reason':'invalid_role_cardinality'}
        key=f'card:{k}'
        row=self.external_role_cardinalities.setdefault(key,{'kind':'role_cardinality','cardinality':k,
                                                            'sources':{},'support':0})
        src=normalize(str(source)); old=int(row['sources'].get(src,0))
        row['sources'][src]=max(old,max(1,int(support)))
        row['support']=sum(int(v) for v in row['sources'].values())
        return {'status':'cross_modal_schema_registered','schema':key,'support':row['support'],
                'sources':len(row['sources'])}

    @staticmethod
    def _dependency_roles_supported(session: dict, output_index: int, roles) -> bool:
        supports=list(session.get('supports',()))
        n=int(session.get('input_arity',0)); roles=tuple(sorted(set(int(x) for x in roles)))
        if not roles or len(roles)>=n or len(supports)<2:
            return False
        outside=tuple(i for i in range(n) if i not in roles)
        excluded_witness={i:False for i in outside}
        included_witness={i:False for i in roles}
        for i,left in enumerate(supports):
            lb=tuple(left['before']); lo=tuple(left['after'])[output_index]
            for right in supports[i+1:]:
                rb=tuple(right['before']); ro=tuple(right['after'])[output_index]
                if all(lb[k]==rb[k] for k in roles):
                    for k in outside:
                        if lb[k]!=rb[k]:
                            if lo!=ro: return False
                            excluded_witness[k]=True
                if lo!=ro:
                    for k in roles:
                        if lb[k]!=rb[k] and all(lb[j]==rb[j] for j in roles if j!=k):
                            included_witness[k]=True
        return all(excluded_witness.values()) and all(included_witness.values())

    def _matching_external_dependency_cardinality(self, session: dict, output_index: int):
        """Infer unseen role positions from a learned sparsity/cardinality prior.

        The prior provides only *how many* roles tend to matter.  The new task's
        own interventions must identify *which* roles.  At least two independent
        provenance sources are required before a cardinality prior can transfer
        across arities.
        """
        if int(session.get('parameter_count',0)) != 0:
            return None
        supports=list(session.get('supports',()))
        if len(supports) < self.min_support:
            return None
        n=int(session.get('input_arity',0))
        winners=[]
        for key,row in self.external_role_cardinalities.items():
            if len(row.get('sources',{})) < 2:
                continue
            k=int(row.get('cardinality',0))
            if k < 1 or k >= n:
                continue
            for roles in combinations(range(n),k):
                if self._dependency_roles_supported(session,output_index,roles):
                    winners.append((f'{key}->roles:{n}:'+','.join(map(str,roles)),tuple(roles),row))
        return winners[0] if len(winners)==1 else None

    @staticmethod
    def _dependency_policy_key(input_arity: int, roles) -> str:
        return f"{int(input_arity)}:{len(tuple(roles))}"

    @staticmethod
    def _dependency_rbf_features(input_arity: int, roles, support_count: int = 0) -> tuple[float, ...]:
        """Domain-neutral, scaled structural features for the RBF router.

        No task name, predicate, entity, output, or held-out label is present.
        The role fraction lets nearby arities share evidence without declaring
        them semantically identical.
        """
        n=max(1,int(input_arity)); k=len(tuple(roles)); s=max(0,int(support_count))
        return (min(n,8)/8.0, min(k,4)/2.0, k/n, min(s,8)/8.0)

    def _dependency_strategy_order(self, input_arity: int, roles, support_count: int = 0):
        key=self._dependency_policy_key(input_arity,roles)
        table=self.dependency_search_stats.get(key,{})
        default=['auto_library','no_library']
        # Exact historical class remains the first authority.
        if table:
            seen=[]
            for strategy in default:
                row=table.get(strategy)
                if not row or int(row.get('trials',0)) <= 0:
                    continue
                trials=max(1,int(row.get('trials',0))); success=int(row.get('success',0))
                avg=float(row.get('candidates',0))/trials
                seen.append((-success/trials,avg,strategy))
            seen.sort(); ordered=[x[2] for x in seen]
            ordered.extend(x for x in default if x not in ordered)
            return key,ordered,{'used':False,'mode':'exact_class','scores':[]}
        # Only unseen structural classes are eligible for interpolation.  The
        # router can save search effort but cannot suppress either strategy.
        if self.rbf_strategy_enabled:
            features=self._dependency_rbf_features(input_arity,roles,support_count)
            rbf=self.rbf_strategy_router.rank(features,default)
            return key,list(rbf['order']),{**rbf,'mode':'rbf','features':list(features)}
        return key,default,{'used':False,'mode':'disabled','scores':[]}

    def _record_dependency_strategy(self, key: str, strategy: str, report: dict,
                                    input_arity: int | None = None, roles=(),
                                    support_count: int = 0) -> None:
        table=self.dependency_search_stats.setdefault(key,{})
        row=table.setdefault(strategy,{'trials':0,'success':0,'candidates':0})
        success=report.get('status')=='learned_hypothesis'
        row['trials']=int(row.get('trials',0))+1
        row['success']=int(row.get('success',0))+success
        row['candidates']=int(row.get('candidates',0))+max(0,int(report.get('candidates',0) or 0))
        if input_arity is not None:
            self.rbf_strategy_router.observe(
                self._dependency_rbf_features(input_arity,roles,support_count), strategy,
                success=success, candidates=int(report.get('candidates',0) or 0),
                failure_budget=int(getattr(self.programs,'max_candidates',1) or 1))

    def _meta_representation_features(self, session: dict) -> tuple[float, ...]:
        """Learner-neutral structural signature used by the shared MetaController.

        Positions have the same meaning in the symbolic learner: arity, support,
        failure fraction, output/effect width, and availability of role-set,
        cardinality, projection/permutation and topology priors.  No words, task
        names, entities or answers are included.
        """
        n=max(1,int(session.get('input_arity',0)))
        support=max(0,len(session.get('supports',())))
        out=max(0,int(session.get('output_arity',0)))
        rs=sum(1 for row in self.external_role_sets.values() if int(row.get('input_arity',0))==n)
        card=sum(1 for row in self.external_role_cardinalities.values() if 0<int(row.get('cardinality',0))<n)
        proj=(sum(1 for row in self.external_projection_schemas.values() if int(row.get('input_arity',0))==n)
              +sum(1 for row in self.external_permutation_schemas.values() if len(row.get('perm',()))==n))
        return (min(n,8)/8.0,min(support,8)/8.0,0.0,min(out,8)/8.0,
                min(rs,8)/8.0,min(card,8)/8.0,min(proj,8)/8.0,0.0)

    def _meta_representation_order(self, session: dict, strategies) -> tuple[list[str], dict]:
        default=list(strategies)
        if self.meta_controller is None:
            return default,{'used':False,'mode':'disabled','order':default}
        route=self.meta_controller.rank('representation',self._meta_representation_features(session),default)
        return list(route.get('order',default)),route

    def _record_meta_representation(self, session: dict, strategy: str, success: bool, cost: float = 1.0) -> None:
        if self.meta_controller is None:
            return
        self.meta_controller.observe('representation',self._meta_representation_features(session),strategy,
                                     success=bool(success),cost=max(0.001,float(cost)),failure_budget=2.0)

    def _matching_external_dependency_role_set(self, session: dict, output_index: int):
        """Select an unordered relevance prior using target-domain invariance.

        A prior is admissible only when the target observations themselves show
        that changing roles outside the set can leave this output unchanged, and
        changing selected roles can change the output.  The prior then restricts
        the synthesis alphabet; it never supplies the arithmetic operation.
        """
        if int(session.get('parameter_count',0)) != 0:
            return None
        supports=list(session.get('supports',()))
        if len(supports) < self.min_support:
            return None
        n=int(session.get('input_arity',0))
        if n < 2 or not (0 <= int(output_index) < int(session.get('output_arity',0))):
            return None
        winners=[]
        for key,row in self.external_role_sets.items():
            if int(row.get('input_arity',0)) != n:
                continue
            roles=tuple(sorted(set(int(x) for x in row.get('roles',()))))
            if not roles or len(roles) >= n:
                continue
            outside=tuple(i for i in range(n) if i not in roles)
            excluded_witness={i:False for i in outside}
            included_witness={i:False for i in roles}
            violated=False
            for i,left in enumerate(supports):
                lb=tuple(left['before']); lo=tuple(left['after'])[output_index]
                for right in supports[i+1:]:
                    rb=tuple(right['before']); ro=tuple(right['after'])[output_index]
                    selected_same=all(lb[k] == rb[k] for k in roles)
                    if selected_same:
                        for k in outside:
                            if lb[k] != rb[k]:
                                if lo != ro:
                                    violated=True; break
                                excluded_witness[k]=True
                    if violated: break
                    if lo != ro:
                        for k in roles:
                            if lb[k] != rb[k] and all(lb[j] == rb[j] for j in roles if j != k):
                                included_witness[k]=True
                if violated: break
            if (not violated and all(excluded_witness.values())
                    and all(included_witness.values())):
                winners.append((key,roles,row))
        return winners[0] if len(winners)==1 else None

    def _matching_external_projection(self, session: dict):
        if int(session.get('parameter_count',0))!=0:return None
        n=int(session.get('input_arity',0));m=int(session.get('output_arity',0))
        if n<2 or m<1:return None
        supports=list(session.get('supports',()))
        if len(supports)<2:return None
        winners=[]
        for key,row in self.external_projection_schemas.items():
            mapping=tuple(int(x) for x in row.get('mapping',()))
            if int(row.get('input_arity',0))!=n or len(mapping)!=m:continue
            ok=True
            for ex in supports:
                before=tuple(ex['before']);after=tuple(ex['after'])
                if tuple(before[i] for i in mapping)!=after:
                    ok=False;break
            if ok:winners.append((key,mapping,row))
        return winners[0] if len(winners)==1 else None

    def _matching_external_permutation(self, session: dict):
        if int(session.get('parameter_count',0))!=0:return None
        n=int(session.get('input_arity',0))
        if n<2 or int(session.get('output_arity',0))!=n:return None
        supports=list(session.get('supports',()))
        if len(supports)<2:return None
        winners=[]
        for key,row in self.external_permutation_schemas.items():
            perm=tuple(int(x) for x in row.get('perm',()))
            if len(perm)!=n:continue
            ok=True
            for ex in supports:
                before=tuple(ex['before']); after=tuple(ex['after'])
                if tuple(before[i] for i in perm)!=after:
                    ok=False;break
            if ok:winners.append((key,perm,row))
        return winners[0] if len(winners)==1 else None

    def _install_external_permutation(self, session: dict, match) -> list[dict]:
        key,perm,row=match;reports=[]
        if str(key).startswith('roles:'):
            mode='meta_role_set_transfer'; reason='meta_role_set_prior'
        elif str(key).startswith('proj:'):
            mode='cross_modal_projection_transfer'; reason='cross_modal_projection_prior'
        else:
            mode='cross_modal_permutation_transfer'; reason='cross_modal_permutation_prior'
        for out_idx,skill in enumerate(session['output_skills']):
            expr=Expr('var',perm[out_idx])
            self.programs.solutions[skill]=[expr]
            self.programs.dependencies[skill]=set()
            rep={'status':'learned_hypothesis','examples':len(session['supports']),'candidates':0,
                 'search_complete':True,'programs':[str(expr)],'reason':reason,
                 'cross_modal_schema':key}
            self.programs.reports[skill]=dict(rep);reports.append({'skill':skill,**rep})
        session['promoted']=True;session['last_reports']=reports;session['cross_modal_schema']=key
        session['cross_modal_mode']=mode
        session['cross_modal_sources']=sorted(row.get('sources',{}))
        self._register_semantics(session['pattern'])
        return reports

    def observe(self, text: str, before: Iterable[int], after: Iterable[int]) -> dict:
        """Observe one independently produced transition; no semantic frame is supplied."""
        if not isinstance(text, str) or not text.strip() or len(text) > 2048:
            raise ValueError('La instrucción natural debe ser texto no vacío de hasta 2048 caracteres.')
        before_t = self._validate_state(before, 'estado inicial')
        after_t = self._validate_state(after, 'estado final')
        pattern, params = _surface(text)
        args = before_t + params
        if len(args) > 4:
            raise ValueError('El sintetizador actual admite como máximo cuatro entradas entre estado y parámetros lingüísticos.')
        key = pattern
        prefix = _skill_prefix(pattern)
        session = self.sessions.get(key)
        if session is None:
            session = {
                'pattern': pattern,
                'prefix': prefix,
                'input_arity': len(before_t),
                'parameter_count': len(params),
                'output_arity': len(after_t),
                'output_skills': [f'{prefix}_o{i}' for i in range(len(after_t))],
                'supports': [],
                'promoted': False,
                'last_reports': [],
            }
            # Detect the astronomically unlikely digest collision explicitly.
            for other in self.sessions.values():
                if other.get('prefix') == prefix and other.get('pattern') != pattern:
                    raise RuntimeError('Colisión de identificador de procedimiento.')
            self.sessions[key] = session
        expected = (session['input_arity'], session['parameter_count'], session['output_arity'])
        actual = (len(before_t), len(params), len(after_t))
        if expected != actual:
            raise ValueError('La misma construcción lingüística produjo una transición de forma incompatible.')

        signature = {'before': list(before_t), 'params': list(params), 'after': list(after_t)}
        duplicate = signature in session['supports']
        if not duplicate:
            session['supports'].append(signature)
            concepts = _concepts(pattern)
            for i, value in enumerate(after_t):
                self.programs.add_example(session['output_skills'][i], args, value, concepts=concepts)

        support = len(session['supports'])
        if support < self.min_support:
            strategy_fns={
                'projection':self._matching_external_projection,
                'permutation':self._matching_external_permutation,
                'role_set':self._matching_external_role_set,
            }
            order,route=self._meta_representation_order(session,['projection','permutation','role_set'])
            match=None; chosen_strategy=None; meta_attempts=[]
            for strategy in order:
                fn=strategy_fns.get(strategy)
                trial=fn(session) if fn is not None else None
                ok=trial is not None
                self._record_meta_representation(session,strategy,ok)
                meta_attempts.append({'strategy':strategy,'matched':ok})
                if ok:
                    match=trial; chosen_strategy=strategy; break
            if match is not None:
                reports=self._install_external_permutation(session,match)
                result={'status':'procedure_learned','pattern':pattern,'support':support,'required':self.min_support,
                        'duplicate':duplicate,'promoted':True,'reports':reports,
                        'programs':[r.get('programs',[]) for r in reports],
                        'precondition_mode':session.get('cross_modal_mode','cross_modal_transfer'),
                        'cross_modal_schema':match[0],'cross_modal_sources':session.get('cross_modal_sources',[]),
                        'meta_controller_route':route,'meta_controller_attempts':meta_attempts,
                        'meta_controller_strategy':chosen_strategy}
                self.audit.append({'event':'observe_cross_modal_fit',**deepcopy(result)})
                return result
            result = {
                'status': 'procedure_pending', 'pattern': pattern, 'support': support,
                'required': self.min_support, 'duplicate': duplicate, 'promoted': False,
                'meta_controller_route':route,'meta_controller_attempts':meta_attempts,
            }
            self.audit.append({'event':'observe_pending', **result})
            return result

        reports = []
        all_learned = True
        dependency_schemas=[]
        if not duplicate or not session.get('promoted'):
            for output_index, skill in enumerate(session['output_skills']):
                rep_order,rep_route=self._meta_representation_order(session,['role_set','role_cardinality'])
                dep=None; dep_strategy=None; rep_attempts=[]
                for rep_strategy in rep_order:
                    if rep_strategy=='role_set':
                        candidate=self._matching_external_dependency_role_set(session,output_index)
                    else:
                        candidate=self._matching_external_dependency_cardinality(session,output_index)
                    matched=candidate is not None
                    rep_attempts.append({'strategy':rep_strategy,'matched':matched})
                    if not matched:
                        self._record_meta_representation(session,rep_strategy,False)
                        continue
                    dep=candidate; dep_strategy=rep_strategy; break
                if dep is not None:
                    dep_key, dep_roles, dep_row=dep
                    policy_key,strategy_order,rbf_route=self._dependency_strategy_order(
                        int(session.get('input_arity',0)),dep_roles,len(session.get('supports',())))
                    attempts=[]; report=None
                    for strategy in strategy_order:
                        if strategy=='auto_library':
                            trial=self.programs.fit(skill,allowed_vars=dep_roles)
                        else:
                            trial=self.programs.fit(skill,library=[],allowed_vars=dep_roles)
                        self._record_dependency_strategy(
                            policy_key,strategy,trial,int(session.get('input_arity',0)),dep_roles,
                            len(session.get('supports',())))
                        attempts.append({'strategy':strategy,'status':trial.get('status'),
                                         'candidates':trial.get('candidates'),
                                         'library_seeded':trial.get('library_seeded',0)})
                        report=trial
                        if trial.get('status')=='learned_hypothesis':
                            break
                    report={**report,'meta_dependency_schema':dep_key,
                            'meta_dependency_roles':list(dep_roles),
                            'meta_dependency_sources':sorted(dep_row.get('sources',{})),
                            'meta_dependency_policy_key':policy_key,
                            'meta_dependency_strategy_order':strategy_order,
                            'meta_dependency_rbf_route':rbf_route,
                            'meta_dependency_attempts':attempts}
                    dependency_schemas.append(dep_key)
                    # The learned policy orders search but cannot remove the
                    # general learner. If every restricted strategy fails, use
                    # ordinary unrestricted synthesis as a completeness fallback.
                    representation_success=report.get('status')=='learned_hypothesis'
                    self._record_meta_representation(session,dep_strategy,representation_success,
                                                     cost=max(1.0,float(len(rep_attempts))))
                    report={**report,'meta_controller_route':rep_route,
                            'meta_controller_representation_attempts':rep_attempts,
                            'meta_controller_representation_strategy':dep_strategy}
                    if report.get('status') != 'learned_hypothesis':
                        fallback=self.programs.fit(skill)
                        report={**fallback,'meta_dependency_attempt':{
                            'schema':dep_key,'roles':list(dep_roles),
                            'restricted_attempts':attempts},
                            'meta_controller_route':rep_route,
                            'meta_controller_representation_attempts':rep_attempts,
                            'meta_controller_representation_strategy':dep_strategy}
                else:
                    report = self.programs.fit(skill)
                    report={**report,'meta_controller_route':rep_route,
                            'meta_controller_representation_attempts':rep_attempts}
                reports.append({'skill': skill, **report})
                if report.get('status') != 'learned_hypothesis':
                    all_learned = False
            session['last_reports'] = reports
            session['promoted'] = bool(all_learned)
            session['meta_dependency_schemas']=sorted(set(dependency_schemas))
            self._register_semantics(pattern)
        else:
            reports = list(session.get('last_reports', ()))
            all_learned = bool(session.get('promoted'))

        result = {
            'status': 'procedure_learned' if all_learned else 'procedure_unresolved',
            'pattern': pattern, 'support': support, 'required': self.min_support,
            'duplicate': duplicate, 'promoted': bool(all_learned), 'reports': reports,
            'programs': [r.get('programs', []) for r in reports],
            'meta_dependency_schemas': list(session.get('meta_dependency_schemas',())),
        }
        if not all_learned:
            probe=self.suggest_probe(pattern,0)
            if probe.get('status')=='evidence_probe':
                result['evidence_request']=probe
        self.audit.append({'event':'observe_fit', **deepcopy(result)})
        return result

    def _candidate_dependency_role_sets(self, session: dict, output_index: int = 0):
        """Return cardinality-compatible role subsets not yet contradicted.

        This is a version-space diagnostic, not a learned answer. A subset is
        discarded only when two observed inputs are identical on that subset but
        have different outputs. The target function itself is never inspected.
        """
        if int(session.get('parameter_count',0))!=0:
            return []
        supports=list(session.get('supports',()))
        n=int(session.get('input_arity',0)); out_idx=int(output_index)
        if n<2 or not supports or not 0<=out_idx<int(session.get('output_arity',0)):
            return []
        cardinalities=sorted({int(r.get('cardinality',0)) for r in self.external_role_cardinalities.values()
                              if len(r.get('sources',{}))>=2 and 0<int(r.get('cardinality',0))<n})
        candidates=[]
        for k in cardinalities:
            for roles in combinations(range(n),k):
                consistent=True
                for i,left in enumerate(supports):
                    lb=tuple(left['before']); lo=tuple(left['after'])[out_idx]
                    for right in supports[i+1:]:
                        rb=tuple(right['before']); ro=tuple(right['after'])[out_idx]
                        if all(lb[j]==rb[j] for j in roles) and lo!=ro:
                            consistent=False; break
                    if not consistent: break
                if consistent:
                    candidates.append(tuple(roles))
        return candidates

    def suggest_probe(self, text: str, output_index: int = 0, role_costs=None) -> dict:
        """Propose a target-free numeric intervention that splits role hypotheses.

        The returned state is an *experiment request*: Leobot does not predict its
        output. An external environment/user may execute it and feed the observed
        transition back through :meth:`observe`. This keeps active learning
        auditable and avoids fabricating labels.
        """
        pattern,_params=_surface(text)
        session=self.sessions.get(pattern)
        if session is None:
            return {'status':'no_probe','reason':'unknown_procedure_pattern'}
        if int(session.get('parameter_count',0))!=0:
            return {'status':'no_probe','reason':'parameterized_surface_not_supported'}
        candidates=self._candidate_dependency_role_sets(session,output_index)
        if len(candidates)<2:
            return {'status':'no_probe','reason':'role_version_space_not_ambiguous',
                    'candidate_role_sets':[list(x) for x in candidates]}
        n=int(session.get('input_arity',0)); supports=list(session.get('supports',()))
        # Choose the coordinate whose membership most evenly partitions current
        # hypotheses. Ties are deterministic and therefore reproducible.
        # Prefer coordinates not yet isolated by a controlled one-role
        # intervention. Repeating a role that already produced an invariance or
        # sensitivity witness usually adds less information than testing a new one.
        tested=set()
        for i,left in enumerate(supports):
            lb=tuple(left['before'])
            for right in supports[i+1:]:
                rb=tuple(right['before'])
                diffs=[j for j in range(n) if lb[j]!=rb[j]]
                if len(diffs)==1:
                    tested.add(diffs[0])
        # V6.6: expected information gain per declared intervention cost.
        # With equal costs this preserves the previous balanced-split behaviour;
        # callers may declare a higher real-world cost for manipulating some
        # roles. The outcome itself is never predicted or fabricated.
        def role_cost(role):
            if role_costs is None:
                base=1.0
            elif isinstance(role_costs,dict):
                base=float(role_costs.get(role,1.0))
            else:
                vals=list(role_costs)
                base=float(vals[role]) if role < len(vals) else 1.0
            if not (base > 0.0):
                raise ValueError('Los costos de intervención deben ser positivos.')
            # Prefer unseen interventions when epistemic value is otherwise tied.
            return base*(1.20 if role in tested else 1.0)
        actions=[]
        details=[]
        for role in range(n):
            inside_h=[c for c in candidates if role in c]
            outside_h=[c for c in candidates if role not in c]
            if inside_h and outside_h:
                actions.append({'label':role,'groups':[inside_h,outside_h],'cost':role_cost(role)})
                details.append((role,len(inside_h),len(outside_h)))
        if not actions:
            return {'status':'no_probe','reason':'no_discriminating_role',
                    'candidate_role_sets':[list(x) for x in candidates]}
        if self.meta_controller is not None:
            epistemic=self.meta_controller.select_epistemic_action(candidates,actions)
            if epistemic.get('status')=='epistemic_action':
                pick=int(epistemic['chosen_index']); role=int(actions[pick]['label'])
                inside=sum(role in c for c in candidates); outside=len(candidates)-inside
            else:
                epistemic=None; details.sort(key=lambda x:(x[0] in tested,-min(x[1],x[2]),abs(x[1]-x[2]),x[0]))
                role,inside,outside=details[0]
        else:
            epistemic=None; details.sort(key=lambda x:(x[0] in tested,-min(x[1],x[2]),abs(x[1]-x[2]),x[0]))
            role,inside,outside=details[0]
        base=list(tuple(supports[0]['before']))
        existing={tuple(x['before']) for x in supports}
        proposal=None
        for delta in (1,-1,2,-2,5,11,-11):
            q=list(base); q[role]=int(q[role])+delta
            if tuple(q) not in existing:
                proposal=tuple(q); break
        if proposal is None:
            return {'status':'no_probe','reason':'could_not_construct_novel_intervention'}
        result={'status':'evidence_probe','pattern':pattern,'before':proposal,
                'output_index':int(output_index),'vary_role':role,
                'candidate_role_sets':[list(x) for x in candidates],
                'partition':{'contains_role':inside,'excludes_role':outside},
                'reason':'maximize_expected_information_gain_per_cost' if epistemic else 'maximize_role_hypothesis_disagreement'}
        if epistemic:
            result['epistemic_selection']=epistemic
            result['intervention_cost']=float(actions[int(epistemic['chosen_index'])]['cost'])
        return result

    def _execute_atomic(self, text: str, state: Iterable[int]) -> dict:
        state_t = self._validate_state(state, 'estado')
        pattern, params = _surface(text)
        matches = []
        for variant in self._rewrite_variants(pattern):
            session = self.sessions.get(variant)
            if session is None or not session.get('promoted'):
                continue
            if len(state_t) != session['input_arity'] or len(params) != session['parameter_count']:
                continue
            matches.append((variant, session))
        if not matches:
            return {'status':'unknown_procedure','pattern':pattern,'result':None}
        families = {s.get('semantic_family') for _, s in matches}
        families.discard(None)
        if len(families) > 1:
            return {'status':'ambiguous_procedure','pattern':pattern,'result':None,
                    'alternatives':sorted(v for v,_ in matches)}
        variant, session = sorted(matches, key=lambda item:item[0])[0]
        args = state_t + params
        if len(args) > 4:
            return {'status':'incompatible_state','pattern':pattern,'result':None}
        for counterexample in session.get('counterexamples', ()):
            if (tuple(counterexample['before']) == state_t
                    and tuple(counterexample['params']) == params):
                return {'status':'corrected_conflict','pattern':pattern,
                        'matched_pattern':variant,'result':None,
                        'observed_after':tuple(counterexample['after'])}
        values=[]; details=[]
        for skill in session['output_skills']:
            pred = self.programs.predict(skill, args)
            details.append({'skill':skill, **pred})
            if pred.get('status') not in ('hypothesis',):
                return {'status':'ambiguous_procedure' if pred.get('status')=='ambiguous' else 'unresolved_procedure',
                        'pattern':pattern,'result':None,'details':details}
            values.append(pred['value'])
        result=tuple(values)
        out={'status':'executed','pattern':pattern,'matched_pattern':variant,'result':result,'details':details,
             'composed_paraphrase': variant != pattern}
        self.audit.append({'event':'execute','pattern':pattern,'matched_pattern':variant,'state':list(state_t),
                           'params':list(params),'result':list(result),'composed_paraphrase':variant != pattern})
        return out

    @staticmethod
    def _sequence_clauses(text: str) -> list[str]:
        norm = normalize(text)
        parts = [p.strip() for p in _SEQUENCE_SPLIT.split(norm) if p.strip()]
        return parts if len(parts) >= 2 else []

    def execute(self, text: str, state: Iterable[int]) -> dict:
        """Execute one grounded procedure or a bounded natural-language sequence.

        Sequence composition is deliberately transparent: each clause must map
        to an independently grounded atomic procedure (possibly through learned
        semantic rewrites).  No answer or task-specific plan is hard-coded.
        """
        atomic = self._execute_atomic(text, state)
        if atomic.get('status') != 'unknown_procedure':
            return atomic
        # If this exact full surface has its own unresolved evidence, do not
        # bypass that uncertainty by decomposing it into easier clauses.
        full_pattern, _ = _surface(text)
        if full_pattern in self.sessions:
            return atomic
        if not self.sequence_composition_enabled:
            return atomic
        clauses = self._sequence_clauses(text)
        if not clauses:
            return atomic
        current = self._validate_state(state, 'estado')
        steps = []
        for clause in clauses:
            step = self._execute_atomic(clause, current)
            steps.append({'text':clause, **step})
            if step.get('status') != 'executed':
                return {'status':'unknown_plan','pattern':normalize(text),'result':None,'steps':steps}
            current = tuple(step['result'])
        out = {'status':'executed_plan','pattern':normalize(text),'result':current,'steps':steps}
        self.audit.append({'event':'execute_plan','pattern':normalize(text),'steps':len(steps),'result':list(current)})
        return out

    def correct(self, text: str, before: Iterable[int], after: Iterable[int]) -> dict:
        """Apply an explicit correction to one grounded procedure (from V8.9).

        If the promoted program contradicts the corrected transition, only this
        surface is demoted: its supports, examples and induced programs are
        discarded and it must be re-taught. The correction is retained as
        counterevidence for its exact input, so a later general program cannot
        silently overwrite it. Other procedures are untouched. Without a
        contradiction the correction is an ordinary observation.
        """
        before_t = self._validate_state(before, 'estado inicial')
        after_t = self._validate_state(after, 'estado final')
        pattern, params = _surface(text)
        session = self.sessions.get(pattern)
        if session is None or not session.get('promoted'):
            return self.observe(text, before_t, after_t)
        predicted = self._execute_atomic(text, before_t)
        if predicted.get('status') == 'executed' and tuple(predicted['result']) == after_t:
            return self.observe(text, before_t, after_t)
        session['promoted'] = False
        session['supports'] = []
        session['last_reports'] = []
        counterexamples=session.setdefault('counterexamples',[])
        counterexamples[:]=[row for row in counterexamples
                            if tuple(row['before'])!=before_t or tuple(row['params'])!=params]
        counterexamples.append({'before':list(before_t),'params':list(params),
                                'after':list(after_t)})
        for skill in session.get('output_skills', []):
            for table in (self.programs.examples, self.programs.solutions, self.programs.reports):
                table.pop(skill, None)
        self.audit.append({'event':'correct','pattern':pattern,'before':list(before_t),'after':list(after_t),
                           'predicted':list(predicted['result']) if predicted.get('result') is not None else None})
        return {'status':'procedure_demoted','pattern':pattern,'reason':'counterexample_conflict','promoted':False}

    def observe_goal(self, text: str, goal: Iterable[int]) -> dict:
        """Learn a target-state construction from natural text + observed target.

        Numeric literals are parameters, exactly as in procedure grounding.  No
        hand-authored goal frame or operation label is supplied.
        """
        if not isinstance(text,str) or not text.strip() or len(text)>2048:
            raise ValueError('El objetivo natural debe ser texto no vacío de hasta 2048 caracteres.')
        target=self._validate_state(goal,'objetivo')
        pattern,params=_surface(text)
        if not params:
            return {'status':'goal_unresolved','pattern':pattern,'reason':'La construcción actual necesita al menos un parámetro numérico observable.'}
        if len(params)>4:
            raise ValueError('El sintetizador de objetivos admite como máximo cuatro parámetros numéricos.')
        prefix='goal_'+hashlib.blake2s(pattern.encode('utf8'),digest_size=8).hexdigest()
        session=self.goal_sessions.get(pattern)
        if session is None:
            session={'pattern':pattern,'prefix':prefix,'parameter_count':len(params),'output_arity':len(target),
                     'output_skills':[f'{prefix}_o{i}' for i in range(len(target))],
                     'supports':[],'promoted':False,'last_reports':[]}
            self.goal_sessions[pattern]=session
        expected=(session['parameter_count'],session['output_arity']);actual=(len(params),len(target))
        if expected!=actual:
            raise ValueError('La misma construcción de objetivo produjo una forma incompatible.')
        signature={'params':list(params),'goal':list(target)}
        duplicate=signature in session['supports']
        if not duplicate:
            session['supports'].append(signature)
            concepts=_concepts(pattern)
            for i,value in enumerate(target):
                self.programs.add_example(session['output_skills'][i],params,value,concepts=concepts)
        support=len(session['supports'])
        if support<self.min_support:
            result={'status':'goal_pending','pattern':pattern,'support':support,'required':self.min_support,'duplicate':duplicate}
            self.audit.append({'event':'goal_pending',**result});return result
        reports=[];all_learned=True
        if not duplicate or not session.get('promoted'):
            for skill in session['output_skills']:
                report=self.programs.fit(skill);reports.append({'skill':skill,**report})
                if report.get('status')!='learned_hypothesis':all_learned=False
            session['last_reports']=reports;session['promoted']=bool(all_learned)
        else:
            reports=list(session.get('last_reports',()));all_learned=bool(session.get('promoted'))
        result={'status':'goal_learned' if all_learned else 'goal_unresolved','pattern':pattern,'support':support,
                'required':self.min_support,'duplicate':duplicate,'reports':reports}
        self.audit.append({'event':'goal_fit',**deepcopy(result)});return result

    def resolve_goal(self, text: str) -> dict:
        pattern,params=_surface(text)
        session=self.goal_sessions.get(pattern)
        if session is None or not session.get('promoted'):
            return {'status':'unknown_goal','pattern':pattern,'goal':None}
        if len(params)!=session['parameter_count']:
            return {'status':'incompatible_goal','pattern':pattern,'goal':None}
        values=[];details=[]
        for skill in session['output_skills']:
            pred=self.programs.predict(skill,params);details.append({'skill':skill,**pred})
            if pred.get('status')!='hypothesis':
                return {'status':'unresolved_goal','pattern':pattern,'goal':None,'details':details}
            values.append(pred['value'])
        goal=tuple(values)
        return {'status':'goal_resolved','pattern':pattern,'goal':goal,'details':details}

    def plan_text_goal(self, text: str, state: Iterable[int], max_steps: int = 6, max_nodes: int = 10000) -> dict:
        resolved=self.resolve_goal(text)
        if resolved.get('status')!='goal_resolved':
            return {**resolved,'result':None,'steps':[]}
        planned=self.plan(state,resolved['goal'],max_steps=max_steps,max_nodes=max_nodes)
        return {**planned,'goal_text':text,'resolved_goal':resolved['goal'],'goal_details':resolved.get('details',[])}

    def plan(self, state: Iterable[int], goal: Iterable[int], max_steps: int = 6, max_nodes: int = 10000) -> dict:
        """Find a shortest bounded plan over already-grounded atomic procedures.

        This planner does not invent action semantics: candidate transitions are
        the executable procedures previously learned from observed experience.
        Parameterized actions are intentionally excluded in this first planning
        experiment because an unbounded parameter domain would make enumeration
        ill-defined without an additional proposal mechanism.
        """
        start=self._validate_state(state,'estado')
        target=self._validate_state(goal,'objetivo')
        if len(start)!=len(target):
            return {'status':'incompatible_goal','result':None,'steps':[]}
        max_steps=max(0,int(max_steps)); max_nodes=max(1,int(max_nodes))
        if start==target:
            return {'status':'plan_found','result':start,'steps':[],'nodes':1,'actions_considered':0}
        # One representative per behavioural family avoids exploring lexical
        # synonyms as distinct physical actions.
        representatives={}
        for pattern,session in self.sessions.items():
            if not session.get('promoted') or session.get('parameter_count')!=0:
                continue
            if session.get('input_arity')!=len(start) or session.get('output_arity')!=len(start):
                continue
            family=session.get('semantic_family') or ('surface:'+pattern)
            previous=representatives.get(family)
            if previous is None or pattern < previous:
                representatives[family]=pattern
        actions=sorted(representatives.values())
        if not actions:
            return {'status':'no_actions','result':None,'steps':[],'nodes':1,'actions_considered':0}
        queue=deque([(start,[])])
        visited={start}; nodes=0; transitions=0
        while queue:
            current,path=queue.popleft();nodes+=1
            if nodes>max_nodes:
                return {'status':'plan_budget_exhausted','result':None,'steps':[],
                        'nodes':nodes-1,'actions_considered':transitions,'available_actions':actions}
            if len(path)>=max_steps:
                continue
            for action in actions:
                transitions+=1
                out=self._execute_atomic(action,current)
                if out.get('status')!='executed':
                    continue
                nxt=tuple(out['result'])
                if nxt==current or nxt in visited:
                    continue
                step={'action':action,'before':list(current),'after':list(nxt)}
                new_path=path+[step]
                if nxt==target:
                    result={'status':'plan_found','result':nxt,'steps':new_path,'nodes':nodes,
                            'actions_considered':transitions,'available_actions':actions}
                    self.audit.append({'event':'plan','start':list(start),'goal':list(target),
                                       'steps':len(new_path),'nodes':nodes,'actions_considered':transitions})
                    return result
                visited.add(nxt);queue.append((nxt,new_path))
        return {'status':'goal_unreached','result':None,'steps':[],'nodes':nodes,
                'actions_considered':transitions,'available_actions':actions}

    def as_dict(self) -> dict:
        return {
            'version':9, 'min_support':self.min_support,
            'semantic_rewrites_enabled':self.semantic_rewrites_enabled,
            'sequence_composition_enabled':self.sequence_composition_enabled,
            'max_rewrite_states':self.max_rewrite_states, 'max_rewrite_steps':self.max_rewrite_steps,
            'sessions':deepcopy(self.sessions),'goal_sessions':deepcopy(self.goal_sessions),'audit':deepcopy(self.audit),
            'semantic_families':{k:sorted(v) for k,v in self.semantic_families.items()},
            'rewrite_evidence':{k:[[list(a),list(b)] for a,b in rules] for k,rules in self.rewrite_evidence.items()},
            'external_permutation_schemas':deepcopy(self.external_permutation_schemas),
            'external_projection_schemas':deepcopy(self.external_projection_schemas),
            'external_role_sets':deepcopy(self.external_role_sets),
            'external_role_cardinalities':deepcopy(self.external_role_cardinalities),
            'dependency_search_stats':deepcopy(self.dependency_search_stats),
            'rbf_strategy_enabled':self.rbf_strategy_enabled,
            'rbf_strategy_router':self.rbf_strategy_router.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict, programs: ProgramLearner) -> 'ProcedureGrounder':
        version=data.get('version',1)
        if version not in (1,2,3,4,5,6,7,8,9):
            raise ValueError('Estado de grounding de procedimientos no compatible.')
        obj=cls(programs,min_support=data.get('min_support',3),
                semantic_rewrites=data.get('semantic_rewrites_enabled',True),
                sequence_composition=data.get('sequence_composition_enabled',True),
                max_rewrite_states=data.get('max_rewrite_states',64),
                max_rewrite_steps=data.get('max_rewrite_steps',3))
        obj.sessions=deepcopy(data.get('sessions',{}))
        obj.goal_sessions=deepcopy(data.get('goal_sessions',{}))
        obj.audit=deepcopy(data.get('audit',[]))
        if version >= 2:
            obj.semantic_families=defaultdict(set,{k:set(v) for k,v in data.get('semantic_families',{}).items()})
            obj.rewrite_evidence={k:[(tuple(a),tuple(b)) for a,b in rules]
                                  for k,rules in data.get('rewrite_evidence',{}).items()}
            obj._rebuild_rewrite_union()
        else:
            # Backward-compatible load: rebuild semantic families/rewrite evidence
            # from the promoted V3.2 sessions without changing learned programs.
            for pattern, session in list(obj.sessions.items()):
                if session.get('promoted'):
                    obj._register_semantics(pattern)
        obj.external_permutation_schemas=deepcopy(data.get('external_permutation_schemas',{})) if version>=4 else {}
        obj.external_projection_schemas=deepcopy(data.get('external_projection_schemas',{})) if version>=5 else {}
        obj.external_role_sets=deepcopy(data.get('external_role_sets',{})) if version>=6 else {}
        obj.external_role_cardinalities=deepcopy(data.get('external_role_cardinalities',{})) if version>=8 else {}
        obj.dependency_search_stats=deepcopy(data.get('dependency_search_stats',{})) if version>=7 else {}
        if version>=9:
            obj.rbf_strategy_enabled=bool(data.get('rbf_strategy_enabled',True))
            obj.rbf_strategy_router=RBFStrategyRouter.from_dict(data.get('rbf_strategy_router',{}))
        return obj

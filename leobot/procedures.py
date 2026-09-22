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

from .language import normalize
from .programs import ProgramLearner, LIMIT, Expr, COMMUTATIVE

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
            result = {
                'status': 'procedure_pending', 'pattern': pattern, 'support': support,
                'required': self.min_support, 'duplicate': duplicate, 'promoted': False,
            }
            self.audit.append({'event':'observe_pending', **result})
            return result

        reports = []
        all_learned = True
        if not duplicate or not session.get('promoted'):
            for skill in session['output_skills']:
                report = self.programs.fit(skill)
                reports.append({'skill': skill, **report})
                if report.get('status') != 'learned_hypothesis':
                    all_learned = False
            session['last_reports'] = reports
            session['promoted'] = bool(all_learned)
            self._register_semantics(pattern)
        else:
            reports = list(session.get('last_reports', ()))
            all_learned = bool(session.get('promoted'))

        result = {
            'status': 'procedure_learned' if all_learned else 'procedure_unresolved',
            'pattern': pattern, 'support': support, 'required': self.min_support,
            'duplicate': duplicate, 'promoted': bool(all_learned), 'reports': reports,
            'programs': [r.get('programs', []) for r in reports],
        }
        self.audit.append({'event':'observe_fit', **deepcopy(result)})
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
            'version':3, 'min_support':self.min_support,
            'semantic_rewrites_enabled':self.semantic_rewrites_enabled,
            'sequence_composition_enabled':self.sequence_composition_enabled,
            'max_rewrite_states':self.max_rewrite_states, 'max_rewrite_steps':self.max_rewrite_steps,
            'sessions':deepcopy(self.sessions),'goal_sessions':deepcopy(self.goal_sessions),'audit':deepcopy(self.audit),
            'semantic_families':{k:sorted(v) for k,v in self.semantic_families.items()},
            'rewrite_evidence':{k:[[list(a),list(b)] for a,b in rules] for k,rules in self.rewrite_evidence.items()},
        }

    @classmethod
    def from_dict(cls, data: dict, programs: ProgramLearner) -> 'ProcedureGrounder':
        version=data.get('version',1)
        if version not in (1,2,3):
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
        return obj

"""Conversation facade, persistence and dataset ingestion. No network operations."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import tempfile
from itertools import permutations
from .core import Atom, KnowledgeBase, Engine, Proof
from .learning import RelationalLearner
from .programs import ProgramLearner
from .procedures import ProcedureGrounder
from .symbolic import SymbolicWorldLearner
from .concepts import ConceptGrounder
from .language import Language, normalize


class Bot:
    def __init__(self, kb=None, grounded_language: bool = True, grounding_min_support: int = 2) -> None:
        self.kb, self.language, self.programs = (kb if kb is not None else KnowledgeBase()), Language(), ProgramLearner()
        self.procedures = ProcedureGrounder(self.programs)
        self.symbolic = SymbolicWorldLearner()
        self.concepts = ConceptGrounder(self.kb)
        self.grounded_language = bool(grounded_language)
        self.grounding_min_support = max(1, int(grounding_min_support))
        # Untrusted semantic hypotheses are kept separate from active grammar until
        # independent grounded episodes support the same delexicalized construction.
        self.grounding_hypotheses: dict[str, dict] = {}
        self.last_fact: str | None = None
        self.last_result: dict | None = None
        self.training_reports: list[dict] = []

    def ingest(self, data: dict) -> dict:
        counts = {'constructions': 0, 'facts': 0, 'relational_examples': 0, 'numeric_examples': 0}
        for e in data.get('language', []):
            counts['constructions'] += self.language.teach(e['text'], e['frame'], 'dataset_annotation')
        for f in data.get('facts', []):
            before = self.kb.stats()['facts']
            self.last_fact = self.kb.add(Atom.from_dict(f), f.get('source', 'dataset'))
            counts['facts'] += self.kb.stats()['facts'] - before
        changed_rel, changed_num = [], []
        for e in data.get('relational_examples', []):
            changed = self.kb.add_example(e['target'], tuple(e['args']), e['positive'])
            counts['relational_examples'] += changed
            if changed and e['target'] not in changed_rel:
                changed_rel.append(e['target'])
        for e in data.get('numeric_examples', []):
            changed = self.programs.add_example(e['skill'], tuple(e['inputs']), e['output'], e.get('concepts'))
            counts['numeric_examples'] += changed
            if changed and e['skill'] not in changed_num:
                changed_num.append(e['skill'])
        reports = []
        # Explicit ordering permits learning a skill, then using it as a primitive.
        requested = data.get('learn', changed_rel)
        for request in requested:
            spec = {'target': request} if isinstance(request, str) else request
            target = spec['target']
            if target in changed_rel or not any(r.head.pred == target and r.origin == 'learned' for r in self.kb.rules.values()):
                opts = {k: spec[k] for k in ('max_length', 'max_candidates', 'max_pairs', 'max_seconds') if k in spec}
                reports.append(RelationalLearner(self.kb, **opts).fit(target, allowed=spec.get('allowed')))
        for skill in changed_num:
            reports.append({'skill': skill, **self.programs.fit(skill)})
        self.training_reports.extend(reports)
        return {'added': counts, 'training': reports, 'memory': self.kb.stats()}

    @staticmethod
    def _question_like(text: str) -> bool:
        norm = normalize(text)
        starts = ('que ', 'cual ', 'donde ', 'cuando ', 'quien ', 'cuanto ', 'como ',
                  'en que ', 'a que ', 'de que ', 'por que ')
        return '?' in text or '¿' in text or any(norm.startswith(x) for x in starts)

    def _entities_mentioned(self, text: str) -> set[str]:
        """Retrieve known entities by bounded n-grams, never by full KB scan."""
        tokens = normalize(text).split()
        if not tokens or len(tokens) > 48:
            return set()
        candidates = set()
        for width in range(1, min(4, len(tokens)) + 1):
            for i in range(len(tokens) - width + 1):
                candidates.add(' '.join(tokens[i:i+width]))
        if hasattr(self.kb, 'known_entities'):
            return set(self.kb.known_entities(candidates))
        # Compatibility fallback for custom KB implementations.
        return {x for x in candidates if self.kb.predicates_for_entities({x})}

    @staticmethod
    def _grounding_signature(text: str, frame: dict) -> tuple[str, str] | None:
        """Return a delexicalized surface+semantic key for grounded induction.

        Concrete argument values are replaced by markers tied to their semantic
        argument position.  This lets independent entity pairs support the same
        construction while preserving role/order information.
        """
        norm = normalize(text)
        args = list(frame.get('args', []))
        spans = []
        used: set[int] = set()
        for pos, value in enumerate(args):
            if isinstance(value, str) and value.startswith('?'):
                continue
            needle = normalize(str(value))
            hits = [m for m in re.finditer(r'(?<!\w)' + re.escape(needle) + r'(?!\w)', norm)
                    if not used.intersection(range(m.start(), m.end()))]
            if len(hits) != 1:
                return None
            m = hits[0]
            used.update(range(m.start(), m.end()))
            spans.append((m.start(), m.end(), f'<a{pos}>'))
        spans.sort()
        parts=[]; cursor=0
        for a,b,marker in spans:
            parts.extend((norm[cursor:a], marker)); cursor=b
        parts.append(norm[cursor:])
        surface=''.join(parts)
        semantic={'act':frame.get('act'),'pred':frame.get('pred'),'arity':len(args),
                  'unknown':[i for i,v in enumerate(args) if isinstance(v,str) and v.startswith('?')]}
        return surface, json.dumps(semantic,sort_keys=True,ensure_ascii=False,separators=(',',':'))

    def _record_grounding_candidates(self, text: str, choices: list[dict]) -> dict | None:
        """Update a contrastive version space from one grounded episode.

        Each episode may support several semantic hypotheses.  Hypotheses are
        generalized by replacing concrete entities with role markers, then the
        candidate set is intersected across independent episodes with the same
        delexicalized surface.  Promotion occurs only when one hypothesis remains
        and the independent-support threshold has been reached.
        """
        grouped: dict[str, dict[str, dict]] = {}
        all_evidence=set()
        for chosen in choices:
            sig=self._grounding_signature(text, chosen['frame'])
            if sig is None:
                continue
            surface,semantic_json=sig
            generic_surface=re.sub(r'<a\d+>', '<slot>', surface)
            semantic=json.loads(semantic_json)
            cluster=json.dumps({'surface':generic_surface,'act':semantic.get('act')},
                               sort_keys=True,ensure_ascii=False,separators=(',',':'))
            hyp_key=json.dumps({'surface':surface,'semantic':semantic},
                               sort_keys=True,ensure_ascii=False,separators=(',',':'))
            grouped.setdefault(cluster,{})[hyp_key]=chosen
            all_evidence.update(chosen.get('evidence',()))
        if not grouped:
            return None
        episode_id=json.dumps({'text':normalize(text),'evidence':sorted(all_evidence)},
                              sort_keys=True,ensure_ascii=False,separators=(',',':'))
        promoted_any=False; pending=[]
        for cluster,current in grouped.items():
            state=self.grounding_hypotheses.get(cluster)
            if not isinstance(state,dict) or 'possible' not in state:
                state={'possible':sorted(current),'observations':[],'promoted':False,'conflict':False}
                self.grounding_hypotheses[cluster]=state
            if any(o.get('episode_id')==episode_id for o in state.get('observations',[])):
                pending.append(state)
                continue
            previous=set(state.get('possible',[]))
            now=set(current)
            possible=now if not state.get('observations') else previous & now
            observation={'episode_id':episode_id,'text':text,
                         'candidates':{k:{'frame':v['frame'],'evidence':list(v['evidence'])}
                                       for k,v in current.items()}}
            state.setdefault('observations',[]).append(observation)
            state['possible']=sorted(possible)
            if not possible:
                state['conflict']=True
                pending.append(state)
                continue
            if len(possible)==1 and len(state['observations']) >= self.grounding_min_support and not state.get('promoted'):
                winner=next(iter(possible)); changed=False
                supports=[]
                for obs in state['observations']:
                    detail=obs['candidates'].get(winner)
                    if detail is None:
                        continue
                    supports.append(detail)
                    try:
                        changed=self.language.teach(obs['text'],detail['frame'],'grounded_induction',detail['evidence']) or changed
                    except ValueError:
                        state['conflict']=True
                        return None
                if len(supports) >= self.grounding_min_support:
                    state['promoted']=True; promoted_any=True
                    self.training_reports.append({'type':'language_grounded_promoted','text':text,
                                                  'hypothesis':winner,'support':len(supports),
                                                  'possible_before_promotion':1})
            else:
                pending.append(state)
        if promoted_any:
            parsed=self.language.parse(text)
            if parsed['status']=='parsed':
                parsed['grounded_induction']={'learned':True,'pending':False,
                    'required':self.grounding_min_support,'candidate_count':len(choices),
                    'version_space':True}
                return parsed
        active=[s for s in pending if not s.get('conflict')]
        if active:
            best=min(active,key=lambda st:(len(st.get('possible',[])) or 10**9,-len(st.get('observations',[]))))
            poss=len(best.get('possible',[])); support=len(best.get('observations',[]))
            self.training_reports.append({'type':'language_grounded_pending','text':text,
                                          'support':support,'required':self.grounding_min_support,
                                          'possible':poss,'version_space':True})
            return {'status':'grounding_pending','frame':None,'alternatives':[],
                    'grounded_induction':{'learned':False,'pending':True,'support':support,
                                          'required':self.grounding_min_support,'possible':poss,
                                          'candidate_count':len(choices),'version_space':True}}
        return None

    def _try_grounded_language(self, text: str) -> dict | None:
        """Induce a construction from independently repeated grounded evidence.

        Candidate meanings come only from already-known facts whose concrete
        entities occur in the utterance.  A unique candidate becomes an untrusted
        hypothesis first; it enters the active grammar only after independent
        supports reach ``grounding_min_support``.  Both positive and explicitly
        negative facts are considered.
        """
        entities = self._entities_mentioned(text)
        if not entities or len(entities) > 8:
            return None
        pred_scores = self.kb.predicates_for_entities(entities)
        if not pred_scores:
            return None
        candidates: dict[str, dict] = {}
        checks = 0; max_checks = 768
        question = self._question_like(text)
        ordered_entities = sorted(entities, key=lambda x: (-len(x), x))
        for base_pred, _ in sorted(pred_scores.items(), key=lambda kv: (-kv[1], kv[0])):
            arity = int(getattr(self.kb, 'arity', {}).get(base_pred, 0) or 0)
            if not 1 <= arity <= 4:
                continue
            if not question and pred_scores.get(base_pred, 0) < arity:
                continue
            for pred in (base_pred, '!' + base_pred):
                if question:
                    bound_count = arity - 1
                    if bound_count > len(ordered_entities):
                        continue
                    bound_rows = [()] if bound_count == 0 else permutations(ordered_entities, bound_count)
                    for bound in bound_rows:
                        for unknown_pos in range(arity):
                            checks += 1
                            if checks > max_checks:
                                return None
                            vals = iter(bound); args=[]
                            for pos in range(arity):
                                args.append('?answer' if pos == unknown_pos else next(vals))
                            rows=[]
                            for fact in self.kb.matches(Atom(pred, tuple(args))):
                                rows.append(fact)
                                if len(rows) >= 4:
                                    break
                            if not rows:
                                continue
                            frame={'act':'query','pred':pred,'args':args}
                            key=json.dumps(frame,sort_keys=True,ensure_ascii=False)
                            candidates[key]={'frame':frame,'evidence':[r['id'] for r in rows]}
                else:
                    if arity > len(ordered_entities):
                        continue
                    for args in permutations(ordered_entities, arity):
                        checks += 1
                        if checks > max_checks:
                            return None
                        fact = next(self.kb.matches(Atom(pred, tuple(args))), None)
                        if fact is None:
                            continue
                        frame={'act':'assert','pred':pred,'args':list(args)}
                        key=json.dumps(frame,sort_keys=True,ensure_ascii=False)
                        candidates[key]={'frame':frame,'evidence':[fact['id']]}
        if not candidates:
            return None
        return self._record_grounding_candidates(text, list(candidates.values()))


    def observe_concept_statement(self, text: str) -> dict:
        """Learn a previously unnamed relation from an ordinary natural assertion."""
        report = self.concepts.observe(text)
        self.training_reports.append({'type': 'concept_grounding', 'text': text, **report})
        return report

    def query_concept(self, text: str) -> dict:
        """Resolve a natural yes/no relation utterance against an invented concept."""
        return self.concepts.resolve(text)

    def observe_transition(self, text: str, before, after) -> dict:
        """Learn an action meaning from a natural utterance and an observed state change."""
        report = self.procedures.observe(text, before, after)
        self.training_reports.append({'type':'procedure_grounding', **report})
        return report

    def execute_transition(self, text: str, state) -> dict:
        """Apply a grounded action cue to a new observable state."""
        return self.procedures.execute(text, state)

    def plan_transition(self, state, goal, max_steps: int = 6, max_nodes: int = 10000) -> dict:
        """Plan over learned grounded actions toward an explicit target state."""
        return self.procedures.plan(state, goal, max_steps=max_steps, max_nodes=max_nodes)

    def observe_goal(self, text: str, goal) -> dict:
        """Learn the meaning of a natural-language goal from an observed target state."""
        report=self.procedures.observe_goal(text,goal)
        self.training_reports.append({'type':'goal_grounding',**report})
        return report

    def plan_goal(self, text: str, state, max_steps: int = 6, max_nodes: int = 10000) -> dict:
        """Resolve a learned natural-language goal and plan using acquired actions."""
        return self.procedures.plan_text_goal(text,state,max_steps=max_steps,max_nodes=max_nodes)

    def observe_symbolic_transition(self, text: str, before, after) -> dict:
        """Learn a factual action model from natural language + observed state change."""
        report = self.symbolic.observe(text, before, after)
        self.training_reports.append({'type':'symbolic_transition', 'text':text, 'report':report})
        return report

    def execute_symbolic_transition(self, text: str, state) -> dict:
        return self.symbolic.execute(text, state)

    def observe_symbolic_goal(self, text: str, goal) -> dict:
        report = self.symbolic.observe_goal(text, goal)
        self.training_reports.append({'type':'symbolic_goal', 'text':text, 'report':report})
        return report

    def plan_symbolic(self, state, goal, max_steps: int = 8, max_nodes: int = 20_000, use_macros: bool = True, use_iterations: bool = True, max_iterative_steps: int = 10_000) -> dict:
        return self.symbolic.plan(state, goal, max_steps=max_steps, max_nodes=max_nodes, use_macros=use_macros, use_iterations=use_iterations, max_iterative_steps=max_iterative_steps)

    def learn_symbolic_macro(self, state, goal, max_steps: int = 12, max_nodes: int = 50_000) -> dict:
        """Solve with primitives, verify the trace, and offer it as hierarchy experience."""
        plan=self.symbolic.plan(state,goal,max_steps=max_steps,max_nodes=max_nodes,use_macros=False)
        report=self.symbolic.observe_plan(state,goal,plan)
        self.training_reports.append({'type':'symbolic_macro','report':report})
        return {'plan':plan,'learning':report}

    def learn_symbolic_iteration(self, state, goal, max_steps: int = 64, max_nodes: int = 100_000) -> dict:
        """Solve with primitives only, then offer the verified repeated trace as variable-length evidence."""
        plan=self.symbolic.plan(state,goal,max_steps=max_steps,max_nodes=max_nodes,use_macros=False,use_iterations=False)
        report=self.symbolic.observe_iterative_plan(plan)
        self.training_reports.append({'type':'symbolic_iteration','report':report})
        return {'plan':plan,'learning':report}

    def plan_symbolic_goal(self, text: str, state, max_steps: int = 8, max_nodes: int = 20_000, use_macros: bool = True, use_iterations: bool = True) -> dict:
        return self.symbolic.plan_goal(text, state, max_steps=max_steps, max_nodes=max_nodes, use_macros=use_macros, use_iterations=use_iterations)

    def answer_atom(self, atom: Atom) -> dict:
        result = Engine(self.kb).answer(atom)
        self.last_result = result
        status = result['status']
        proofs = result['positive']['answers']
        if status == 'unknown':
            text = 'No tengo información suficiente para afirmarlo ni negarlo.'
        elif status in ('conflict', 'contested'):
            text = 'Hay información contradictoria en esta conclusión o en sus condiciones. No la presentaré como un hecho seguro.'
        elif status == 'incomplete':
            text = 'La búsqueda alcanzó un límite. El resultado es incompleto; no equivale a una respuesta negativa.'
        elif status == 'refuted':
            text = 'Tengo evidencia explícita en contra de: ' + self.language.describe(atom.pred, atom.args) + '.'
        elif status == 'negative_hypothesis':
            text = 'Una regla aprendida sugiere una respuesta negativa, pero sigue siendo una hipótesis.'
        elif proofs:
            descriptions = [self.language.describe(p.atom.pred, p.atom.args) for p in proofs[:12]]
            prefix = 'Según la hipótesis aprendida: ' if any(p.hypothesis for p in proofs) else 'Según la información registrada: '
            text = prefix + '; '.join(descriptions) + '.'
            if len(proofs) > 12:
                text += f' Hay {len(proofs) - 12} resultados adicionales en la traza.'
        else:
            text = 'No encontré resultados; eso no demuestra que no existan.'
        return {'text': text, 'status': status, 'proofs': [p.as_dict(self.kb) for p in proofs],
                'negative_proofs': [p.as_dict(self.kb) for p in (result['negative']['answers'] if result['negative'] else [])],
                'stats': result['positive']['stats']}

    def explain(self) -> dict:
        if self.last_result is None:
            return {'text': 'Todavía no hay una consulta que explicar.', 'status': 'unknown'}
        proofs = self.last_result['positive']['answers']
        if not proofs and self.last_result['negative']:
            proofs = self.last_result['negative']['answers']
        lines = []
        seen = set()
        stack = [(p, 0) for p in reversed(proofs)]
        while stack and len(lines) < 80:
            p, indent = stack.pop()
            key = (p.atom, p.id)
            if key in seen:
                continue
            seen.add(key)
            if p.kind == 'fact':
                source = self.kb.fact_source(p.id) if hasattr(self.kb, 'fact_source') else 'retirado'
                lines.append('  ' * indent + f'{p.atom}: dato {p.id}, fuente {source}.')
            elif p.kind == 'compiled':
                lines.append('  ' * indent + f'{p.atom}: cierre transitivo compilado por BFS indexado.')
            else:
                r = self.kb.rules.get(p.id)
                if r:
                    lines.append('  ' * indent + f'{r.origin}: {r}')
            for child in reversed(p.children):
                stack.append((child, indent + 1))
        return {'text': '\n'.join(lines) or 'No hay una prueba positiva ni negativa.', 'status': 'trace'}

    def respond(self, text: str) -> dict:
        parsed = self.language.parse(text)
        # A concept surface that has already been learned is more specific than
        # a still-pending generic grounding hypothesis.  Resolve it before the
        # generic grounding route can absorb the utterance.
        if parsed['status'] == 'unrecognized' and self._question_like(text):
            concept = self.query_concept(text)
            if concept.get('status') in ('entailed','contradicted','contested','unknown'):
                messages = {
                    'entailed': 'Sí: puedo deducir esa relación del conocimiento aprendido.',
                    'contradicted': 'Tengo evidencia explícita para la relación contraria.',
                    'contested': 'La evidencia disponible es contradictoria.',
                    'unknown': 'No puedo deducir esa relación con el conocimiento actual.',
                }
                return {'text': messages[concept['status']], **concept}
        if self.grounded_language and parsed['status'] == 'parsed':
            # A broad slot can sometimes absorb words that should have been fixed
            # structure.  When the utterance mentions already-known entities that
            # disappear from the parsed concrete arguments, let grounded evidence
            # challenge the existing construction instead of silently trusting it.
            frame=parsed.get('frame') or {}
            if frame.get('act') in ('assert','query'):
                mentioned=self._entities_mentioned(text)
                concrete={normalize(str(v)) for v in frame.get('args',[])
                          if not (isinstance(v,str) and v.startswith('?'))}
                if mentioned and not mentioned.issubset(concrete):
                    grounded=self._try_grounded_language(text)
                    if grounded is not None:
                        parsed=grounded
        if parsed['status'] == 'unrecognized' and self.grounded_language:
            grounded = self._try_grounded_language(text)
            if grounded is not None:
                parsed = grounded
        # Generic grounding may remain ambiguous while the concept learner has
        # accumulated enough contrastive evidence for a specific surface.  Let
        # the specific concept hypothesis promote/withdraw without discarding the
        # older grounding version-space.  Pending concept evidence alone does not
        # override the historical grounding_pending response.
        if parsed['status'] == 'grounding_pending' and not self._question_like(text):
            concept = self.observe_concept_statement(text)
            if concept.get('status') in ('concept_learned','concept_unresolved','concept_contradictory',
                                         'concept_alias_learned','concept_alias_confirmed','concept_alias_withdrawn'):
                messages = {
                    'concept_learned': 'Aprendí una hipótesis relacional nueva a partir de los ejemplos y del contexto factual.',
                    'concept_unresolved': 'Registré el concepto, pero todavía no encontré una definición relacional que explique los ejemplos.',
                    'concept_contradictory': 'Los ejemplos de esa relación son contradictorios.',
                    'concept_alias_learned': 'La nueva formulación es compatible de forma única con una relación ya aprendida y quedó vinculada como hipótesis reutilizable.',
                    'concept_alias_confirmed': 'La nueva evidencia sigue siendo compatible con la relación aprendida.',
                    'concept_alias_withdrawn': 'La nueva evidencia contradijo la equivalencia lingüística anterior; retiré ese alias sin borrar la relación original.',
                }
                return {'text': messages[concept['status']], **concept}
        if parsed['status'] != 'parsed' and parsed['status'] != 'grounding_pending':
            if self._question_like(text):
                concept = self.query_concept(text)
                if concept.get('status') in ('entailed','contradicted','contested','unknown'):
                    messages = {
                        'entailed': 'Sí: puedo deducir esa relación del conocimiento aprendido.',
                        'contradicted': 'Tengo evidencia explícita para la relación contraria.',
                        'contested': 'La evidencia disponible es contradictoria.',
                        'unknown': 'No puedo deducir esa relación con el conocimiento actual.',
                    }
                    return {'text': messages[concept['status']], **concept}
            else:
                concept = self.observe_concept_statement(text)
                if concept.get('status') in ('concept_pending','concept_learned','concept_unresolved','concept_contradictory',
                                                 'concept_alias_learned','concept_alias_confirmed','concept_alias_withdrawn'):
                    messages = {
                        'concept_pending': 'Registré el ejemplo como una posible relación nueva, pero aún falta evidencia contrastiva.',
                        'concept_learned': 'Aprendí una hipótesis relacional nueva a partir de los ejemplos y del contexto factual.',
                        'concept_unresolved': 'Registré el concepto, pero todavía no encontré una definición relacional que explique los ejemplos.',
                        'concept_contradictory': 'Los ejemplos de esa relación son contradictorios.',
                        'concept_alias_learned': 'La nueva formulación es compatible de forma única con una relación ya aprendida y quedó vinculada como hipótesis reutilizable.',
                        'concept_alias_confirmed': 'La nueva evidencia sigue siendo compatible con la relación aprendida.',
                        'concept_alias_withdrawn': 'La nueva evidencia contradijo la equivalencia lingüística anterior; retiré ese alias sin borrar la relación original.',
                    }
                    return {'text': messages[concept['status']], **concept}
        if parsed['status'] != 'parsed':
            if parsed['status'] == 'grounding_pending':
                g=parsed.get('grounded_induction',{})
                return {'text': f'Tengo una hipótesis de significado respaldada por {g.get("support",0)} experiencia(s), pero todavía no la usaré como conocimiento lingüístico hasta reunir {g.get("required",self.grounding_min_support)} apoyos independientes.',
                        'status':'grounding_pending','grounded_induction':g}
            message = ('Esa frase admite varias interpretaciones aprendidas. Necesito una formulación más precisa.'
                       if parsed['status'] == 'ambiguous' else
                       'No sé interpretar esa formulación todavía. Puedes enseñarme una construcción con texto y significado, o usar /consulta.')
            return {'text': message, 'status': parsed['status']}
        frame = parsed['frame']
        action = frame['act']
        if action == 'query':
            return self.answer_atom(Atom(frame['pred'], tuple(frame['args'])))
        if action == 'assert':
            self.last_fact = self.kb.add(Atom(frame['pred'], tuple(frame['args'])), 'conversación')
            # Avoid a stale conversational explanation after new information.
            self.last_result = None
            return {'text': 'Dato registrado con su procedencia.', 'status': 'stored', 'id': self.last_fact}
        if action == 'correct_last':
            if not self.last_fact:
                return {'text': 'No hay un dato anterior inequívoco que pueda corregir.', 'status': 'unknown'}
            old_fact = self.kb.get_fact(self.last_fact) if hasattr(self.kb, 'get_fact') else None
            if old_fact is None:
                return {'text': 'El dato anterior ya no existe.', 'status': 'unknown'}
            old = old_fact['atom']
            args, slot = list(old.args), frame['slot']
            if type(slot) is not int or not 0 <= slot < len(args):
                return {'text': 'La corrección no corresponde al dato anterior.', 'status': 'unrecognized'}
            args[slot] = str(frame['value'])
            self.last_fact = self.kb.replace(self.last_fact, Atom(old.pred, tuple(args)))
            self.last_result = None
            return {'text': 'Corrección aplicada: ' + self.language.describe(old.pred, tuple(args)) + '.', 'status': 'corrected'}
        if action == 'calculate':
            answer = self.programs.predict(frame['skill'], tuple(frame['values']))
            if answer['status'] == 'hypothesis':
                message = f'Resultado según el procedimiento aprendido: {answer["value"]}. Regla: {answer["programs"][0]}.'
            elif answer['status'] == 'ambiguous':
                message = f'Los procedimientos compatibles discrepan: {answer["alternatives"]}. Necesito otro ejemplo para distinguirlos.'
            elif answer['status'] == 'contradictory_examples':
                message = 'Los ejemplos enseñan resultados contradictorios para la misma entrada.'
            else:
                message = 'No tengo un procedimiento válido para resolver eso dentro del presupuesto actual.'
            return {'text': message, **answer}
        if action == 'explain':
            return self.explain()
        return {'text': 'El acto comunicativo anotado no está implementado.', 'status': 'unrecognized'}

    def as_dict(self) -> dict:
        return {'version': 1, 'kb': self.kb.as_dict(), 'language': self.language.as_dict(),
                'grounded_language': self.grounded_language,
                'grounding_min_support': self.grounding_min_support,
                'grounding_hypotheses': self.grounding_hypotheses,
                'programs': self.programs.as_dict(), 'procedures': self.procedures.as_dict(),
                'symbolic': self.symbolic.as_dict(), 'concepts': self.concepts.as_dict(), 'last_fact': self.last_fact,
                'training_reports': self.training_reports}

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as out:
                json.dump(self.as_dict(), out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: str | Path) -> Bot:
        path = Path(path)
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('La memoria excede el límite de carga de 100 MiB.')
        data = json.loads(path.read_text(encoding='utf8'))
        if data.get('version') != 1:
            raise ValueError('Formato de bot no compatible.')
        bot = cls(grounded_language=data.get('grounded_language', True),
                  grounding_min_support=data.get('grounding_min_support', 2))
        bot.kb = KnowledgeBase.from_dict(data['kb'])
        bot.language = Language.from_dict(data['language'])
        bot.programs = ProgramLearner.from_dict(data['programs'])
        bot.procedures = ProcedureGrounder.from_dict(data.get('procedures', {}), bot.programs)
        bot.symbolic = SymbolicWorldLearner.from_dict(data.get('symbolic', {}))
        bot.concepts = ConceptGrounder.from_dict(data.get('concepts', {}), bot.kb)
        bot.last_fact = data.get('last_fact')
        bot.grounding_hypotheses = data.get('grounding_hypotheses', {})
        bot.training_reports = data.get('training_reports', [])
        return bot

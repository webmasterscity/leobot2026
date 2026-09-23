"""Leobot state, learner wiring, persistence, and public facade."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .core import Atom, KnowledgeBase, Engine
from .learning import RelationalLearner
from .programs import ProgramLearner
from .procedures import ProcedureGrounder
from .symbolic import SymbolicWorldLearner
from .concepts import ConceptGrounder
from .schemas import OpenArityConceptGrounder
from .metarepr import MetaRepresentationLibrary
from .metacontrol import MetaController
from .language import Language, normalize
from .document import DocumentLearningMixin
from .language_acquisition import LanguageAcquisitionMixin
from .conditional_learning import ConditionalLearningMixin
from .dialogue import DialogueMixin
from .state_fields import plain_state, restore_plain_state


class Bot(DocumentLearningMixin, LanguageAcquisitionMixin, ConditionalLearningMixin, DialogueMixin):
    def __init__(self, kb=None, grounded_language: bool = True, grounding_min_support: int = 2,
                 raw_relation_min_support: int = 3, allow_extensional_grounding: bool = False,
                 raw_relation_max_arity: int = 8) -> None:
        self.kb, self.language, self.programs = (kb if kb is not None else KnowledgeBase()), Language(), ProgramLearner()
        self.procedures = ProcedureGrounder(self.programs)
        self.symbolic = SymbolicWorldLearner()
        self.concepts = ConceptGrounder(self.kb)
        self.schemas = OpenArityConceptGrounder(self.kb)
        # V6.0-V6.2: domain-free structural priors shared between learners.
        self.meta_representations = MetaRepresentationLibrary()
        self.meta_controller = MetaController()
        self._sync_meta_controller()
        self.grounded_language = bool(grounded_language)
        # Legacy V3 extensional grounding can map arbitrary new wording onto an
        # existing predicate from co-occurrence alone.  That is underdetermined
        # semantics, so it is reproducible only by explicit opt-in and is not on
        # the default operational path.
        self.allow_extensional_grounding = bool(allow_extensional_grounding)
        self.grounding_min_support = max(1, int(grounding_min_support))
        self.raw_relation_min_support = max(3, int(raw_relation_min_support))
        self.raw_relation_max_arity = max(1, min(8, int(raw_relation_max_arity)))
        # Untrusted semantic hypotheses are kept separate from active grammar until
        # independent grounded episodes support the same delexicalized construction.
        self.grounding_hypotheses: dict[str, dict] = {}
        # V4.5: unresolved ordinary assertions can support a bounded, opaque
        # primitive relation.  Pending raw text is data, never executable code.
        self.raw_relation_observations: list[dict] = []
        self.raw_relation_promotions: dict[str, dict] = {}
        # Raw relational roles may be linked to independently observed changes.
        # This stores evidence and conflicts, never a translated predicate name.
        self.raw_world_alignment_hypotheses: dict[str, dict] = {}
        # V5.11: negative raw assertions are learned in a separate evidence pool so
        # they can never count as positive support.  If repeated negative wording
        # reveals one stable base relation, only !predicate facts are asserted.
        self.raw_negative_relation_observations: list[dict] = []
        # V5.5: learned meta-schemas for safe question syntax. A transform is
        # promoted only after two distinct grounded predicates support the same
        # abstract assertion->query topology.
        self.question_transform_hypotheses: dict[str, dict] = {}
        # V5.6: natural conditional examples can induce a Horn rule only after
        # several independent grounded episodes agree on the same role mapping.
        # The conditional itself never asserts its antecedent or consequent as fact.
        self.conditional_rule_hypotheses: dict[str, dict] = {}
        # V5.8: unresolved single-antecedent conditionals may teach opaque clause
        # constructions from repeated hypothetical episodes.  These observations
        # never become facts; they only bootstrap language forms, after which the
        # ordinary grounded conditional learner must still induce the rule.
        self.conditional_bootstrap_observations: list[dict] = []
        self.conditional_bootstrap_promotions: list[dict] = []
        self.last_fact: str | None = None
        # V5.16: bounded conversational fact history.  This is not a transcript
        # or a hidden semantic cache: it contains only IDs of facts that were
        # actually asserted/revised in the dialogue.  It lets an explicit repair
        # refer back past an intervening topic while remaining auditable through
        # the underlying KB fact/provenance records.
        self.discourse_facts: list[str] = []
        # V5.22: cross-predicate document-role bridges are learned only from
        # repeated *explicit* shared referents in independent document episodes.
        # Coreference-resolved facts never count as support, preventing circular
        # self-confirmation.
        self.document_role_bridge_hypotheses: dict[str, dict] = {}
        # V5.25: candidate document-event schemas are learned only from repeated
        # explicit adjacent fact pairs whose argument-equality structure recurs in
        # independent documents.  The schema is *not* an event assertion.  A
        # latent event node is materialized only when a demonstrative reference
        # (eso/esto/aquello) cannot be resolved to an entity and exactly one
        # promoted structural candidate can explain it.  This keeps event
        # invention demand-driven and makes ambiguous partitions abstain.
        self.document_event_schema_hypotheses: dict[str, dict] = {}
        # V5.27: meta-transfer of event *topology* is kept separate from exact
        # predicate schemas.  A topology becomes active only after at least two
        # predicate-disjoint exact schemas were not merely promoted but actually
        # materialized to resolve an event reference.  This prevents one repeated
        # lexical family from licensing a universal event heuristic.
        self.document_event_meta_hypotheses: dict[str, dict] = {}
        # V5.29: a transferred event topology is not universally applicable just
        # because its internal role geometry matches.  We separately learn which
        # downstream predicate/argument roles have independently *used* exact
        # event representations.  Meta-transferred event candidates are admitted
        # only through a promoted, uncontested consumer-role gate.
        self.document_event_reference_hypotheses: dict[str, dict] = {}
        # V5.31: explicit competition between a transferred event interpretation
        # and an ordinary-entity interpretation for the same downstream role.
        # Event credit comes only from V5.29's predicate-disjoint exact uses;
        # independent credit comes only when an ambiguous demonstrative is later
        # disambiguated by an explicit assertion in the same document episode.
        # Resolver-produced facts never count, preventing self-confirmation.
        self.document_event_choice_hypotheses: dict[str, dict] = {}
        # V5.28: pending raw document episodes for testing whether a proven event
        # topology can reduce the examples required to acquire *new* opaque
        # relations.  These records contain text/provenance only; they do not
        # assert facts until a unique meta-constrained anti-unification succeeds.
        self.document_event_bootstrap_observations: list[dict] = []
        # V5.33: explicit document-causal links may be reified as a representation
        # type distinct from events.  Support is learned only from actual downstream
        # uses of causal nodes and is deduplicated by semantic episode content, not
        # by source names or generated fact IDs.  This lets causal dependencies
        # compete with event representations without treating every adjacency as
        # causality.
        self.document_causal_reference_hypotheses: dict[str, dict] = {}
        # V5.34: generic predictive gates for reified explicit document links.
        # Any safe binary ``_doc_*`` relation already produced by the document
        # parser can become a first-class dependency representation without a new
        # hand-written candidate generator.  V5.33 causal gates are mirrored into
        # this store for backward-compatible evidence.
        self.document_dependency_reference_hypotheses: dict[str, dict] = {}
        # V5.35: latent persistent-state schemas are induced from repeated
        # non-contiguous explicit facts that keep one carrier entity stable while
        # unrelated intervening statements vary.  No input predicate names the
        # state.  A schema is only a hypothesis until a later demonstrative needs
        # the joint persistent condition; only then is a state node materialized.
        self.document_state_schema_hypotheses: dict[str, dict] = {}
        self.document_state_reference_hypotheses: dict[str, dict] = {}
        # V5.37: meta-topologies for persistent states erase lexical predicate
        # identity while preserving role geometry.  Promotion requires at least
        # two predicate-disjoint exact state families that were actually consumed
        # downstream.  Meta-transferred uses are deliberately non-crediting.
        self.document_state_meta_hypotheses: dict[str, dict] = {}
        self.document_state_meta_reference_hypotheses: dict[str, dict] = {}
        # V5.38: type-agnostic latent-representation proposal policies.  These
        # hypotheses are learned from successful *exact* uses belonging to at
        # least two different representation families (currently event/state),
        # then erase the family label, predicate names and arities.  Only common
        # relational features and the downstream consumer role survive.  Generic
        # bundle uses are intentionally non-crediting, preventing recursive
        # self-licensing.
        self.document_latent_strategy_hypotheses: dict[str, dict] = {}
        self.last_result: dict | None = None
        self.training_reports: list[dict] = []
        # Bounded discourse state.  This is linguistic working memory, not factual
        # truth: referents are only used to propose repairs that an already learned
        # construction can parse unambiguously.
        self.discourse_referents: list[dict] = []
        self.discourse_max_referents = 32
        # V8.9: last observed/executed symbolic world state, so dialogue can plan
        # toward learned goal constructions without restating the state.
        self.last_symbolic_state: list[tuple[str, ...]] | None = None
        # Entities seen in any observed or executed symbolic state; a goal naming
        # anything else is refused instead of planned.
        self.symbolic_entities: set[str] = set()

    def _remember_discourse_fact(self, fid: str | None) -> str | None:
        """Mark one concrete fact as the current conversational focus."""
        if not fid:
            return fid
        self.last_fact = fid
        live=[]
        for prior in self.discourse_facts:
            if prior == fid:
                continue
            if hasattr(self.kb, 'get_fact') and self.kb.get_fact(prior) is None:
                continue
            live.append(prior)
        live.append(fid)
        self.discourse_facts = live[-32:]
        return fid

    def _replace_discourse_fact(self, old_id: str, new_id: str) -> None:
        """Replace a revised fact ID in discourse history without duplicating it."""
        out=[]
        for fid in self.discourse_facts:
            if fid in (old_id,new_id):
                continue
            if fid not in out and (not hasattr(self.kb,'get_fact') or self.kb.get_fact(fid) is not None):
                out.append(fid)
        # The revision itself is the newest discourse event even when it repairs
        # a fact that was originally mentioned before an intervening topic.
        out.append(new_id)
        self.discourse_facts=out[-32:]
        self.last_fact=new_id

    def _recent_discourse_facts(self) -> list[dict]:
        """Return current conversational facts, newest first, with a V5.15 fallback."""
        ids=list(self.discourse_facts)
        if self.last_fact and self.last_fact not in ids:
            ids.append(self.last_fact)
        rows=[]; seen=set()
        for fid in reversed(ids[-32:]):
            if fid in seen or not hasattr(self.kb,'get_fact'):
                continue
            seen.add(fid); fact=self.kb.get_fact(fid)
            if fact is None or 'conversación' not in str(fact.get('source','')):
                continue
            rows.append(fact)
        return rows

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

    def _publish_meta_projection(self, input_arity: int, mapping, *, family: str,
                                 source: str, support: int = 1) -> dict:
        """Publish a role-flow abstraction and expose it only to other learners.

        The central library contains no domain semantics.  Receiving learners
        still require their own target observations to match the projection before
        it can lower search/support.  This is therefore a prior over
        representation topology, not a transferred answer.
        """
        meta=self.meta_representations.register_projection(
            input_arity, mapping, family=family, source=source, support=support)
        roles=self.meta_representations.register_role_set(
            input_arity, mapping, family=family, source=source, support=support)
        if meta.get('status')!='meta_representation_registered':
            return {'meta':meta,'role_set':roles,'propagated':{}}
        propagated={}
        if family != 'procedure':
            propagated['procedure']=self.procedures.register_external_projection(
                input_arity,mapping,source=f'meta:{family}:{source}',support=support)
            propagated['procedure_role_set']=self.procedures.register_external_role_set(
                input_arity,mapping,source=f'meta:{family}:{source}',support=support)
            propagated['procedure_role_cardinality']=self.procedures.register_external_role_cardinality(
                len(set(int(x) for x in mapping)),source=f'meta:{family}:{source}',support=support)
        if family != 'symbolic':
            propagated['symbolic']=self.symbolic.register_external_projection(
                input_arity,mapping,source=f'meta:{family}:{source}',support=support)
            propagated['symbolic_role_set']=self.symbolic.register_external_role_set(
                input_arity,mapping,source=f'meta:{family}:{source}',support=support)
            propagated['symbolic_role_cardinality']=self.symbolic.register_external_role_cardinality(
                len(set(int(x) for x in mapping)),source=f'meta:{family}:{source}',support=support)
        return {'meta':meta,'role_set':roles,'propagated':propagated}

    def _publish_meta_role_set(self, input_arity: int, roles, *, family: str,
                               source: str, support: int = 1) -> dict:
        meta=self.meta_representations.register_role_set(
            input_arity,roles,family=family,source=source,support=support)
        if meta.get('status')!='meta_representation_registered':
            return {'meta':meta,'propagated':{}}
        propagated={}
        if family != 'procedure':
            propagated['procedure']=self.procedures.register_external_role_set(
                input_arity,roles,source=f'meta:{family}:{source}',support=support)
            propagated['procedure_cardinality']=self.procedures.register_external_role_cardinality(
                len(set(int(x) for x in roles)),source=f'meta:{family}:{source}',support=support)
        if family != 'symbolic':
            propagated['symbolic']=self.symbolic.register_external_role_set(
                input_arity,roles,source=f'meta:{family}:{source}',support=support)
            propagated['symbolic_cardinality']=self.symbolic.register_external_role_cardinality(
                len(set(int(x) for x in roles)),source=f'meta:{family}:{source}',support=support)
        return {'meta':meta,'propagated':propagated}

    def observe_world_transition(self, before, after) -> dict:
        """Compare a real state change with one uniquely matching raw text fact.

        Symbol equality is evidence about role relevance, not predicate meaning.
        Three independent facts must agree before a structural prior is shared.
        """
        def facts(rows):
            result=set()
            for fact in rows:
                row=tuple(str(value) for value in fact)
                if not 2 <= len(row) <= 9 or len(result)>=10_000:
                    raise ValueError('Estado del entorno fuera del presupuesto.')
                result.add(row)
            return result

        prior=facts(before); observed=facts(after)
        changed=prior ^ observed
        if not changed:
            return {'status':'raw_world_no_change'}
        changed_values={normalize(value) for fact in changed for value in fact[1:]}
        candidates=[]
        promoted={promotion.get('predicate'):int(promotion.get('arity',0))
                  for promotion in self.raw_relation_promotions.values()
                  if isinstance(promotion.get('predicate'),str)}
        relevant=set(self.kb.predicates_for_entities(changed_values)) & set(promoted)
        for predicate in sorted(relevant):
            arity=promoted[predicate]
            if arity<3:
                continue
            fact_ids=set()
            for value in sorted(changed_values):
                for position in range(arity):
                    pattern=Atom(predicate,tuple(value if index==position else f'?role{index}'
                                                 for index in range(arity)))
                    for fact in self.kb.matches(pattern):
                        fact_ids.add(fact['id'])
                        if len(fact_ids)>64:
                            return {'status':'raw_world_budget','candidates':len(fact_ids)}
            for fid in sorted(fact_ids):
                fact=self.kb.get_fact(fid)
                if fact is None or fact['atom'].pred!=predicate:
                    continue
                args=fact['atom'].args
                normalized_args=tuple(normalize(str(value)) for value in args)
                if len(args)!=arity or len(set(normalized_args))!=arity:
                    continue
                roles=tuple(index for index,value in enumerate(normalized_args)
                            if value in changed_values)
                if len(roles)>=2:
                    edges=set()
                    for fact in changed:
                        values={normalize(value) for value in fact[1:]}
                        present=tuple(index for index,role in enumerate(roles)
                                      if normalized_args[role] in values)
                        if len(present)>=2:
                            edges.add(present)
                    candidates.append((predicate,arity,roles,tuple(sorted(edges)),fid))
        if len(candidates)!=1:
            return {'status':'raw_world_ambiguous' if candidates else 'raw_world_unmatched',
                    'candidates':len(candidates)}
        predicate,arity,roles,edges,fact_id=candidates[0]
        episode=hashlib.blake2b(json.dumps([sorted(prior),sorted(observed)],
                                              ensure_ascii=False).encode('utf8'),
                                 digest_size=12).hexdigest()
        state=self.raw_world_alignment_hypotheses.setdefault(predicate,{
            'arity':arity,'observations':[],'promoted_roles':None,'promoted_edges':None})
        if any(row['episode']==episode for row in state['observations']):
            return {'status':'raw_world_duplicate','predicate':predicate}
        record={'episode':episode,'fact_id':fact_id,'roles':list(roles),
                'edges':[list(edge) for edge in edges]}
        state['observations'].append(record)
        state['observations']=state['observations'][-64:]
        source='raw_world:'+predicate
        withdrawn=None
        if state.get('promoted_roles') is not None and (
                state['promoted_roles']!=list(roles) or
                state.get('promoted_edges')!=[list(edge) for edge in edges]):
            withdrawn=self._remove_meta_source_from_consumers('raw_world',source)
            state['promoted_roles']=None
            state['promoted_edges']=None
        tail=[]
        for row in reversed(state['observations']):
            if row['roles']!=list(roles) or row.get('edges')!=[list(edge) for edge in edges]:
                break
            tail.append(row)
        independent=len({row['fact_id'] for row in tail})
        published=None
        if (len(roles)<arity and independent>=3 and
                MetaRepresentationLibrary.canonical_role_topology(len(roles),edges) is not None):
            role_set=self._publish_meta_role_set(
                arity,roles,family='raw_world',source=source,support=independent)
            topology=self._publish_meta_role_topology(
                len(roles),edges,family='raw_world',source=source,support=independent)
            if (role_set['meta'].get('status')=='meta_representation_registered' and
                    topology['meta'].get('status')=='meta_representation_registered'):
                published={'role_set':role_set,'topology':topology}
                state['promoted_roles']=list(roles)
                state['promoted_edges']=[list(edge) for edge in edges]
        status=('raw_world_conflict' if withdrawn is not None else
                'raw_world_grounded' if published is not None else 'raw_world_pending')
        report={'status':status,'predicate':predicate,'arity':arity,
                'roles':list(roles),'edges':[list(edge) for edge in edges],
                'independent_support':independent,
                'source_fact_id':fact_id,'episode':episode,
                'published':published,'withdrawn':withdrawn}
        self.training_reports.append({'type':'raw_world_transition',**report})
        return report

    def _publish_meta_role_topology(self, input_arity: int, edges, *, family: str,
                                    source: str, support: int = 1) -> dict:
        meta=self.meta_representations.register_role_topology(
            input_arity,edges,family=family,source=source,support=support)
        if meta.get('status')!='meta_representation_registered':
            return {'meta':meta,'propagated':{}}
        propagated={}
        if family != 'symbolic':
            propagated['symbolic']=self.symbolic.register_external_role_topology(
                input_arity,edges,source=f'meta:{family}:{source}',support=support)
        return {'meta':meta,'propagated':propagated}

    def _sync_meta_controller(self) -> None:
        """Share one auditable meta-controller across independent learners.

        The learners never own the controller state; they only report bounded
        structural decisions to the bot-level instance.  This makes persistence
        single-source and permits cross-mechanism transfer without copying task
        semantics between learners.
        """
        self.procedures.meta_controller = self.meta_controller
        self.symbolic.meta_controller = self.meta_controller

    def _sync_meta_representations(self) -> None:
        """Rebuild consumer indexes from the auditable central representation memory.

        Role-cardinality rows are weaker priors: they state only how many
        roles repeatedly mattered across earlier tasks.  They are useful to the
        procedure learner across unseen arities, but they never identify which
        roles; the target domain must establish that by interventions.
        """
        for row in self.meta_representations.rows():
            kind=row.get('kind')
            for source,info in sorted((row.get('sources') or {}).items()):
                family=str(info.get('family','unknown')); support=int(info.get('support',1))
                if kind=='role_cardinality':
                    if family != 'procedure':
                        self.procedures.register_external_role_cardinality(
                            int(row.get('cardinality',0)),source=f'meta:{family}:{source}',support=support)
                    if family != 'symbolic':
                        self.symbolic.register_external_role_cardinality(
                            int(row.get('cardinality',0)),source=f'meta:{family}:{source}',support=support)
                    continue
                if kind=='role_topology':
                    if family != 'symbolic':
                        self.symbolic.register_external_role_topology(
                            int(row.get('input_arity',0)),row.get('edges',()),
                            source=f'meta:{family}:{source}',support=support)
                    continue
                if 'input_arity' not in row:
                    continue
                n=int(row['input_arity'])
                if kind=='role_set':
                    values=tuple(int(x) for x in row.get('roles',()))
                    if family != 'procedure':
                        self.procedures.register_external_role_set(n,values,source=f'meta:{family}:{source}',support=support)
                        self.procedures.register_external_role_cardinality(
                            len(set(values)),source=f'meta:{family}:{source}',support=support)
                    if family != 'symbolic':
                        self.symbolic.register_external_role_set(n,values,source=f'meta:{family}:{source}',support=support)
                        self.symbolic.register_external_role_cardinality(
                            len(set(values)),source=f'meta:{family}:{source}',support=support)
                else:
                    mapping=tuple(int(x) for x in row.get('mapping',()))
                    if family != 'procedure':
                        self.procedures.register_external_projection(n,mapping,source=f'meta:{family}:{source}',support=support)
                        self.procedures.register_external_role_cardinality(
                            len(set(mapping)),source=f'meta:{family}:{source}',support=support)
                    if family != 'symbolic':
                        self.symbolic.register_external_projection(n,mapping,source=f'meta:{family}:{source}',support=support)
                        self.symbolic.register_external_role_cardinality(
                            len(set(mapping)),source=f'meta:{family}:{source}',support=support)

    def _remove_meta_source_from_consumers(self, family: str, source: str,
                                           _seen: set[tuple[str,str]] | None = None) -> dict:
        """Withdraw a disproved structural source from the central memory and consumers."""
        if _seen is None:
            _seen=set()
        marker=(family,source)
        if marker in _seen:
            return {'status':'already_withdrawn','source':source}
        _seen.add(marker)
        report=self.meta_representations.withdraw_source(source)
        propagated_source=normalize(f'meta:{family}:{source}')
        for learner in (self.procedures,self.symbolic):
            for attr in ('external_projection_schemas','external_permutation_schemas','external_role_sets','external_role_cardinalities','external_role_topologies'):
                table=getattr(learner,attr,{})
                for key in list(table):
                    row=table[key]; sources=row.get('sources',{})
                    if propagated_source in sources:
                        sources.pop(propagated_source,None)
                        row['support']=sum(int(v) for v in sources.values())
                        if not sources:
                            table.pop(key,None)
        invalidated_actions=[]
        for pattern,session in sorted(self.symbolic.sessions.items()):
            if (not session.get('promoted') or
                    propagated_source not in session.get('cross_modal_sources',())):
                continue
            direct=self.symbolic._fit(pattern)
            if direct.get('status')=='operator_learned':
                session.pop('cross_modal_schema',None)
                session.pop('cross_modal_sources',None)
                continue
            self.symbolic._drop_from_analogy_indexes(pattern)
            invalidated_actions.append(pattern)
        for pattern in invalidated_actions:
            self._remove_meta_source_from_consumers('symbolic','symbolic:'+pattern,_seen)
        affected_skills=set();invalidated_procedures=[]
        for pattern,session in sorted(self.procedures.sessions.items()):
            if not session.get('promoted'):
                continue
            sources=set(session.get('cross_modal_sources',()))
            for item in session.get('last_reports',()):
                sources.update(item.get('meta_dependency_sources',()))
            if propagated_source in sources:
                invalidated_procedures.append(pattern)
                for skill in session.get('output_skills',()):
                    affected_skills.update(self.programs._invalidate(skill))
        if affected_skills:
            for pattern,session in sorted(self.procedures.sessions.items()):
                if (session.get('promoted') and pattern not in invalidated_procedures and
                        affected_skills.intersection(session.get('output_skills',()))):
                    invalidated_procedures.append(pattern)
        for pattern in invalidated_procedures:
            session=self.procedures.sessions[pattern]
            session['promoted']=False
            session['last_reports']=[]
            session['meta_dependency_schemas']=[]
            session.pop('cross_modal_schema',None)
            session.pop('cross_modal_sources',None)
            self.procedures._register_semantics(pattern)
            self._remove_meta_source_from_consumers('procedure','procedure:'+pattern,_seen)
        if invalidated_actions or invalidated_procedures:
            report=dict(report)
            report['invalidated_actions']=invalidated_actions
            report['invalidated_procedures']=invalidated_procedures
        return report


    def observe_concept_statement(self, text: str) -> dict:
        """Learn a previously unnamed relation from an ordinary natural assertion."""
        report = self.concepts.observe(text)
        self.training_reports.append({'type': 'concept_grounding', 'text': text, **report})
        return report

    def query_concept(self, text: str) -> dict:
        """Resolve a natural yes/no relation utterance against an invented concept."""
        return self.concepts.resolve(text)

    def observe_schema_statement(self, text: str) -> dict:
        """Learn an open-role concept and export only its domain-free role flow."""
        report = self.schemas.observe(text)
        if report.get('status') in ('schema_learned','schema_confirmed'):
            surface=report.get('surface')
            session=self.schemas.sessions.get(surface,{}) if surface else {}
            projection=session.get('projection')
            mention_count=int(session.get('mention_count',0) or 0)
            if projection is not None and mention_count >= 2:
                support=len(session.get('observations',()))
                published=self._publish_meta_role_set(
                    mention_count,tuple(projection),family='schema',
                    source='schema_surface:'+str(surface),support=support)
                if published.get('meta',{}).get('status')=='meta_representation_registered':
                    report=dict(report); report['meta_representation']=published
                solution=session.get('solution') if isinstance(session.get('solution'),dict) else {}
                topology=solution.get('role_topology') or ()
                arity=int(session.get('arity') or 0)
                if arity>=2 and topology:
                    topo=self._publish_meta_role_topology(
                        arity,topology,family='schema',
                        source='schema_surface:'+str(surface),support=support)
                    if topo.get('meta',{}).get('status')=='meta_representation_registered':
                        report=dict(report); report['meta_role_topology']=topo
        else:
            surface=report.get('surface')
            source='schema_surface:'+str(surface) if surface else None
            if source and self.meta_representations.has_source(source):
                report=dict(report); report['meta_representation_withdrawal']=self._remove_meta_source_from_consumers('schema',source)
        self.training_reports.append({'type': 'open_arity_concept_grounding', 'text': text, **report})
        return report

    def query_schema(self, text: str) -> dict:
        """Resolve an utterance through an acquired open-arity concept schema."""
        return self.schemas.resolve(text)

    def acquire_schema_assertion(self, text: str, source: str = 'conversación',
                                 require_novel: bool = True) -> dict:
        """Acquire new referents/facts through a previously learned surface."""
        report=self.schemas.acquire_assertion(text,source=source,require_novel=require_novel)
        if report.get('status')=='schema_fact_stored':
            self._remember_discourse_fact(report.get('id')); self.last_result=None
            self.training_reports.append({'type':'schema_surface_assertion','text':text,**report})
        return report

    def observe_transition(self, text: str, before, after) -> dict:
        """Learn an action meaning from a natural utterance and an observed state change."""
        report = self.procedures.observe(text, before, after)
        # Cross-representation abstraction: a learned pure tuple permutation is
        # registered as structural knowledge for the symbolic learner.  No action
        # name or domain predicate crosses the boundary.
        cross=None
        source='procedure:'+str(report.get('pattern'))
        if report.get('status')=='procedure_learned':
            session=self.procedures.sessions.get(report.get('pattern'),{})
            n=int(session.get('input_arity',0)); m=int(session.get('output_arity',0))
            signature=self.procedures.observed_projection_signature(session)
            if signature is not None:
                n,mapping=signature
                if list(mapping)!=list(range(n)):
                    published=self._publish_meta_projection(
                        n,tuple(mapping),family='procedure',
                        source=source, support=len(session.get('supports',())))
                    cross=published.get('propagated',{}).get('symbolic')
                    if cross is not None:
                        report=dict(report); report['meta_representation']=published
            # A non-projection program can still export a weaker, unordered
            # dependency certificate when every retained hypothesis agrees on
            # which input roles matter.  No arithmetic operator or language
            # surface is transferred.
            if int(session.get('parameter_count',0))==0 and n>=2:
                deps=[]; certified=True
                for skill in session.get('output_skills',()):
                    row=self.programs.dependency_roles(skill)
                    if row is None:
                        certified=False; break
                    deps.extend(int(x) for x in row)
                roles=tuple(sorted(set(deps))) if certified else ()
                if roles and len(roles)<n:
                    dep_published=self._publish_meta_role_set(
                        n,roles,family='procedure',source=source,
                        support=len(session.get('supports',())))
                    if dep_published.get('meta',{}).get('status')=='meta_representation_registered':
                        report=dict(report); report['meta_dependency_representation']=dep_published
                        if cross is None:
                            report['cross_modal_relevance']=dep_published.get('propagated',{}).get('symbolic')
        if report.get('status')!='procedure_learned' and self.meta_representations.has_source(source):
            report=dict(report); report['meta_representation_withdrawal']=self._remove_meta_source_from_consumers('procedure',source)
        if cross is not None:
            report=dict(report);report['cross_modal_learning']=cross
        self.training_reports.append({'type':'procedure_grounding', **report})
        return report

    def correct_transition(self, text: str, before, after) -> dict:
        """Correct one grounded procedure without disturbing the others."""
        report = self.procedures.correct(text, before, after)
        self.training_reports.append({'type':'procedure_correction', **report})
        return report

    def execute_transition(self, text: str, state) -> dict:
        """Apply a grounded action cue to a new observable state."""
        return self.procedures.execute(text, state)

    def suggest_transition_probe(self, text: str, output_index: int = 0, role_costs=None) -> dict:
        """Ask which unlabeled intervention offers the most information per declared cost."""
        return self.procedures.suggest_probe(text,output_index,role_costs=role_costs)

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
        self.last_symbolic_state = sorted(tuple(f) for f in after)
        self.symbolic_entities.update(str(arg) for state in (before, after) for fact in state for arg in tuple(fact)[1:])
        cross=None
        if report.get('status')=='operator_learned':
            add=tuple(tuple(x) for x in report.get('add',()))
            delete=tuple(tuple(x) for x in report.get('delete',()))
            perm=self.symbolic._effect_permutation_signature(add,delete)
            if perm is not None:
                n=len(tuple(perm)); mapping=tuple(perm)
                published=self._publish_meta_projection(
                    n,mapping,family='symbolic',
                    source='symbolic:'+str(report.get('pattern')),support=int(report.get('support',1)))
                cross=published.get('propagated',{}).get('procedure')
                if cross is not None:
                    report=dict(report); report['meta_representation']=published
            else:
                sig=self.symbolic._effect_projection_signature(str(report.get('pattern')),add,delete)
                if sig is not None:
                    n,mapping=sig
                    published=self._publish_meta_projection(
                        n,mapping,family='symbolic',
                        source='symbolic:'+str(report.get('pattern')),support=int(report.get('support',1)))
                    cross=published.get('propagated',{}).get('procedure')
                    if cross is not None:
                        report=dict(report); report['meta_representation']=published
        if report.get('status')=='operator_learned':
            pattern=str(report.get('pattern') or '')
            n=self.symbolic._pattern_role_count(pattern)
            edges=[]
            for fact in report.get('preconditions',()):
                edge=self.symbolic._fact_role_edge(tuple(fact))
                if edge is not None:
                    edges.append(edge)
            if n>=2 and edges:
                topo=self._publish_meta_role_topology(
                    n,edges,family='symbolic',source='symbolic:'+pattern,
                    support=int(report.get('support',1)))
                if topo.get('meta',{}).get('status')=='meta_representation_registered':
                    report=dict(report); report['meta_role_topology']=topo
        source='symbolic:'+str(report.get('pattern'))
        if report.get('status')!='operator_learned' and self.meta_representations.has_source(source):
            report=dict(report); report['meta_representation_withdrawal']=self._remove_meta_source_from_consumers('symbolic',source)
        if cross is not None:
            report=dict(report);report['cross_modal_learning']=cross
        self.training_reports.append({'type':'symbolic_transition', 'text':text, 'report':report})
        return report

    def execute_symbolic_transition(self, text: str, state) -> dict:
        report = self.symbolic.execute(text, state)
        if report.get('status') == 'executed_symbolic_action':
            self.last_symbolic_state = sorted(tuple(f) for f in report['result'])
            self.symbolic_entities.update(arg for fact in self.last_symbolic_state for arg in fact[1:])
        return report

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

    def as_dict(self) -> dict:
        data = {
            'version': 1,
            'kb': self.kb.as_dict(),
            'language': self.language.as_dict(),
            'grounded_language': self.grounded_language,
            'allow_extensional_grounding': self.allow_extensional_grounding,
            'grounding_min_support': self.grounding_min_support,
            'raw_relation_min_support': self.raw_relation_min_support,
            'raw_relation_max_arity': self.raw_relation_max_arity,
            'programs': self.programs.as_dict(),
            'procedures': self.procedures.as_dict(),
            'symbolic': self.symbolic.as_dict(),
            'concepts': self.concepts.as_dict(),
            'schemas': self.schemas.as_dict(),
            'meta_representations': self.meta_representations.as_dict(),
            'meta_controller': self.meta_controller.as_dict(),
            'last_fact': self.last_fact,
            'discourse_facts': self.discourse_facts,
            'discourse_referents': self.discourse_referents,
            'discourse_max_referents': self.discourse_max_referents,
            'last_symbolic_state': ([list(f) for f in self.last_symbolic_state]
                                    if self.last_symbolic_state is not None else None),
            'symbolic_entities': sorted(self.symbolic_entities),
        }
        data.update(plain_state(self))
        return data

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
                  grounding_min_support=data.get('grounding_min_support', 2),
                  raw_relation_min_support=data.get('raw_relation_min_support', 3),
                  allow_extensional_grounding=data.get('allow_extensional_grounding', False),
                  raw_relation_max_arity=data.get('raw_relation_max_arity', 8))
        bot.kb = KnowledgeBase.from_dict(data['kb'])
        bot.language = Language.from_dict(data['language'])
        bot.programs = ProgramLearner.from_dict(data['programs'])
        bot.procedures = ProcedureGrounder.from_dict(data.get('procedures', {}), bot.programs)
        bot.symbolic = SymbolicWorldLearner.from_dict(data.get('symbolic', {}))
        bot.concepts = ConceptGrounder.from_dict(data.get('concepts', {}), bot.kb)
        bot.schemas = OpenArityConceptGrounder.from_dict(data.get('schemas', {}), bot.kb)
        bot.meta_representations = MetaRepresentationLibrary.from_dict(data.get('meta_representations', {}))
        bot.meta_controller = MetaController.from_dict(data.get('meta_controller', {}))
        bot._sync_meta_controller()
        bot._sync_meta_representations()
        bot.last_fact = data.get('last_fact')
        bot.discourse_facts = [fid for fid in data.get('discourse_facts', [])
                               if isinstance(fid,str) and bot.kb.get_fact(fid) is not None][-32:]
        if bot.last_fact and bot.last_fact not in bot.discourse_facts and bot.kb.get_fact(bot.last_fact) is not None:
            bot.discourse_facts.append(bot.last_fact)
        restore_plain_state(bot, data)
        bot._restore_raw_consumption()
        bot.discourse_max_referents = max(4, int(data.get('discourse_max_referents', 32)))
        bot.discourse_referents = list(data.get('discourse_referents', []))[-bot.discourse_max_referents:]
        state = data.get('last_symbolic_state')
        bot.last_symbolic_state = [tuple(f) for f in state] if state is not None else None
        bot.symbolic_entities = set(data.get('symbolic_entities', []))
        return bot

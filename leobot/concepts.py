"""Grounded invention of previously unnamed binary relational concepts.

The learner does not receive a target predicate annotation.  It extracts a stable
surface schema from natural assertions that mention exactly two already-known
entities, treats explicit Spanish ``no`` as polarity, creates an opaque predicate
identifier, and asks the existing relational program learner to explain the
labelled pairs from the factual context.

This is deliberately conservative and restricted: it is not unrestricted
semantic parsing.  A concept is promoted only after independent positive and
negative examples, and failure to derive a pair is reported as unknown rather
than false.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterable
from itertools import permutations

from .core import Atom, Engine
from .language import normalize
from .learning import RelationalLearner
from .metapolicy import policy_spec, policy_key, policy_family, valid_policy


_NEGATORS = frozenset({'no'})  # grammatical polarity, not a domain relation
_MARKER_RE = re.compile(r'<e[01]>')


@dataclass(frozen=True)
class ConceptParse:
    surface: str
    target: str
    args: tuple[str, str]
    positive: bool


class ConceptGrounder:
    """Invent and learn binary relational predicates from natural examples."""

    def __init__(self, kb, min_positive: int = 2, min_negative: int = 2,
                 max_relation_length: int = 3, min_alias_support: int = 2,
                 allow_predicate_invention: bool = True, max_inventions: int = 64,
                 invention_shadow_probe_budget: int = 0) -> None:
        self.kb = kb
        self.min_positive = max(1, int(min_positive))
        self.min_negative = max(1, int(min_negative))
        self.max_relation_length = max(1, int(max_relation_length))
        self.min_alias_support = max(2, int(min_alias_support))
        self.allow_predicate_invention = bool(allow_predicate_invention)
        self.max_inventions = max(0, int(max_inventions))
        self.invention_shadow_probe_budget = max(0, min(64, int(invention_shadow_probe_budget)))
        # Dream-RSI-inspired but fully non-neural replay policy.  It controls only
        # the generic order in which inverse/direct two-step helper patterns are
        # explored during bounded predicate invention.  Completed invention traces
        # are replayed offline; no historical program is re-executed.
        self.invention_policy_order: list[tuple[bool,bool]] = [
            (False,False),(False,True),(True,False),(True,True)]
        self.invention_replay_worlds: list[dict] = []
        self.invention_policy_updates = 0
        self.invention_candidate_policy = 'baseline'
        self.invention_candidate_replay_worlds: list[dict] = []
        self.invention_candidate_policy_updates = 0
        self.invention_candidate_regime_resets = 0
        # surface -> metadata.  Examples themselves live in kb.examples so that
        # relational learning and contradiction handling remain single-source.
        self.sessions: dict[str, dict] = {}

    def _known_mentions(self, text: str) -> list[tuple[int, int, str]]:
        norm = normalize(text)
        tokens = norm.split()
        if not tokens or len(tokens) > 64:
            return []
        candidates: set[str] = set()
        for width in range(1, min(4, len(tokens)) + 1):
            for i in range(len(tokens) - width + 1):
                candidates.add(' '.join(tokens[i:i + width]))
        known = set(self.kb.known_entities(candidates)) if hasattr(self.kb, 'known_entities') else set()
        spans: list[tuple[int, int, str]] = []
        for entity in sorted(known, key=lambda x: (-len(x), x)):
            hits = list(re.finditer(r'(?<!\w)' + re.escape(entity) + r'(?!\w)', norm))
            if len(hits) != 1:
                continue
            m = hits[0]
            # Prefer longest non-overlapping entity names.
            if any(not (m.end() <= a or m.start() >= b) for a, b, _ in spans):
                continue
            spans.append((m.start(), m.end(), entity))
        spans.sort()
        return spans

    @staticmethod
    def _concept_id(surface: str) -> str:
        digest = hashlib.blake2b(surface.encode('utf8'), digest_size=8).hexdigest()
        return 'concept_' + digest

    def parse(self, text: str) -> ConceptParse | None:
        norm = normalize(text)
        spans = self._known_mentions(norm)
        if len(spans) != 2:
            return None
        (a0, b0, e0), (a1, b1, e1) = spans
        if e0 == e1:
            return None
        templ = norm[:a0] + ' <e0> ' + norm[b0:a1] + ' <e1> ' + norm[b1:]
        tokens = templ.split()
        positive = True
        cleaned: list[str] = []
        for tok in tokens:
            if tok in _NEGATORS:
                positive = False
            else:
                cleaned.append(tok)
        # The two markers alone are not a concept-bearing utterance.
        fixed = [x for x in cleaned if not _MARKER_RE.fullmatch(x)]
        if not fixed:
            return None
        surface = ' '.join(cleaned)
        if surface.count('<e0>') != 1 or surface.count('<e1>') != 1:
            return None
        return ConceptParse(surface, self._concept_id(surface), (e0, e1), positive)

    def _predict(self, target: str, args: tuple[str, str]) -> str:
        """Return four-valued entailment status for a learned concept target."""
        result = Engine(self.kb).answer(Atom(target, args))
        positive = bool(result['positive']['answers'])
        negative = bool(result['negative']['answers'])
        if positive and not negative:
            return 'entailed'
        if negative and not positive:
            return 'contradicted'
        if positive and negative:
            return 'contested'
        return 'unknown'

    def _root_concepts(self, exclude_surface: str) -> list[dict]:
        roots=[]
        for surface, session in self.sessions.items():
            if surface == exclude_surface:
                continue
            if session.get('status') == 'learned_hypothesis' and not session.get('alias_target'):
                roots.append(session)
        return roots

    def _alias_candidates(self, surface: str, examples: dict[tuple[str, str], set[bool]]) -> list[str]:
        """Find already learned concepts consistent with contrastive labels.

        This is deliberately conservative: aliases require at least one positive
        and one explicit negative example, a minimum number of independent pairs,
        and exactly one compatible previously learned root concept.  Unknown on a
        negative pair is acceptable because the negative label itself is explicit;
        an entailed negative pair rejects the candidate.
        """
        clean=[(pair, next(iter(labels))) for pair, labels in examples.items() if len(labels) == 1]
        if len(clean) < self.min_alias_support:
            return []
        if not any(label for _, label in clean) or not any(not label for _, label in clean):
            return []
        out=[]
        for session in self._root_concepts(surface):
            target=session['target']
            ok=True
            for pair,label in clean:
                status=self._predict(target,pair)
                if label:
                    if status != 'entailed':
                        ok=False;break
                elif status in ('entailed','contested'):
                    ok=False;break
            if ok:
                out.append(target)
        return sorted(set(out))

    @staticmethod
    def _inv_key(pattern) -> str:
        return ''.join('1' if bool(x) else '0' for x in pattern)

    @staticmethod
    def _inv_pattern(key: str) -> tuple[bool,bool]:
        if key not in ('00','01','10','11'):
            raise ValueError('Patrón de replay inválido.')
        return (key[0]=='1',key[1]=='1')

    def _replay_score(self, order_keys: tuple[str,...]) -> int | None:
        """Exact replay cost on the *realized* invention histories.

        A candidate policy is evaluable only when every pattern it moves ahead of
        the successful pattern was fully explored in that historical world.  This
        mirrors Dream-RSI's sharp limitation: history is exact where it exists and
        says nothing about branches never visited.
        """
        total=0
        for world in self.invention_replay_worlds:
            success=world['success_pattern']; exhausted=set(world['exhausted'])
            counts={str(k):int(v) for k,v in world['counts'].items()}
            try: pos=order_keys.index(success)
            except ValueError: return None
            before=order_keys[:pos]
            if any(k not in exhausted for k in before):
                return None
            total += sum(counts.get(k,0) for k in before) + int(world['success_position'])
        return total

    def _update_invention_replay_policy(self, report: dict) -> dict | None:
        trace=list(report.get('invention_trace') or ())
        if not trace:
            return None
        success_index=None
        for i,row in enumerate(trace):
            if row.get('used') and row.get('target_status')=='learned_hypothesis':
                success_index=i;break
        if success_index is None:
            return None
        keys=[self._inv_key(row.get('inversion_pattern',(False,False))) for row in trace]
        success_key=keys[success_index]
        # Candidate generation is grouped by inversion pattern.  Patterns that
        # occurred strictly before the successful group are known to be exhausted.
        first_success_group=keys.index(success_key)
        exhausted=[];counts={}
        for key in keys[:first_success_group]:
            counts[key]=counts.get(key,0)+1
            if key not in exhausted: exhausted.append(key)
        success_position=sum(1 for key in keys[:success_index+1] if key==success_key)
        counts[success_key]=success_position
        world={'success_pattern':success_key,'exhausted':exhausted,
               'counts':counts,'success_position':success_position}
        self.invention_replay_worlds.append(world)
        if len(self.invention_replay_worlds)>64:
            self.invention_replay_worlds=self.invention_replay_worlds[-64:]
        current=tuple(self._inv_key(p) for p in self.invention_policy_order)
        current_score=self._replay_score(current)
        best=current;best_score=current_score
        for order in permutations(('00','01','10','11')):
            score=self._replay_score(order)
            if score is None:
                continue
            if best_score is None or score < best_score:
                best,best_score=order,score
        changed=best != current and best_score is not None and (current_score is None or best_score < current_score)
        if changed:
            self.invention_policy_order=[self._inv_pattern(k) for k in best]
            self.invention_policy_updates += 1
        return {'worlds':len(self.invention_replay_worlds),'policy_before':list(current),
                'policy_after':[self._inv_key(p) for p in self.invention_policy_order],
                'replay_cost_before':current_score,'replay_cost_after':best_score,
                'updated':changed,'scope':'realized_invention_history'}

    @staticmethod
    def _candidate_policy_spec(policy: str):
        return policy_spec(policy)

    @staticmethod
    def _candidate_policy_key(meta: dict, policy: str):
        return policy_key(meta, policy)

    @staticmethod
    def _candidate_policy_family() -> tuple[str,...]:
        return policy_family()

    @staticmethod
    def _valid_candidate_policy(policy: str) -> bool:
        return valid_policy(policy)

    def _candidate_world_score(self, world: dict, policy: str) -> int | None:
        catalog=sorted(world['catalog'],key=lambda m:self._candidate_policy_key(m,policy))
        observed=world['observed_costs']
        # V7 worlds can contain multiple successful branches discovered by
        # bounded shadow exploration.  Replay follows the candidate policy until
        # the *first* known success, and is exact only if every preceding outcome
        # is recorded.  Legacy V5/V6 worlds retain one historical success.
        successes=set(world.get('successful_definitions') or ())
        if successes:
            total=0
            for meta in catalog:
                definition=meta['definition']
                if definition not in observed:
                    return None
                total += int(observed[definition])
                if definition in successes:
                    return total
            return None
        success=world.get('success_definition')
        positions={m['definition']:i for i,m in enumerate(catalog)}
        if success not in positions:
            return None
        prefix=[m['definition'] for m in catalog[:positions[success]+1]]
        if any(d not in observed for d in prefix):
            return None
        return sum(int(observed[d]) for d in prefix)

    def _candidate_replay_score(self, policy: str) -> int | None:
        total=0
        for world in self.invention_candidate_replay_worlds:
            score=self._candidate_world_score(world,policy)
            if score is None:
                return None
            total += score
        return total

    def _update_candidate_replay_policy(self, report: dict) -> dict | None:
        if not report.get('invention_catalog_complete'):
            return None
        catalog=list(report.get('invention_candidate_catalog') or ())
        trace=list(report.get('invention_trace') or ())
        if not catalog or not trace:
            return None
        successes=[str(row.get('definition')) for row in trace
                   if row.get('used') and row.get('target_status')=='learned_hypothesis']
        if not successes:
            return None
        observed={str(row.get('definition')):max(1,int(row.get('candidates') or 1)) for row in trace}
        world={'catalog':catalog,'successful_definitions':sorted(set(successes)),
               'success_definition':successes[0],'observed_costs':observed,
               'deployed_policy':report.get('invention_candidate_policy',self.invention_candidate_policy),
               'online_attempts':int(report.get('invention_attempts') or 0),
               'shadow_attempts':int(report.get('invention_shadow_attempts') or 0)}
        current=self.invention_candidate_policy
        self.invention_candidate_replay_worlds.append(world)
        if len(self.invention_candidate_replay_worlds)>32:
            self.invention_candidate_replay_worlds=self.invention_candidate_replay_worlds[-32:]
        # A policy is retired only from exact realized evidence.  With shadow
        # branches, the latest world may prove another synthesized policy cheaper
        # even when the historical baseline itself remains partly unobserved.
        current_latest=self._candidate_world_score(world,current)
        baseline_latest=self._candidate_world_score(world,'baseline')
        policies=self._candidate_policy_family()
        latest_scored=[(self._candidate_world_score(world,p),p) for p in policies]
        latest_scored=[x for x in latest_scored if x[0] is not None]
        latest_best=min(latest_scored) if latest_scored else (None,None)
        has_shadow=any(bool(row.get('shadow')) for row in trace)
        if has_shadow:
            regime_reset=(current_latest is not None and latest_best[0] is not None
                          and latest_best[0] < current_latest)
        else:
            # Preserve the historical V5.3 rule when no extra counterfactual
            # branches were deliberately observed.
            regime_reset=(current!='baseline' and current_latest is not None
                          and baseline_latest is not None and current_latest > baseline_latest)
        if regime_reset:
            self.invention_candidate_replay_worlds=[world]
            self.invention_candidate_regime_resets += 1
        before=self._candidate_replay_score(current)
        best=current;best_score=before
        for policy in policies:
            score=self._candidate_replay_score(policy)
            if score is None:
                continue
            if best_score is None or score < best_score:
                best,best_score=policy,score
        changed=best!=current and best_score is not None and (before is None or best_score < before)
        if changed:
            self.invention_candidate_policy=best
            self.invention_candidate_policy_updates += 1
        return {'worlds':len(self.invention_candidate_replay_worlds),
                'policy_before':current,'policy_after':self.invention_candidate_policy,
                'replay_cost_before':before,'replay_cost_after':best_score,
                'latest_policy_cost':current_latest,'latest_baseline_cost':baseline_latest,
                'latest_best_cost':latest_best[0],'latest_best_policy':latest_best[1],
                'regime_reset':regime_reset,
                'updated':changed,'exact_on_realized_history':True}

    def _shadow_probe_threshold(self) -> int:
        """Typical online candidate count for the currently deployed policy.

        Only worlds actually deployed under that policy vote.  With no history,
        three attempts is the conservative grace window, avoiding exploratory
        overhead on the first ordinary use of a newly synthesized policy.
        """
        vals=sorted(int(w.get('online_attempts')) for w in self.invention_candidate_replay_worlds
                    if w.get('deployed_policy') == self.invention_candidate_policy
                    and isinstance(w.get('online_attempts'), int) and int(w.get('online_attempts')) > 0)
        if not vals:
            return 3
        return max(1, vals[len(vals)//2])

    def observe(self, text: str) -> dict:
        parsed = self.parse(text)
        if parsed is None:
            return {'status': 'concept_unrecognized'}
        session = self.sessions.setdefault(parsed.surface, {
            'surface': parsed.surface,
            'target': parsed.target,
            'observations': [],
            'status': 'pending',
            'solution': None,
            'alias_target': None,
        })
        eid = json.dumps({'args': parsed.args, 'positive': parsed.positive}, separators=(',', ':'))
        is_new = not any(o['id'] == eid for o in session['observations'])
        if is_new:
            session['observations'].append({'id': eid, 'text': text, 'args': list(parsed.args),
                                            'positive': parsed.positive})

        # Once a surface is an alias, new evidence validates the alias instead of
        # silently editing the root concept.  Incompatibility withdraws only the
        # language alias and falls back to its own provisional concept learner.
        alias_target=session.get('alias_target')
        if alias_target:
            predicted=self._predict(alias_target, parsed.args)
            compatible=(parsed.positive and predicted == 'entailed') or (
                not parsed.positive and predicted not in ('entailed','contested'))
            if compatible:
                return {'status':'concept_alias_confirmed','surface':parsed.surface,
                        'target':alias_target,'positive':parsed.positive,
                        'independent_observation':is_new}
            session['alias_target']=None
            session['status']='pending'
            session['solution']=None
            withdrawn=True
        else:
            withdrawn=False

        changed = self.kb.add_example(session['target'], parsed.args, parsed.positive)
        examples = self.kb.examples.get(session['target'], {})
        pos = sum(labels == {True} for labels in examples.values())
        neg = sum(labels == {False} for labels in examples.values())
        contradictory = sum(len(labels) > 1 for labels in examples.values())
        base = {'surface': parsed.surface, 'target': session['target'], 'positive_examples': pos,
                'negative_examples': neg, 'changed': changed, 'contradictory': contradictory}
        if contradictory:
            session['status'] = 'contradictory_examples'
            session['solution'] = None
            return {'status': 'concept_contradictory', **base}

        # Prior learned concepts can reduce the evidence needed for a new wording.
        # Promotion occurs only when exactly one root concept survives contrastive
        # positive+negative evidence; otherwise the surface remains independent.
        alias_candidates=self._alias_candidates(parsed.surface, examples)
        if len(alias_candidates) == 1:
            session['status']='alias_learned'
            session['alias_target']=alias_candidates[0]
            session['solution']={'status':'alias_learned','target':alias_candidates[0]}
            return {'status':'concept_alias_learned','alias_target':alias_candidates[0],
                    'alias_candidates':alias_candidates, **base}

        if pos < self.min_positive or neg < self.min_negative:
            session['status'] = 'pending'
            status='concept_alias_withdrawn' if withdrawn else 'concept_pending'
            return {'status': status, 'required_positive': self.min_positive,
                    'required_negative': self.min_negative,
                    'alias_candidates': alias_candidates, **base}
        learner = RelationalLearner(self.kb, max_length=self.max_relation_length,
                                    invention_inversion_order=self.invention_policy_order,
                                    invention_candidate_policy=self.invention_candidate_policy)
        if self.allow_predicate_invention:
            report = learner.fit_with_invention(session['target'], max_inventions=self.max_inventions,
                                                shadow_probe_budget=self.invention_shadow_probe_budget,
                                                shadow_probe_threshold=self._shadow_probe_threshold())
            replay=self._update_invention_replay_policy(report)
            if replay is not None:
                report['replay_policy']=replay
            dream=self._update_candidate_replay_policy(report)
            if dream is not None:
                report['dream_replay_policy']=dream
        else:
            report = learner.fit(session['target'])
        session['status'] = report['status']
        session['solution'] = report
        return {'status': 'concept_learned' if report['status'] == 'learned_hypothesis' else 'concept_unresolved',
                'alias_candidates': alias_candidates, **base, 'learning': report}

    def resolve(self, text: str) -> dict:
        parsed = self.parse(text)
        if parsed is None:
            return {'status': 'concept_unrecognized'}
        session = self.sessions.get(parsed.surface)
        if not session or session.get('status') not in ('learned_hypothesis', 'alias_learned'):
            return {'status': 'concept_unknown', 'surface': parsed.surface}
        target = session.get('alias_target') or session['target']
        result = Engine(self.kb).answer(Atom(target, parsed.args))
        positive = bool(result['positive']['answers'])
        negative = bool(result['negative']['answers'])
        if positive and not negative:
            status = 'entailed'
        elif negative and not positive:
            status = 'contradicted'
        elif positive and negative:
            status = 'contested'
        else:
            status = 'unknown'
        return {'status': status, 'target': target, 'args': list(parsed.args),
                'surface': parsed.surface, 'proof': result}

    def learned(self) -> list[dict]:
        return [dict(v) for v in self.sessions.values() if v.get('status') in ('learned_hypothesis','alias_learned')]

    def as_dict(self) -> dict:
        return {'version': 7, 'min_positive': self.min_positive, 'min_negative': self.min_negative,
                'max_relation_length': self.max_relation_length, 'min_alias_support': self.min_alias_support,
                'allow_predicate_invention': self.allow_predicate_invention,
                'max_inventions': self.max_inventions, 'invention_shadow_probe_budget': self.invention_shadow_probe_budget,
                'sessions': self.sessions,
                'invention_policy_order': [[int(a),int(b)] for a,b in self.invention_policy_order],
                'invention_replay_worlds': self.invention_replay_worlds,
                'invention_policy_updates': self.invention_policy_updates,
                'invention_candidate_policy': self.invention_candidate_policy,
                'invention_candidate_replay_worlds': self.invention_candidate_replay_worlds,
                'invention_candidate_policy_updates': self.invention_candidate_policy_updates,
                'invention_candidate_regime_resets': self.invention_candidate_regime_resets}

    @classmethod
    def from_dict(cls, data: dict, kb) -> 'ConceptGrounder':
        if not data:
            return cls(kb)
        if data.get('version') not in (1, 2, 3, 4, 5, 6, 7):
            raise ValueError('Estado de conceptos no compatible.')
        obj = cls(kb, data.get('min_positive', 2), data.get('min_negative', 2),
                  data.get('max_relation_length', 3), data.get('min_alias_support', 2),
                  data.get('allow_predicate_invention', data.get('version') == 3),
                  data.get('max_inventions', 64), data.get('invention_shadow_probe_budget', 0))
        obj.sessions = data.get('sessions', {})
        if data.get('version') in (4,5,6,7):
            raw_order=data.get('invention_policy_order', [[0,0],[0,1],[1,0],[1,1]])
            order=[(bool(a),bool(b)) for a,b in raw_order]
            if set(order)=={(False,False),(False,True),(True,False),(True,True)} and len(order)==4:
                obj.invention_policy_order=order
            obj.invention_replay_worlds=list(data.get('invention_replay_worlds',[]))[-64:]
            obj.invention_policy_updates=int(data.get('invention_policy_updates',0))
        if data.get('version') in (5,6,7):
            policy=str(data.get('invention_candidate_policy','baseline'))
            if obj._valid_candidate_policy(policy):
                obj.invention_candidate_policy=policy
            obj.invention_candidate_replay_worlds=list(data.get('invention_candidate_replay_worlds',[]))[-32:]
            obj.invention_candidate_policy_updates=int(data.get('invention_candidate_policy_updates',0))
            obj.invention_candidate_regime_resets=int(data.get('invention_candidate_regime_resets',0))
        return obj

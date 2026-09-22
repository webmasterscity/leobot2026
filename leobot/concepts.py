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

from .core import Atom, Engine
from .language import normalize
from .learning import RelationalLearner


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
                 allow_predicate_invention: bool = True, max_inventions: int = 64) -> None:
        self.kb = kb
        self.min_positive = max(1, int(min_positive))
        self.min_negative = max(1, int(min_negative))
        self.max_relation_length = max(1, int(max_relation_length))
        self.min_alias_support = max(2, int(min_alias_support))
        self.allow_predicate_invention = bool(allow_predicate_invention)
        self.max_inventions = max(0, int(max_inventions))
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
        learner = RelationalLearner(self.kb, max_length=self.max_relation_length)
        if self.allow_predicate_invention:
            report = learner.fit_with_invention(session['target'], max_inventions=self.max_inventions)
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
        return {'version': 3, 'min_positive': self.min_positive, 'min_negative': self.min_negative,
                'max_relation_length': self.max_relation_length, 'min_alias_support': self.min_alias_support,
                'allow_predicate_invention': self.allow_predicate_invention,
                'max_inventions': self.max_inventions, 'sessions': self.sessions}

    @classmethod
    def from_dict(cls, data: dict, kb) -> 'ConceptGrounder':
        if not data:
            return cls(kb)
        if data.get('version') not in (1, 2, 3):
            raise ValueError('Estado de conceptos no compatible.')
        obj = cls(kb, data.get('min_positive', 2), data.get('min_negative', 2),
                  data.get('max_relation_length', 3), data.get('min_alias_support', 2),
                  data.get('allow_predicate_invention', data.get('version') == 3),
                  data.get('max_inventions', 64))
        obj.sessions = data.get('sessions', {})
        return obj

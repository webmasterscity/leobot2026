"""Open-arity grounded concept acquisition for one to three semantic roles.

This module extends the earlier binary ``ConceptGrounder`` without replacing it.
It learns an opaque relation from ordinary Spanish contrastive examples while the
number of semantic roles is still unknown.  Surface mentions are only candidate
slots: the learner tests projections of those slots and rejects projections that
collapse positive and negative observations onto the same tuple.  A small
conjunctive relational learner then searches for a rule over existing grounded
predicates.  Thus arity is selected by contrastive evidence plus executable world
structure rather than being supplied as a target annotation.

The implementation is intentionally bounded.  It supports 1--3 learned roles,
single-atom predicates of matching arity, two-binary-atom connected schemas
for ternary relations, and bounded binary stars around one existential event/entity
node.  It is an experiment in representational acquisition, not
unrestricted semantic parsing or general logic-program synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import combinations, permutations, product
import json
import re
from time import perf_counter
from typing import Iterable

from .core import Atom, Engine, Rule
from .language import normalize

_NEGATORS = frozenset({'no'})
_MARKER_RE = re.compile(r'<e\d+>')


@dataclass(frozen=True)
class SchemaParse:
    surface: str
    mentions: tuple[str, ...]
    positive: bool


@dataclass(frozen=True)
class SchemaCandidate:
    projection: tuple[int, ...]
    body: tuple[tuple[str, tuple[int, ...]], ...]

    @property
    def arity(self) -> int:
        return len(self.projection)

    @property
    def cost(self) -> int:
        return len(self.body)

    def text(self) -> str:
        atoms=[]
        for pred, roles in self.body:
            atoms.append(pred + '(' + ','.join(('z' if i < 0 else f'r{i}') for i in roles) + ')')
        return ' & '.join(atoms)


class OpenArityConceptGrounder:
    """Infer 1--3 role relational concepts from contrastive natural examples."""

    def __init__(self, kb, min_positive: int = 2, min_negative: int = 2,
                 max_mentions: int = 3, max_predicates: int = 16,
                 min_alias_support: int = 2, max_star_predicates: int = 6) -> None:
        self.kb = kb
        self.min_positive = max(1, int(min_positive))
        self.min_negative = max(1, int(min_negative))
        self.max_mentions = min(3, max(1, int(max_mentions)))
        self.max_predicates = max(1, int(max_predicates))
        self.min_alias_support = max(2, int(min_alias_support))
        self.max_star_predicates = max(1, int(max_star_predicates))
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
            if any(not (m.end() <= a or m.start() >= b) for a, b, _ in spans):
                continue
            spans.append((m.start(), m.end(), entity))
        spans.sort()
        return spans

    def parse(self, text: str) -> SchemaParse | None:
        norm = normalize(text)
        spans = self._known_mentions(norm)
        if not (1 <= len(spans) <= self.max_mentions):
            return None
        parts=[]; cursor=0
        mentions=[]
        for index, (a, b, entity) in enumerate(spans):
            parts.extend((norm[cursor:a], f' <e{index}> '))
            cursor=b; mentions.append(entity)
        parts.append(norm[cursor:])
        templ=''.join(parts)
        tokens=templ.split()
        positive=True; cleaned=[]
        for tok in tokens:
            if tok in _NEGATORS:
                positive=False
            else:
                cleaned.append(tok)
        fixed=[tok for tok in cleaned if not _MARKER_RE.fullmatch(tok)]
        if not fixed:
            return None
        surface=' '.join(cleaned)
        if any(surface.count(f'<e{i}>') != 1 for i in range(len(mentions))):
            return None
        return SchemaParse(surface, tuple(mentions), positive)

    @staticmethod
    def _surface_parts(surface: str):
        """Split a learned delexicalized surface into fixed token runs and slots.

        The surface itself is learned from prior grounded examples.  No lexical
        class, capitalization heuristic or entity dictionary is consulted here.
        """
        parts=[]; fixed=[]
        for token in surface.split():
            match=_MARKER_RE.fullmatch(token)
            if match:
                if fixed:
                    parts.append(('fixed',tuple(fixed))); fixed=[]
                parts.append(('slot',int(token[2:-1])))
            else:
                fixed.append(token)
        if fixed:
            parts.append(('fixed',tuple(fixed)))
        return parts

    def _match_surface_spans(self, surface: str, text: str, max_matches: int = 2) -> dict:
        """Recover previously learned slots even when their values are unseen.

        Matching is token based and enumerates segmentations consistent with the
        fixed material of the learned surface.  If more than one segmentation is
        possible, Leobot abstains instead of silently selecting a regex boundary.
        """
        norm=normalize(text); raw_tokens=norm.split()
        if not raw_tokens or len(raw_tokens) > 64:
            return {'status':'schema_surface_unmatched'}
        positive=True; tokens=[]
        for token in raw_tokens:
            if token in _NEGATORS:
                positive=False
            else:
                tokens.append(token)
        parts=self._surface_parts(surface)
        slot_ids=[value for kind,value in parts if kind=='slot']
        if not slot_ids or len(set(slot_ids)) != len(slot_ids):
            return {'status':'schema_surface_unmatched'}
        solutions=[]

        # Precompute the minimum number of tokens needed after each part: every
        # future slot must consume >=1 token and every fixed token must match.
        suffix_min=[0]*(len(parts)+1)
        for i in range(len(parts)-1,-1,-1):
            kind,value=parts[i]
            suffix_min[i]=suffix_min[i+1] + (1 if kind=='slot' else len(value))

        def walk(pi: int, ti: int, slots: dict[int,str]):
            if len(solutions) >= max_matches:
                return
            if pi == len(parts):
                if ti == len(tokens):
                    solutions.append(dict(slots))
                return
            kind,value=parts[pi]
            if kind=='fixed':
                n=len(value)
                if tuple(tokens[ti:ti+n]) == value:
                    walk(pi+1,ti+n,slots)
                return
            # A slot is a non-empty contiguous span.  The learned fixed material
            # determines boundaries; multiple legal boundaries are ambiguity.
            max_end=len(tokens)-suffix_min[pi+1]
            for end in range(ti+1,max_end+1):
                slots[value]=' '.join(tokens[ti:end])
                walk(pi+1,end,slots)
                if len(solutions) >= max_matches:
                    break
            slots.pop(value,None)

        walk(0,0,{})
        if not solutions:
            return {'status':'schema_surface_unmatched'}
        if len(solutions) != 1:
            return {'status':'schema_surface_ambiguous','surface':surface,'alternatives':len(solutions)}
        chosen=solutions[0]
        if sorted(chosen) != list(range(max(chosen)+1)):
            return {'status':'schema_surface_unmatched'}
        mentions=tuple(chosen[i] for i in range(max(chosen)+1))
        return {'status':'schema_surface_matched','surface':surface,'mentions':mentions,
                'positive':positive}

    @staticmethod
    def _session_target_mapping(session: dict):
        if session.get('alias_target'):
            return session.get('alias_target'), tuple(session.get('alias_mapping') or ())
        return session.get('target'), tuple(session.get('projection') or ())

    def parse_learned_surface(self, text: str) -> dict:
        """Parse a learned schema using its fixed surface, without entity lookup.

        This is deliberately available only after the corresponding schema has
        been learned from grounded contrastive evidence.  Distinct semantic
        matches or ambiguous slot boundaries cause abstention.
        """
        matches=[]; ambiguous=[]
        for surface,session in sorted(self.sessions.items()):
            if session.get('status') not in ('learned_hypothesis','alias_learned'):
                continue
            parsed=self._match_surface_spans(surface,text)
            if parsed.get('status')=='schema_surface_ambiguous':
                ambiguous.append({'surface':surface,'alternatives':parsed.get('alternatives',2)})
                continue
            if parsed.get('status')!='schema_surface_matched':
                continue
            target,mapping=self._session_target_mapping(session)
            mentions=tuple(parsed['mentions'])
            if not target or not mapping or max(mapping,default=-1) >= len(mentions):
                continue
            args=tuple(mentions[i] for i in mapping)
            matches.append({'surface':surface,'target':target,'mapping':list(mapping),
                            'mentions':list(mentions),'args':list(args),
                            'positive':bool(parsed['positive'])})
        if ambiguous:
            return {'status':'schema_surface_ambiguous','ambiguous':ambiguous}
        unique={}
        for match in matches:
            key=json.dumps({'target':match['target'],'args':match['args'],
                            'positive':match['positive']},sort_keys=True,ensure_ascii=False)
            unique[key]=match
        if not unique:
            return {'status':'schema_surface_unmatched'}
        if len(unique) != 1:
            return {'status':'schema_surface_ambiguous','matches':list(unique.values())}
        return {'status':'schema_surface_matched',**next(iter(unique.values()))}

    def acquire_assertion(self, text: str, source: str = 'conversación',
                          require_novel: bool = True) -> dict:
        """Store a fact expressed through a learned schema with unseen spans.

        The asserted relation itself becomes an explicit primitive fact.  Leobot
        does *not* abductively invent the lower-level facts that originally made
        the learned schema true.  This preserves what the utterance licenses while
        allowing its newly introduced referents to participate in later learning.
        """
        parsed=self.parse_learned_surface(text)
        if parsed.get('status')!='schema_surface_matched':
            return parsed
        target=parsed['target']; args=tuple(parsed['args'])
        known=set(self.kb.known_entities(set(args))) if hasattr(self.kb,'known_entities') else set()
        novel=[value for value in args if value not in known]
        if require_novel and not novel:
            return {**parsed,'status':'schema_surface_no_novel_entities','novel_entities':[]}
        pred=target if parsed.get('positive',True) else '!'+target
        provenance=f'{source}:schema_surface:{target}'
        fid=self.kb.add(Atom(pred,args),provenance)
        event={'event':'schema_surface_assertion','fact_id':fid,'text':text,
               'normalized_text':normalize(text),'surface':parsed['surface'],
               'target':target,'predicate':pred,'args':list(args),
               'mentions':parsed['mentions'],'role_mapping':parsed['mapping'],
               'positive':bool(parsed.get('positive',True)),
               'novel_entities':novel,'source':source}
        if hasattr(self.kb,'audit'):
            # Repeated identical assertions are idempotent at the fact layer; keep
            # only one identical acquisition event as well.
            if event not in self.kb.audit:
                self.kb.audit.append(event)
        return {**parsed,'status':'schema_fact_stored','id':fid,'predicate':pred,
                'novel_entities':novel,'provenance':event}

    @staticmethod
    def _target_id(surface: str, arity: int) -> str:
        digest=hashlib.blake2b(surface.encode('utf8'), digest_size=8).hexdigest()
        return f'schema_{digest}_a{arity}'

    @staticmethod
    def _examples(session: dict) -> dict[tuple[str, ...], set[bool]]:
        out: dict[tuple[str, ...], set[bool]] = {}
        for obs in session.get('observations', []):
            out.setdefault(tuple(obs['mentions']), set()).add(bool(obs['positive']))
        return out

    def _predict_target(self, target: str, args: tuple[str, ...]) -> str:
        result=Engine(self.kb).answer(Atom(target, args))
        positive=bool(result['positive']['answers'])
        negative=bool(result['negative']['answers'])
        if positive and not negative: return 'entailed'
        if negative and not positive: return 'contradicted'
        if positive and negative: return 'contested'
        return 'unknown'

    def _roots(self, exclude_surface: str) -> list[dict]:
        return [s for surface,s in self.sessions.items()
                if surface != exclude_surface and s.get('status') == 'learned_hypothesis'
                and not s.get('alias_target')]

    def _alias_candidates(self, surface: str, examples: dict[tuple[str, ...], set[bool]]) -> list[dict]:
        clean=[(args,next(iter(labels))) for args,labels in examples.items() if len(labels)==1]
        if len(clean) < self.min_alias_support:
            return []
        if not any(label for _,label in clean) or not any(not label for _,label in clean):
            return []
        mention_count=len(clean[0][0]) if clean else 0
        out=[]
        for root in self._roots(surface):
            arity=int(root.get('arity') or 0)
            target=root.get('target')
            if not target or arity < 1 or arity > mention_count:
                continue
            for mapping in permutations(range(mention_count), arity):
                ok=True
                for mentions,label in clean:
                    args=tuple(mentions[i] for i in mapping)
                    status=self._predict_target(target,args)
                    if label:
                        if status != 'entailed': ok=False; break
                    elif status in ('entailed','contested'):
                        ok=False; break
                if ok:
                    out.append({'target':target,'mapping':list(mapping),'arity':arity,
                                'root_surface':root.get('surface')})
        unique={json.dumps(x,sort_keys=True,ensure_ascii=False):x for x in out}
        return [unique[k] for k in sorted(unique)]

    def _relevant_predicates(self, examples: dict[tuple[str, ...], set[bool]]) -> list[str]:
        entities={value for mentions in examples for value in mentions}
        scores=self.kb.predicates_for_entities(entities) if hasattr(self.kb,'predicates_for_entities') else {}
        ranked=[]
        for pred,score in scores.items():
            arity=self.kb.arity.get(pred)
            if pred.startswith('!') or arity not in (1,2,3):
                continue
            ranked.append((int(score),pred))
        ranked.sort(key=lambda x:(-x[0],x[1]))
        return [pred for _,pred in ranked[:self.max_predicates]]

    @staticmethod
    def _projected_labels(examples: dict[tuple[str, ...], set[bool]],
                          projection: tuple[int, ...]) -> dict[tuple[str, ...], set[bool]]:
        out: dict[tuple[str, ...], set[bool]]={}
        for mentions,labels in examples.items():
            args=tuple(mentions[i] for i in projection)
            out.setdefault(args,set()).update(labels)
        return out

    def _bodies(self, arity: int, predicates: Iterable[str]) -> list[tuple[tuple[str, tuple[int, ...]], ...]]:
        predicates=list(predicates)
        seen=set(); bodies=[]

        def add(body):
            # Body conjunction is order-insensitive.  Canonicalization keeps the
            # search deterministic and avoids duplicate schemas.
            key=tuple(sorted((p,tuple(r)) for p,r in body))
            if key in seen: return
            seen.add(key); bodies.append(key)

        roles=tuple(range(arity))
        for pred in predicates:
            if self.kb.arity.get(pred) != arity:
                continue
            for perm in permutations(roles):
                add(((pred,tuple(perm)),))

        if arity == 3:
            binary=[p for p in predicates if self.kb.arity.get(p)==2]
            directed=[(i,j) for i in roles for j in roles if i != j]
            for p,q in product(binary,binary):
                for edge1,edge2 in product(directed,directed):
                    if set(edge1) | set(edge2) != set(roles):
                        continue
                    add(((p,edge1),(q,edge2)))

        # One bounded existential hub captures reified events/objects whose node is
        # not mentioned in the utterance: e.g. actor(z,x) & item(z,y) & place(z,w).
        # This is deliberately one hidden variable, not unrestricted CQ synthesis.
        if arity in (2,3):
            binary=[p for p in predicates if self.kb.arity.get(p)==2][:self.max_star_predicates]
            choices=[]
            for role in roles:
                per_role=[]
                for pred in binary:
                    per_role.append((pred,(-1,role)))
                    per_role.append((pred,(role,-1)))
                choices.append(per_role)
            for atoms in product(*choices):
                add(tuple(atoms))
        return bodies

    @staticmethod
    def _ground_body(body: tuple[tuple[str, tuple[int, ...]], ...],
                     args: tuple[str, ...]) -> tuple[Atom, ...]:
        if any(i < 0 for _,roles in body for i in roles):
            raise ValueError('El cuerpo contiene una variable existencial.')
        return tuple(Atom(pred, tuple(args[i] for i in roles)) for pred,roles in body)

    def _body_holds(self, engine: Engine, body, args: tuple[str, ...]) -> bool:
        if not any(i < 0 for _,roles in body for i in roles):
            for atom in self._ground_body(body,args):
                result=engine.answer(atom)
                pos=bool(result['positive']['answers'])
                neg=bool(result['negative']['answers'])
                if not pos or neg:
                    return False
            return True

        possible=None
        for pred,roles in body:
            if roles.count(-1) != 1:
                return False
            hidden_pos=roles.index(-1)
            pattern=tuple('?z' if i < 0 else args[i] for i in roles)
            query=engine.query(Atom(pred,pattern))
            if not query.get('complete',False):
                return False
            values={proof.atom.args[hidden_pos] for proof in query.get('answers',())}
            possible=values if possible is None else possible & values
            if not possible:
                return False
        return bool(possible)

    def _fit(self, surface: str, examples: dict[tuple[str, ...], set[bool]]) -> dict:
        started=perf_counter()
        clean={args:labels for args,labels in examples.items() if len(labels)==1}
        if not clean:
            return {'status':'no_solution','reason':'no_clean_examples','ms':(perf_counter()-started)*1000}
        mention_count=len(next(iter(clean)))
        predicates=self._relevant_predicates(clean)
        engine=Engine(self.kb)
        candidates=[]; projection_rejections=0; evaluated=0
        for arity in range(1, mention_count+1):
            for projection in combinations(range(mention_count),arity):
                labels=self._projected_labels(clean,projection)
                if any(len(v)>1 for v in labels.values()):
                    projection_rejections += 1
                    continue
                bodies=self._bodies(arity,predicates)
                for body in bodies:
                    evaluated += 1
                    ok=True
                    for args,labs in labels.items():
                        label=next(iter(labs))
                        holds=self._body_holds(engine,body,args)
                        if holds != label:
                            ok=False;break
                    if ok:
                        candidates.append(SchemaCandidate(tuple(projection),body))
        report={'status':'no_solution','surface':surface,'predicates':predicates,
                'candidates_evaluated':evaluated,'projection_rejections':projection_rejections,
                'solutions':[]}
        if not candidates:
            report['ms']=(perf_counter()-started)*1000
            return report
        best_cost=min(c.cost for c in candidates)
        best=[c for c in candidates if c.cost==best_cost]
        signatures=sorted({(c.arity,c.projection) for c in best})
        report['solutions']=[{'arity':c.arity,'projection':list(c.projection),'body':c.text(),'cost':c.cost}
                             for c in sorted(best,key=lambda x:(x.arity,x.projection,x.text()))[:32]]
        report['minimum_cost']=best_cost
        report['minimum_role_signatures']=len(signatures)
        if len(signatures) != 1:
            report['status']='ambiguous_schema'
            report['ms']=(perf_counter()-started)*1000
            return report
        chosen=sorted((c for c in best if (c.arity,c.projection)==signatures[0]),key=lambda x:x.text())[0]
        arity=chosen.arity; target=self._target_id(surface,arity)
        variables=tuple(f'?r{i}' for i in range(arity))
        body_atoms=tuple(Atom(pred,tuple('?z0' if i < 0 else variables[i] for i in roles))
                         for pred,roles in chosen.body)
        evidence=[]
        for mentions,labels in sorted(clean.items()):
            label=next(iter(labels)); projected=tuple(mentions[i] for i in chosen.projection)
            evidence.append(('+' if label else '-')+target+'('+','.join(projected)+')')
        rule=Rule('learned:'+target+':schema',Atom(target,variables),body_atoms,'learned',tuple(evidence))
        self.kb.withdraw_learned(target)
        self.kb.add_rule(rule)
        role_topology=[list(roles) for _pred,roles in chosen.body
                       if roles and all(int(i)>=0 for i in roles)]
        report.update(status='learned_hypothesis',target=target,arity=arity,
                      projection=list(chosen.projection),selected=chosen.text(),
                      role_topology=role_topology if len(role_topology)==len(chosen.body) else [],
                      rules=[rule.as_dict()],minimum_body_alternatives=sum(
                          c.arity==arity and c.projection==chosen.projection and c.cost==best_cost for c in best),
                      ms=(perf_counter()-started)*1000)
        return report

    def _compatible(self, session: dict, mentions: tuple[str, ...], positive: bool) -> bool:
        if session.get('alias_target'):
            mapping=tuple(session.get('alias_mapping') or ())
            target=session['alias_target']
        else:
            mapping=tuple(session.get('projection') or ())
            target=session.get('target')
        if not target or not mapping or max(mapping,default=-1) >= len(mentions):
            return False
        status=self._predict_target(target,tuple(mentions[i] for i in mapping))
        return (positive and status=='entailed') or (not positive and status not in ('entailed','contested'))

    def observe(self, text: str) -> dict:
        parsed=self.parse(text)
        if parsed is None:
            return {'status':'schema_unrecognized'}
        session=self.sessions.setdefault(parsed.surface,{
            'surface':parsed.surface,'mention_count':len(parsed.mentions),'observations':[],
            'status':'pending','target':None,'arity':None,'projection':None,
            'solution':None,'alias_target':None,'alias_mapping':None,
        })
        if session.get('mention_count') != len(parsed.mentions):
            return {'status':'schema_unrecognized'}
        oid=json.dumps({'mentions':parsed.mentions,'positive':parsed.positive},separators=(',',':'))
        is_new=not any(o['id']==oid for o in session['observations'])
        if is_new:
            session['observations'].append({'id':oid,'text':text,'mentions':list(parsed.mentions),
                                            'positive':parsed.positive})
        examples=self._examples(session)
        contradictory=sum(len(labels)>1 for labels in examples.values())
        pos=sum(labels=={True} for labels in examples.values())
        neg=sum(labels=={False} for labels in examples.values())
        base={'surface':parsed.surface,'mentions':list(parsed.mentions),'positive_examples':pos,
              'negative_examples':neg,'contradictory':contradictory,
              'independent_observation':is_new}
        if contradictory:
            if session.get('target'): self.kb.withdraw_learned(session['target'])
            session.update(status='contradictory_examples',solution=None,target=None,arity=None,projection=None,
                           alias_target=None,alias_mapping=None)
            return {'status':'schema_contradictory',**base}

        if session.get('status') in ('learned_hypothesis','alias_learned') and self._compatible(session,parsed.mentions,parsed.positive):
            return {'status':'schema_confirmed','target':session.get('alias_target') or session.get('target'),
                    'arity':session.get('arity'),'projection':session.get('alias_mapping') or session.get('projection'),**base}
        if session.get('status') == 'learned_hypothesis' and session.get('target'):
            self.kb.withdraw_learned(session['target'])
        if session.get('status') in ('learned_hypothesis','alias_learned'):
            session.update(status='pending',solution=None,target=None,arity=None,projection=None,
                           alias_target=None,alias_mapping=None)

        if pos < self.min_positive or neg < self.min_negative:
            return {'status':'schema_pending','required_positive':self.min_positive,
                    'required_negative':self.min_negative,**base}

        aliases=self._alias_candidates(parsed.surface,examples)
        if len(aliases)==1:
            alias=aliases[0]
            session.update(status='alias_learned',target=None,arity=alias['arity'],projection=None,
                           solution={'status':'alias_learned',**alias},alias_target=alias['target'],
                           alias_mapping=alias['mapping'])
            return {'status':'schema_alias_learned','alias':alias,'alias_candidates':aliases,**base}

        report=self._fit(parsed.surface,examples)
        session['solution']=report
        if report.get('status')=='learned_hypothesis':
            session.update(status='learned_hypothesis',target=report['target'],arity=report['arity'],
                           projection=report['projection'],alias_target=None,alias_mapping=None)
            status='schema_learned'
        else:
            session.update(status=report.get('status','no_solution'),target=None,arity=None,projection=None,
                           alias_target=None,alias_mapping=None)
            status='schema_unresolved'
        return {'status':status,'alias_candidates':aliases,'learning':report,**base}

    def resolve(self, text: str) -> dict:
        parsed=self.parse(text)
        if parsed is None:
            learned=self.parse_learned_surface(text)
            if learned.get('status')!='schema_surface_matched':
                return learned if learned.get('status')=='schema_surface_ambiguous' else {'status':'schema_unrecognized'}
            target=learned['target']; mapping=tuple(learned['mapping']); args=tuple(learned['args'])
            surface=learned['surface']
        else:
            session=self.sessions.get(parsed.surface)
            if not session or session.get('status') not in ('learned_hypothesis','alias_learned'):
                return {'status':'schema_unknown','surface':parsed.surface}
            target,mapping=self._session_target_mapping(session)
            if not mapping or max(mapping,default=-1) >= len(parsed.mentions):
                return {'status':'schema_unknown','surface':parsed.surface}
            args=tuple(parsed.mentions[i] for i in mapping); surface=parsed.surface
        result=Engine(self.kb).answer(Atom(target,args))
        positive=bool(result['positive']['answers']); negative=bool(result['negative']['answers'])
        if positive and not negative: status='entailed'
        elif negative and not positive: status='contradicted'
        elif positive and negative: status='contested'
        else: status='unknown'
        return {'status':status,'target':target,'args':list(args),'arity':len(args),
                'surface':surface,'role_mapping':list(mapping),'proof':result}

    def learned(self) -> list[dict]:
        return [dict(v) for v in self.sessions.values()
                if v.get('status') in ('learned_hypothesis','alias_learned')]

    def as_dict(self) -> dict:
        return {'version':1,'min_positive':self.min_positive,'min_negative':self.min_negative,
                'max_mentions':self.max_mentions,'max_predicates':self.max_predicates,
                'min_alias_support':self.min_alias_support,'max_star_predicates':self.max_star_predicates,
                'sessions':self.sessions}

    @classmethod
    def from_dict(cls, data: dict, kb) -> 'OpenArityConceptGrounder':
        if not data:
            return cls(kb)
        if data.get('version') != 1:
            raise ValueError('Estado de esquemas no compatible.')
        obj=cls(kb,data.get('min_positive',2),data.get('min_negative',2),
                data.get('max_mentions',3),data.get('max_predicates',16),
                data.get('min_alias_support',2),data.get('max_star_predicates',6))
        obj.sessions=data.get('sessions',{})
        return obj

"""Supervised induction of relational programs; no per-domain answers.

Searches binary path compositions, inverses, and transitive closure. Previously
learned relations are reusable operators. This is a deliberately restricted DSL,
not an implementation of arbitrary program discovery or unrestricted language.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from collections import defaultdict
from time import perf_counter
from .core import Atom, Rule, KnowledgeBase, Engine, BudgetExceeded, variable

PairSet = frozenset[tuple[str, str]]


@dataclass(frozen=True)
class Path:
    steps: tuple[tuple[str, bool], ...]  # predicate, reverse
    recursive: bool = False

    @property
    def cost(self) -> int:
        return len(self.steps) + (3 if self.recursive else 0)

    def text(self) -> str:
        s = ' ; '.join(('inverse(' + p + ')') if inv else p for p, inv in self.steps)
        return 'closure(' + s + ')' if self.recursive else s

    def rules(self, target: str, evidence: tuple[str, ...]) -> list[Rule]:
        vs = ['?x'] + [f'?z{i}' for i in range(len(self.steps) - 1)] + ['?y']
        body = tuple(Atom(p, (vs[i + 1], vs[i]) if inv else (vs[i], vs[i + 1]))
                     for i, (p, inv) in enumerate(self.steps))
        result = [Rule('learned:' + target + ':base', Atom(target, ('?x', '?y')), body, 'learned', evidence)]
        if self.recursive:
            # Closure is currently generated only for one-step base relations.
            p, inv = self.steps[0]
            first = Atom(p, ('?z', '?x') if inv else ('?x', '?z'))
            result.append(Rule('learned:' + target + ':rec', Atom(target, ('?x', '?y')),
                               (first, Atom(target, ('?z', '?y'))), 'learned', evidence))
        return result


class RelationalLearner:
    def __init__(self, kb: KnowledgeBase, max_length: int = 3, max_candidates: int = 20_000,
                 max_pairs: int = 40_000, max_seconds: float = 10.0, max_auto_predicates: int = 32,
                 max_auto_hops: int = 3, max_auto_entities: int = 512) -> None:
        if max_length < 1 or max_length > 16:
            raise ValueError('La longitud del programa debe estar entre 1 y 16.')
        self.kb, self.max_length = kb, max_length
        self.max_candidates, self.max_pairs, self.max_seconds = max_candidates, max_pairs, max_seconds
        self.max_auto_predicates = max(1, int(max_auto_predicates))
        self.max_auto_hops = max(0, int(max_auto_hops))
        self.max_auto_entities = max(8, int(max_auto_entities))
        self.relevance_entities = 0
        self.relevance_hops = 0
        self._extension_cache: dict[tuple, tuple[PairSet, int]] = {}
        self._preserve_extension_cache = False
        self._extension_stack: set[str] = set()


    def _auto_predicates(self, target: str, examples: dict[tuple[str, str], set[bool]]) -> tuple[list[str], int]:
        """Retrieve a bounded relevant predicate set without scanning the whole KB.

        Direct candidates come from an entity->predicate inverted index. Learned
        heads are admitted when they depend on already relevant predicates. The
        ranking is deterministic and based only on overlap with labelled entities.
        """
        entities = {v for pair in examples for v in pair}
        positive_entities={v for pair,labels in examples.items() if labels == {True} for v in pair}
        negative_entities={v for pair,labels in examples.items() if labels == {False} for v in pair}
        raw_score = self.kb.predicates_for_entities(entities) if hasattr(self.kb, 'predicates_for_entities') else {}
        pos_score = self.kb.predicates_for_entities(positive_entities) if hasattr(self.kb, 'predicates_for_entities') else {}
        neg_score = self.kb.predicates_for_entities(negative_entities) if hasattr(self.kb, 'predicates_for_entities') else {}
        score: dict[str, int] = {p: int(pos_score.get(p,0))*10000 + int(neg_score.get(p,0))*100 + int(n)
                                 for p, n in raw_score.items()
                                 if p != target and self.kb.arity.get(p) == 2}
        # Expand a bounded local entity neighborhood so predicates that only
        # connect intermediate nodes can still be retrieved.  Endpoint-touching
        # predicates keep a higher score; deeper predicates receive a decayed
        # bonus and cannot make the search scan the whole KB.
        seen_entities=set(entities);frontier=set(entities);hops=0
        max_hops=min(self.max_auto_hops,max(0,self.max_length-1))
        if hasattr(self.kb,'neighbor_entities') and hasattr(self.kb,'predicates_for_entities'):
            for depth in range(max_hops):
                if not frontier or len(seen_entities) >= self.max_auto_entities:
                    break
                local=self.kb.predicates_for_entities(frontier)
                local_preds={p for p in local if p != target and self.kb.arity.get(p) == 2}
                neighbors=set(self.kb.neighbor_entities(frontier,local_preds,
                                   max_neighbors=max(1,self.max_auto_entities-len(seen_entities))))
                new_entities=neighbors-seen_entities
                if not new_entities:
                    break
                seen_entities.update(new_entities);frontier=new_entities;hops=depth+1
                nearby=self.kb.predicates_for_entities(new_entities)
                decay=max(1,100//(depth+2))
                for p,n in nearby.items():
                    if p == target or self.kb.arity.get(p) != 2:
                        continue
                    score[p]=max(score.get(p,0),int(n)*decay)
        self.relevance_entities=len(seen_entities);self.relevance_hops=hops
        relevant = set(score)
        changed = True
        while changed:
            changed = False
            for rule in self.kb.rules.values():
                head = rule.head.pred.lstrip('!')
                if head == target or self.kb.arity.get(head) != 2 or head in relevant:
                    continue
                deps = {a.pred.lstrip('!') for a in rule.body}
                if deps & relevant:
                    relevant.add(head)
                    score[head] = max((score.get(d, 0) for d in deps), default=0)
                    changed = True
        ranked = sorted(relevant, key=lambda p: (-score.get(p, 0), p))
        total = len(ranked)
        return ranked[:self.max_auto_predicates], total

    def _simple_path_steps(self, pred: str) -> tuple[tuple[str, bool], ...] | None:
        """Recognize the non-recursive chain rules generated by ``Path.rules``."""
        rules=list(self.kb.heads.get(pred,{}).values())
        if len(rules) != 1:
            return None
        rule=rules[0]
        if rule.origin != 'learned' or rule.head.args != ('?x','?y') or not rule.body:
            return None
        if any(atom.pred == pred for atom in rule.body):
            return None
        current='?x';steps=[]
        for atom in rule.body:
            if len(atom.args) != 2:
                return None
            a,b=atom.args
            if a == current and variable(b):
                steps.append((atom.pred,False));current=b
            elif b == current and variable(a):
                steps.append((atom.pred,True));current=a
            else:
                return None
        return tuple(steps) if current == '?y' else None

    def _extension(self, pred: str) -> tuple[PairSet, int]:
        # Primitive extensions are safe to cache during one logical learning
        # transaction.  fit_with_invention preserves the cache across its internal
        # retries because facts stay fixed while helper rules are tried.
        rules=list(self.kb.heads.get(pred,{}).values())
        if not rules:
            key=('fact',pred)
            if key in self._extension_cache:
                ext,_=self._extension_cache[key];return ext,0
            ext = frozenset(f['atom'].args for f in self.kb.matches(Atom(pred, ('?x', '?y'))))
            if len(ext) > self.max_pairs:
                raise BudgetExceeded('Relación de entrenamiento demasiado grande.')
            out=(ext,len(ext));self._extension_cache[key]=out
            return out

        steps=self._simple_path_steps(pred)
        if steps is not None and pred not in self._extension_stack:
            signature=tuple((r.id,tuple((a.pred,a.args) for a in r.body)) for r in rules)
            key=('path',pred,signature)
            if key in self._extension_cache:
                ext,_=self._extension_cache[key];return ext,0
            self._extension_stack.add(pred)
            try:
                ext=None;work=0
                for step_pred,reverse in steps:
                    rel,w=self._extension(step_pred);work+=w
                    if reverse:
                        rel=frozenset((y,x) for x,y in rel)
                    ext=rel if ext is None else self._compose(ext,rel)
                    if len(ext) > self.max_pairs:
                        raise BudgetExceeded('Relación de entrenamiento demasiado grande.')
                out=(ext or frozenset(),work);self._extension_cache[key]=out
                return out
            finally:
                self._extension_stack.discard(pred)

        # Recursive or non-chain learned predicates retain the general engine.
        qr = Engine(self.kb).query(Atom(pred, ('?x', '?y')))
        if not qr['complete']:
            raise BudgetExceeded('No se pudo obtener una relación de entrenamiento completa.')
        ext = frozenset(p.atom.args for p in qr['answers'])
        if len(ext) > self.max_pairs:
            raise BudgetExceeded('Relación de entrenamiento demasiado grande.')
        return ext, qr['stats']['work']

    def _tick(self, n: int = 1) -> None:
        self.joins += n
        if self.joins % 256 == 0 and perf_counter() - self.started > self.max_seconds:
            raise BudgetExceeded('Tiempo de búsqueda agotado.')
        if self.joins > max(1_000_000, self.max_candidates * 200):
            raise BudgetExceeded('Presupuesto de composición agotado.')

    def _compose(self, left: PairSet, right: PairSet) -> PairSet:
        index: dict[str, set[str]] = defaultdict(set)
        for x, y in right:
            index[x].add(y)
        out: set[tuple[str, str]] = set()
        for x, z in left:
            self._tick()
            for y in index.get(z, ()):
                self._tick()
                out.add((x, y))
                if len(out) > self.max_pairs:
                    raise BudgetExceeded('Demasiados pares en una relación candidata.')
        return frozenset(out)

    def _closure(self, base: PairSet) -> PairSet:
        result, frontier = set(base), base
        while frontier:
            extra = self._compose(frontier, base) - result
            result.update(extra)
            if len(result) > self.max_pairs:
                raise BudgetExceeded('Cierre transitivo demasiado grande.')
            frontier = frozenset(extra)
        return frozenset(result)

    def fit(self, target: str, allowed: list[str] | None = None, install: bool = True) -> dict:
        if not self._preserve_extension_cache:
            self._extension_cache.clear();self._extension_stack.clear()
        self.started, self.joins, self.candidates = perf_counter(), 0, 0
        self.kb.withdraw_learned(target)
        examples = self.kb.examples.get(target, {})
        positive = frozenset(a for a, labels in examples.items() if labels == {True})
        negative = frozenset(a for a, labels in examples.items() if labels == {False})
        report = {'target': target, 'status': 'no_solution', 'positive': len(positive), 'negative': len(negative),
                  'search_complete': True, 'solutions': [], 'rules': [], 'notice': 'Hipótesis dentro de un DSL restringido.',
                  'predicate_mode': 'auto' if allowed is None else 'explicit'}
        if any(len(labels) > 1 for labels in examples.values()):
            return {**report, 'status': 'contradictory_examples', 'ms': 0.0, 'candidates': 0, 'joins': 0}
        if not positive:
            return {**report, 'status': 'need_positive_examples', 'ms': 0.0, 'candidates': 0, 'joins': 0}
        primitives: list[tuple[Path, PairSet]] = []
        solutions: list[Path] = []
        seen: dict[PairSet, Path] = {}
        feature_work = 0

        def consider(path: Path, ext: PairSet) -> bool:
            self.candidates += 1
            if self.candidates > self.max_candidates:
                raise BudgetExceeded('Presupuesto de candidatos agotado.')
            if perf_counter() - self.started > self.max_seconds:
                raise BudgetExceeded('Tiempo de búsqueda agotado.')
            old = seen.get(ext)
            # Equality here is on the WHOLE observed world, not just labels.
            # It remains a heuristic: unseen worlds may distinguish these programs.
            if old is not None and old.cost <= path.cost:
                return False
            seen[ext] = path
            if positive <= ext and not negative.intersection(ext):
                solutions.append(path)
            return bool(ext)

        try:
            if allowed is None:
                predicates, total_candidates = self._auto_predicates(target, examples)
                report['predicate_candidates_total'] = total_candidates
                report['predicate_selected'] = predicates
                report['relevance_entities'] = self.relevance_entities
                report['relevance_hops'] = self.relevance_hops
            else:
                predicates = list(allowed)
                report['predicate_candidates_total'] = len(predicates)
                report['predicate_selected'] = predicates
            for pred in predicates:
                if pred == target or pred.startswith('!'):
                    continue
                ext, work = self._extension(pred)
                feature_work += work
                for inverse in (False, True):
                    rel = frozenset((y, x) for x, y in ext) if inverse else ext
                    path = Path(((pred, inverse),))
                    if consider(path, rel):
                        primitives.append((path, rel))
            frontier = primitives
            for length in range(2, self.max_length + 1):
                next_level: list[tuple[Path, PairSet]] = []
                for path, ext in frontier:
                    for leaf, rel in primitives:
                        candidate = Path(path.steps + leaf.steps)
                        extension = self._compose(ext, rel)
                        if consider(candidate, extension):
                            next_level.append((candidate, extension))
                frontier = next_level
                if not frontier:
                    break
            for path, ext in primitives:
                consider(Path(path.steps, True), self._closure(ext))
        except BudgetExceeded as exc:
            report['search_complete'], report['reason'] = False, str(exc)
        solutions.sort(key=lambda p: (p.cost, p.text()))
        if solutions:
            best = solutions[0]
            evidence = tuple(f'{"+" if True in labels else "-"}{target}({a[0]}, {a[1]})' for a, labels in examples.items())
            rules = best.rules(target, evidence)
            if install:
                for rule in rules:
                    self.kb.add_rule(rule)
            report.update(status='learned_hypothesis', solutions=[p.text() for p in solutions[:16]],
                          rules=[r.as_dict() for r in rules], selected=best.text(), cost=best.cost,
                          minimum_cost_alternatives=sum(p.cost == best.cost for p in solutions),
                          used_learned_library=any(any(r.head.pred == p and r.origin == 'learned'
                                                       for r in self.kb.rules.values()) for p, _ in best.steps))
        report.update(candidates=self.candidates, joins=self.joins, feature_work=feature_work,
                      semantic_states=len(seen), ms=(perf_counter() - self.started) * 1000)
        return report


    def fit_with_invention(self, target: str, allowed: list[str] | None = None,
                           install: bool = True, max_inventions: int = 64,
                           helper_length: int = 2) -> dict:
        """Retry a failed relation by inventing one reusable intermediate path.

        The helper is not named by the caller and is not domain-specific.  We
        enumerate short path compositions over the same relevant predicates used
        by ``fit``.  A helper is retained only when the target becomes learnable
        *and* the selected target program actually depends on that helper.

        This is a bounded predicate-invention experiment, not unrestricted logic
        synthesis.  It deliberately refuses to invent after an incomplete base
        search so that a budget failure is not disguised as representational
        progress.
        """
        invention_started=perf_counter()
        self._extension_cache.clear();self._extension_stack.clear();self._preserve_extension_cache=True
        base=self.fit(target, allowed=allowed, install=install)
        base_candidates=int(base.get('candidates',0) or 0)
        base['predicate_invention_used']=False
        base['invention_attempts']=0
        base['invention_base_candidates']=base_candidates
        if (base.get('status') != 'no_solution' or not base.get('search_complete', True)
                or helper_length != 2 or max_inventions <= 0):
            self._preserve_extension_cache=False
            return base

        predicates=[p for p in base.get('predicate_selected', [])
                    if p != target and not p.startswith('!') and self.kb.arity.get(p) == 2]
        candidates=[]
        # Preserve relevance ranking of predicates and prefer fewer inversions.
        # This is a generic simplicity bias: direct compositions are cheaper to
        # explain/execute than equivalent doubly-inverted helpers.
        inversion_patterns=((False,False),(False,True),(True,False),(True,True))
        for inv_p,inv_q in inversion_patterns:
            for p in predicates:
                for q in predicates:
                    candidates.append(Path(((p,inv_p),(q,inv_q))))
        unique=[];seen_text=set()
        for path in candidates:
            txt=path.text()
            if txt in seen_text: continue
            seen_text.add(txt);unique.append(path)

        attempts=[]
        for path in unique[:max_inventions]:
            digest=hashlib.blake2b((target+'|'+path.text()).encode('utf8'),digest_size=8).hexdigest()
            helper='invent_'+digest
            if helper == target:
                continue
            evidence=(f'invented_for:{target}',f'definition:{path.text()}')
            rules=path.rules(helper,evidence)
            try:
                for rule in rules:self.kb.add_rule(rule)
                trial=self.fit(target, allowed=allowed, install=install)
                selected=str(trial.get('selected') or '')
                used=helper in selected or any(
                    any(a.get('pred')==helper for a in rd.get('body',()))
                    for rd in trial.get('rules',())
                )
                attempts.append({'helper':helper,'definition':path.text(),
                                 'target_status':trial.get('status'),'used':used,
                                 'candidates':trial.get('candidates')})
                if trial.get('status')=='learned_hypothesis' and used:
                    trial['predicate_invention_used']=True
                    trial['invented_predicate']=helper
                    trial['invention_definition']=path.text()
                    trial['invention_attempts']=len(attempts)
                    trial['invention_trace']=attempts
                    trial['invention_base_candidates']=base_candidates
                    trial['invention_total_target_candidates']=base_candidates + sum(int(a.get('candidates') or 0) for a in attempts)
                    trial['invention_total_ms']=(perf_counter()-invention_started)*1000
                    self._preserve_extension_cache=False
                    return trial
                # The helper did not explain the improvement.  Remove both it and
                # any target rule installed by this trial before trying another.
                self.kb.withdraw_learned(target)
            finally:
                # Keep only the successful helper.  If the trial succeeded and
                # returned above, execution never reaches this line.
                if not (attempts and attempts[-1].get('used') and attempts[-1].get('target_status')=='learned_hypothesis'):
                    for rule in rules:self.kb.remove_rule(rule.id)
        # Ensure no failed helper or target hypothesis survives.
        self.kb.withdraw_learned(target)
        base['invention_attempts']=len(attempts)
        base['invention_trace']=attempts
        base['invention_total_target_candidates']=base_candidates + sum(int(a.get('candidates') or 0) for a in attempts)
        base['invention_total_ms']=(perf_counter()-invention_started)*1000
        self._preserve_extension_cache=False
        return base

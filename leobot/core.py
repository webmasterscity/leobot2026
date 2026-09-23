"""Small, auditable, function-free Horn engine. Python stdlib only.
Facts are indexed, conclusions are computed on demand, not cached between queries.
Explicit negation (!p) is not negation-as-failure; missing information is unknown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from time import perf_counter
import re
from typing import Iterator


def variable(s: str) -> bool:
    return s.startswith('?')


@dataclass(frozen=True)
class Atom:
    pred: str
    args: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'args', tuple(self.args))
        if not re.fullmatch(r'!?[A-Za-z_][A-Za-z_0-9]*', self.pred):
            raise ValueError('Predicado inválido.')
        if not 1 <= len(self.args) <= 8 or any(not isinstance(a, str) or not a for a in self.args):
            raise ValueError('Se requieren entre 1 y 8 argumentos de texto no vacíos.')

    @property
    def ground(self) -> bool:
        return not any(variable(x) for x in self.args)

    def opposite(self) -> Atom:
        return Atom(self.pred[1:] if self.pred.startswith('!') else '!' + self.pred, self.args)

    def as_dict(self) -> dict:
        return {'pred': self.pred, 'args': list(self.args)}

    @classmethod
    def from_dict(cls, obj: dict) -> Atom:
        return cls(obj['pred'], tuple(obj['args']))

    @classmethod
    def parse(cls, text: str) -> Atom:
        m = re.fullmatch(r'\s*(!?[A-Za-z_][A-Za-z_0-9]*)\s*\(([^()]*)\)\s*', text)
        if not m:
            raise ValueError('Usa relación(argumento, argumento).')
        return cls(m[1], tuple(x.strip() for x in m[2].split(',')))

    def __str__(self) -> str:
        return f'{self.pred}({", ".join(self.args)})'


@dataclass(frozen=True)
class Rule:
    id: str
    head: Atom
    body: tuple[Atom, ...]
    origin: str = 'taught'
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'body', tuple(self.body))
        object.__setattr__(self, 'evidence', tuple(self.evidence))
        if not self.body or len(self.body) > 16:
            raise ValueError('Una regla necesita entre 1 y 16 condiciones.')
        bound = {x for a in self.body for x in a.args if variable(x)}
        if any(variable(x) and x not in bound for x in self.head.args):
            raise ValueError('Variable de salida sin vincular en las condiciones.')
        if self.origin not in ('taught', 'learned'):
            raise ValueError('Origen de regla inválido.')

    def as_dict(self) -> dict:
        return {'id': self.id, 'head': self.head.as_dict(), 'body': [a.as_dict() for a in self.body],
                'origin': self.origin, 'evidence': list(self.evidence)}

    @classmethod
    def from_dict(cls, d: dict) -> Rule:
        return cls(d['id'], Atom.from_dict(d['head']), tuple(Atom.from_dict(a) for a in d['body']),
                   d.get('origin', 'taught'), tuple(d.get('evidence', [])))

    def __str__(self) -> str:
        return f'{self.head} <- ' + ' & '.join(map(str, self.body))


def unify(pattern: tuple[str, ...], values: tuple[str, ...], bindings: dict[str, str] | None = None) -> dict | None:
    if len(pattern) != len(values):
        return None
    out = dict(bindings or {})
    for p, value in zip(pattern, values):
        if variable(p):
            if p in out and out[p] != value:
                return None
            out[p] = value
        elif p != value:
            return None
    return out


class KnowledgeBase:
    def __init__(self) -> None:
        self.facts: dict[str, dict] = {}
        self.buckets: dict[str, set[str]] = defaultdict(set)
        self.indices: dict[tuple[str, int, str], set[str]] = defaultdict(set)
        # Reverse semantic index used by learners to retrieve only predicates
        # touching entities in the current problem.  This prevents search cost
        # from growing with every unrelated predicate in memory.
        self.entity_predicates: dict[str, set[str]] = defaultdict(set)
        self.entity_predicate_counts: dict[tuple[str, str], int] = defaultdict(int)
        self.dedup: dict[tuple[Atom, str], str] = {}
        self.arity: dict[str, int] = {}
        self.rules: dict[str, Rule] = {}
        self.heads: dict[str, dict[str, Rule]] = defaultdict(dict)
        self.examples: dict[str, dict[tuple[str, str], set[bool]]] = {}
        self.audit: list[dict] = []
        self.next_id = 0
        self.revision = 0

    def _check(self, a: Atom, commit: bool = True) -> None:
        pred = a.pred.lstrip('!')
        if pred in self.arity and self.arity[pred] != len(a.args):
            raise ValueError(f'Aridad incompatible: {pred}.')
        if commit:
            self.arity[pred] = len(a.args)

    def add(self, atom: Atom, source: str = 'usuario') -> str:
        if not atom.ground:
            raise ValueError('Un hecho no puede contener variables.')
        self._check(atom)
        key = (atom, source)
        if key in self.dedup:
            return self.dedup[key]
        self.next_id += 1
        fid = f'f{self.next_id}'
        self.facts[fid] = {'id': fid, 'atom': atom, 'source': source}
        self.buckets[atom.pred].add(fid)
        for pos, value in enumerate(atom.args):
            self.indices[(atom.pred, pos, value)].add(fid)
            base = atom.pred.lstrip('!')
            self.entity_predicate_counts[(value, base)] += 1
            self.entity_predicates[value].add(base)
        self.dedup[key] = fid
        self.revision += 1
        return fid

    def remove(self, fid: str) -> bool:
        if fid not in self.facts:
            return False
        fact = self.facts.pop(fid)
        atom = fact['atom']
        self.buckets[atom.pred].remove(fid)
        for pos, value in enumerate(atom.args):
            self.indices[(atom.pred, pos, value)].remove(fid)
            base = atom.pred.lstrip('!')
            key = (value, base)
            self.entity_predicate_counts[key] -= 1
            if self.entity_predicate_counts[key] <= 0:
                self.entity_predicate_counts.pop(key, None)
                self.entity_predicates[value].discard(base)
                if not self.entity_predicates[value]:
                    self.entity_predicates.pop(value, None)
        del self.dedup[(atom, fact['source'])]
        self.revision += 1
        return True

    def replace(self, fid: str, new: Atom) -> str:
        if fid not in self.facts:
            raise ValueError('No existe el hecho que quieres corregir.')
        if not new.ground:
            raise ValueError('La corrección debe ser concreta.')
        self._check(new, commit=False)
        old = self.facts[fid]
        self.remove(fid)
        nid = self.add(new, old['source'])
        self.audit.append({'event': 'correction', 'old': fid, 'new': nid,
                           'old_atom': old['atom'].as_dict(), 'new_atom': new.as_dict(),
                           'source': old['source']})
        return nid

    def matches(self, pattern: Atom) -> Iterator[dict]:
        ids = self.buckets.get(pattern.pred, set())
        for pos, value in enumerate(pattern.args):
            if not variable(value):
                other = self.indices.get((pattern.pred, pos, value), set())
                if len(other) < len(ids):
                    ids = other
        # IDs are sorted only within the selected bucket for reproducible proofs.
        for fid in sorted(ids, key=lambda x: int(x[1:])):
            fact = self.facts[fid]
            if unify(pattern.args, fact['atom'].args) is not None:
                yield fact

    def contains(self, atom: Atom) -> bool:
        return next(self.matches(atom), None) is not None

    def get_fact(self, fid: str) -> dict | None:
        return self.facts.get(fid)

    def fact_source(self, fid: str) -> str:
        return self.facts.get(fid, {}).get('source', 'retirado')

    def predicates_for_entities(self, entities: set[str]) -> dict[str, int]:
        score: dict[str, int] = defaultdict(int)
        for entity in entities:
            for pred in self.entity_predicates.get(entity, ()):
                score[pred] += 1
        return score

    def known_entities(self, candidates: set[str]) -> set[str]:
        return {value for value in candidates if value in self.entity_predicates}

    def neighbor_entities(self, entities: set[str], predicates: set[str] | None = None,
                          max_neighbors: int = 512) -> set[str]:
        """Return entities one binary-relation hop from ``entities`` using indexes.

        This bounded semantic-neighborhood primitive lets learners discover
        predicates that occur only on intermediate nodes without scanning every
        fact in memory.
        """
        out: set[str] = set()
        for entity in sorted(entities):
            preds = self.entity_predicates.get(entity, set())
            if predicates is not None:
                preds = preds & predicates
            for pred in sorted(preds):
                if self.arity.get(pred) != 2:
                    continue
                for pos in (0, 1):
                    for fid in self.indices.get((pred, pos, entity), ()):
                        atom = self.facts[fid]['atom']
                        for value in atom.args:
                            if value != entity:
                                out.add(value)
                                if len(out) >= max_neighbors:
                                    return out
        return out

    def add_rule(self, rule: Rule) -> None:
        proposed = dict(self.arity)
        for a in (rule.head, *rule.body):
            p = a.pred.lstrip('!')
            if p in proposed and proposed[p] != len(a.args):
                raise ValueError(f'Aridad incompatible: {p}.')
            proposed[p] = len(a.args)
        self.remove_rule(rule.id)
        self.arity = proposed
        self.rules[rule.id] = rule
        self.heads[rule.head.pred][rule.id] = rule
        self.revision += 1

    def remove_rule(self, rid: str) -> None:
        if rid in self.rules:
            rule = self.rules.pop(rid)
            self.heads[rule.head.pred].pop(rid, None)
            self.revision += 1

    def withdraw_learned(self, target: str) -> int:
        todo, seen, removed = [target], set(), 0
        while todo:
            pred = todo.pop()
            if pred in seen:
                continue
            seen.add(pred)
            for rule in list(self.rules.values()):
                if rule.origin == 'learned' and (rule.head.pred == pred or any(a.pred == pred for a in rule.body)):
                    todo.append(rule.head.pred)
                    self.remove_rule(rule.id)
                    removed += 1
        return removed

    def add_example(self, target: str, args: tuple[str, str], positive: bool) -> bool:
        a = Atom(target, tuple(args))
        if not a.ground or len(args) != 2 or not isinstance(positive, bool):
            raise ValueError('Se requieren un par concreto y una etiqueta booleana.')
        self._check(a)
        labels = self.examples.setdefault(target, {}).setdefault(tuple(args), set())
        if positive in labels:
            return False
        labels.add(positive)
        removed = self.withdraw_learned(target)
        self.audit.append({'event': 'example', 'target': target, 'args': list(args),
                           'positive': positive, 'withdrawn_rules': removed})
        return True

    def stats(self) -> dict:
        return {'facts': len(self.facts), 'rules': len(self.rules), 'predicates': len(self.arity),
                'examples': sum(len(v) for v in self.examples.values()), 'revision': self.revision}

    def as_dict(self) -> dict:
        return {'version': 1, 'next_id': self.next_id,
                'facts': [{'id': f['id'], 'atom': f['atom'].as_dict(), 'source': f['source']} for f in self.facts.values()],
                'rules': [r.as_dict() for r in self.rules.values()],
                'examples': {p: [{'args': list(a), 'labels': sorted(labels)} for a, labels in es.items()]
                             for p, es in self.examples.items()}, 'audit': self.audit}

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeBase:
        if data.get('version') != 1:
            raise ValueError('Formato de memoria no compatible.')
        kb = cls()
        for fact in data.get('facts', []):
            fid = fact['id']
            if not re.fullmatch(r'f[1-9][0-9]*', fid) or fid in kb.facts:
                raise ValueError('ID de hecho inválido o duplicado.')
            kb.next_id = int(fid[1:]) - 1
            if kb.add(Atom.from_dict(fact['atom']), fact['source']) != fid:
                raise ValueError('Hecho duplicado en archivo.')
        kb.next_id = max(data.get('next_id', 0), max((int(x[1:]) for x in kb.facts), default=0))
        for rd in data.get('rules', []):
            kb.add_rule(Rule.from_dict(rd))
        for pred, entries in data.get('examples', {}).items():
            kb.examples[pred] = {tuple(e['args']): set(e['labels']) for e in entries}
        kb.audit = data.get('audit', [])
        return kb


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Proof:
    atom: Atom
    kind: str
    id: str
    children: tuple[Proof, ...] = ()
    hypothesis: bool = False
    contested: bool = False
    cost: int = 1

    def as_dict(self, kb: KnowledgeBase, depth: int = 12) -> dict:
        result = {'atom': self.atom.as_dict(), 'kind': self.kind, 'id': self.id,
                  'hypothesis': self.hypothesis, 'contested': self.contested}
        if self.kind == 'fact':
            result['source'] = kb.fact_source(self.id) if hasattr(kb, 'fact_source') else 'retirado'
        elif self.kind == 'compiled':
            result['algorithm'] = self.id
        else:
            rule = kb.rules.get(self.id)
            if rule:
                result.update(rule=str(rule), evidence=list(rule.evidence))
        result['children'] = [p.as_dict(kb, depth - 1) for p in self.children] if depth else []
        if not depth and self.children:
            result['truncated'] = True
        return result


class Engine:
    """Variant-tabled, demand-driven fixed-point evaluation, with explicit budgets.

    All query tables are discarded after each query. A proof is a finite tree, even
    for recursive rules, and ranks favor direct/non-learned/uncontested evidence.
    """
    def __init__(self, kb: KnowledgeBase, max_work: int = 200_000, max_answers: int = 30_000,
                 max_rounds: int = 128, max_depth: int = 80, reuse_within_round: bool = True) -> None:
        self.kb = kb
        self.max_work, self.max_answers = max_work, max_answers
        self.max_rounds, self.max_depth = max_rounds, max_depth
        self.reuse_within_round = reuse_within_round

    @staticmethod
    def canonical(a: Atom) -> Atom:
        names: dict[str, str] = {}
        return Atom(a.pred, tuple(names.setdefault(v, '?' + str(len(names))) if variable(v) else v for v in a.args))

    def _tick(self, n: int = 1) -> None:
        self.work += n
        if self.work > self.max_work:
            raise BudgetExceeded('Presupuesto de operaciones agotado.')

    def _put(self, query: Atom, proof: Proof) -> None:
        rows = self.tables[query]
        old = rows.get(proof.atom.args)
        rank = lambda p: (p.hypothesis, p.contested, p.cost)
        if old is None or rank(proof) < rank(old):
            if old is None:
                self.answer_count += 1
                if self.answer_count > self.max_answers:
                    raise BudgetExceeded('Presupuesto de resultados intermedios agotado.')
            rows[proof.atom.args] = proof
            self.changed = True

    def _demand(self, raw: Atom) -> list[Proof]:
        q = self.canonical(raw)
        self._tick()
        if q not in self.tables:
            self.tables[q] = {}
            self.changed = True
        if q in self.busy or (self.reuse_within_round and q in self.visited):
            return list(self.tables[q].values())
        self.visited.add(q)
        if self.depth >= self.max_depth:
            raise BudgetExceeded('Presupuesto de profundidad agotado.')
        self.busy.add(q)
        self.depth += 1
        try:
            for fact in self.kb.matches(q):
                self._tick()
                atom = fact['atom']
                self._put(q, Proof(atom, 'fact', fact['id'], contested=self.kb.contains(atom.opposite())))
            for rule in self.kb.heads.get(q.pred, {}).values():
                bindings: dict[str, str] | None = {}
                for pos, value in enumerate(q.args):
                    if not variable(value):
                        bindings = unify((rule.head.args[pos],), (value,), bindings)
                        if bindings is None:
                            break
                if bindings is None:
                    continue
                states = [(bindings, (), rule.body)]
                while states:
                    bindings, children, remaining = states.pop()
                    self._tick()
                    if not remaining:
                        args = tuple(bindings.get(v, v) for v in rule.head.args)
                        if any(variable(v) for v in args) or unify(q.args, args) is None:
                            continue
                        self._put(q, Proof(Atom(q.pred, args), 'rule', rule.id, children,
                                           rule.origin == 'learned' or any(p.hypothesis for p in children),
                                           any(p.contested for p in children), 1 + sum(p.cost for p in children)))
                        continue
                    best = max(range(len(remaining)), key=lambda i: sum(not variable(v) or v in bindings for v in remaining[i].args))
                    atom = remaining[best]
                    rest = remaining[:best] + remaining[best + 1:]
                    sub = Atom(atom.pred, tuple(bindings.get(v, v) for v in atom.args))
                    for proof in self._demand(sub):
                        self._tick()
                        new_bindings = unify(atom.args, proof.atom.args, bindings)
                        if new_bindings is not None:
                            states.append((new_bindings, children + (proof,), rest))
                            if len(states) > self.max_answers:
                                raise BudgetExceeded('Presupuesto de uniones intermedias agotado.')
        finally:
            self.busy.remove(q)
            self.depth -= 1
        return list(self.tables[q].values())

    def _compiled_closure(self, query: Atom, started: float) -> dict | None:
        """Fast path for the exact transitive-closure schema learned by Path.rules.

        It uses indexed BFS for a query with at least one bound endpoint.  This
        removes Python recursion depth from long chains and performs work roughly
        proportional to the reachable subgraph instead of repeated fixed points.
        """
        if len(query.args) != 2 or variable(query.args[0]) and variable(query.args[1]):
            return None
        base = self.kb.rules.get(f'learned:{query.pred}:base')
        rec = self.kb.rules.get(f'learned:{query.pred}:rec')
        if not base or not rec or len(base.body) != 1 or len(rec.body) != 2:
            return None
        edge_atom = base.body[0]
        if self.kb.heads.get(edge_atom.pred):
            return None  # keep the generic engine for a derived edge relation
        hx, hy = base.head.args
        if edge_atom.args == (hx, hy):
            inverse = False
        elif edge_atom.args == (hy, hx):
            inverse = True
        else:
            return None
        from collections import deque
        forward = not variable(query.args[0])
        anchor = query.args[0] if forward else query.args[1]
        target = query.args[1] if forward and not variable(query.args[1]) else (query.args[0] if not forward and not variable(query.args[0]) else None)
        queue = deque([anchor])
        reached = {anchor}
        proof_by_node: dict[str, Proof | None] = {anchor: None}
        answers: dict[tuple[str, str], Proof] = {}
        work = 0
        complete, reason = True, None
        try:
            while queue:
                node = queue.popleft()
                if forward:
                    pat = Atom(edge_atom.pred, ('?z', node) if inverse else (node, '?z'))
                else:
                    pat = Atom(edge_atom.pred, (node, '?z') if inverse else ('?z', node))
                for fact in self.kb.matches(pat):
                    work += 1
                    if work > self.max_work:
                        raise BudgetExceeded('Presupuesto de operaciones agotado.')
                    raw = fact['atom']
                    other = raw.args[0] if (forward and inverse) or (not forward and not inverse) else raw.args[1]
                    if other in reached:
                        continue
                    reached.add(other)
                    queue.append(other)
                    edge_proof = Proof(raw, 'fact', fact['id'], contested=self.kb.contains(raw.opposite()))
                    previous = proof_by_node[node]
                    logical = Atom(query.pred, (anchor, other) if forward else (other, anchor))
                    children = (edge_proof,) if previous is None else ((previous, edge_proof) if forward else (edge_proof, previous))
                    cp = Proof(logical, 'compiled', f'indexed_bfs_closure:{query.pred}', children,
                               hypothesis=True, contested=edge_proof.contested or (previous.contested if previous else False),
                               cost=1 + (previous.cost if previous else 0))
                    proof_by_node[other] = cp
                    if unify(query.args, logical.args) is not None:
                        answers[logical.args] = cp
                        if len(answers) > self.max_answers:
                            raise BudgetExceeded('Presupuesto de resultados intermedios agotado.')
                        if target is not None and other == target:
                            queue.clear()
                            break
        except BudgetExceeded as exc:
            complete, reason = False, str(exc)
        return {'answers': list(answers.values()), 'complete': complete, 'reason': reason,
                'stats': {'work': work, 'variants': 1, 'rounds': 1,
                          'intermediate_answers': len(answers), 'ms': (perf_counter() - started) * 1000,
                          'compiled': True}}

    def query(self, query: Atom) -> dict:
        self.kb._check(query, commit=False)
        started = perf_counter()
        compiled = self._compiled_closure(query, started)
        if compiled is not None:
            return compiled
        self.tables: dict[Atom, dict[tuple, Proof]] = {}
        self.busy: set[Atom] = set()
        self.depth = self.work = self.answer_count = 0
        rounds, complete, reason = 0, True, None
        try:
            while True:
                self.changed = False
                self.visited: set[Atom] = set()
                rounds += 1
                self._demand(query)
                for q in list(self.tables):
                    self._demand(q)
                if not self.changed:
                    break
                if rounds >= self.max_rounds:
                    raise BudgetExceeded('Presupuesto de iteraciones agotado.')
        except (BudgetExceeded, RecursionError) as exc:
            complete, reason = False, str(exc)
        answers = list(self.tables.get(self.canonical(query), {}).values())
        return {'answers': answers, 'complete': complete, 'reason': reason,
                'stats': {'work': self.work, 'variants': len(self.tables), 'rounds': rounds,
                          'intermediate_answers': self.answer_count, 'ms': (perf_counter() - started) * 1000}}

    def answer(self, query: Atom, max_conflict_checks: int = 64) -> dict:
        pos = self.query(query)
        neg = self.query(query.opposite()) if query.ground else None
        p = pos['answers'][0] if pos['answers'] else None
        n = neg['answers'][0] if neg and neg['answers'] else None
        complete = pos['complete'] and (not neg or neg['complete'])
        contested = any(x.contested for x in (p, n) if x)
        checks = 0
        # Check derived as well as explicit contradictions in returned proof trees.
        # Do not call answer recursively: proof graph traversal is finite.
        stack = list(pos['answers']) + (list(neg['answers']) if neg else [])
        seen: set[Atom] = set()
        while stack:
            proof = stack.pop()
            if proof.atom in seen:
                continue
            seen.add(proof.atom)
            stack.extend(proof.children)
            if checks >= max_conflict_checks:
                complete = False
                break
            other = self.query(proof.atom.opposite())
            checks += 1
            complete = complete and other['complete']
            contested = contested or bool(other['answers'])
        if p and n:
            status = 'conflict'
        elif not complete:
            status = 'incomplete'
        elif contested:
            status = 'contested'
        elif not query.ground:
            status = 'bindings'
        elif p:
            status = 'hypothesis' if p.hypothesis else 'supported'
        elif n:
            status = 'negative_hypothesis' if n.hypothesis else 'refuted'
        else:
            status = 'unknown'
        return {'status': status, 'query': query, 'positive': pos, 'negative': neg, 'conflict_checks': checks}

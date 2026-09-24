"""Bounded non-neural synthesis of integer expressions from input/output examples.

The primitives are general arithmetic, not solutions by topic. Signatures include
unlabelled probes; ambiguous minimum-size programs may request another example.
Agreement is always a hypothesis, never proof outside the supplied examples.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product, permutations
from random import Random
from time import perf_counter
from collections import defaultdict
import hashlib
import re

OPS = ('add', 'sub', 'mul', 'floordiv', 'mod', 'min', 'max')
# G-39: generic index access into a context grid (-1 outside it).  Only
# available when a search is given contexts; it is substrate, not a solution.
# G-39b: generic aggregation/iteration over the same grid (0 is background):
# nb = non-zero 8-neighbours, comp = size of the 4-connected same-colour part.
CONTEXT_OPS = ('at', 'nb', 'comp')
# Whole-grid aggregates, given to grid programs as variables after (h, w).
GRID_FEATURES = ('moda', 'mas_frecuente', 'menos_frecuente', 'colores',
                 'arriba', 'izquierda', 'alto_dibujo', 'ancho_dibujo')
LEAF_OPS = frozenset(('var', 'const', 'call', 'pcall'))
COMMUTATIVE = frozenset(('add', 'mul', 'min', 'max'))
LIMIT = 10 ** 12


class GridContext:
    """A grid with its generic aggregates, computed once per grid."""
    __slots__ = ('grid', 'features', 'neighbours', 'components')

    def __init__(self, grid) -> None:
        self.grid = grid
        h, w = len(grid), len(grid[0])
        counts: dict[int, int] = defaultdict(int)
        for row in grid:
            for v in row:
                counts[v] += 1
        nonzero = {k: n for k, n in counts.items() if k}
        rows = [r for r in range(h) if any(grid[r])]
        cols = [c for c in range(w) if any(grid[r][c] for r in range(h))]
        # G-39c: ties go to the colour seen first in reading order, never to
        # its code, so renaming colours renames these values and nothing else.
        self.features = (max(counts, key=lambda k: counts[k]),
                         max(nonzero, key=lambda k: nonzero[k]) if nonzero else 0,
                         min(nonzero, key=lambda k: nonzero[k]) if nonzero else 0,
                         len(nonzero), rows[0] if rows else 0, cols[0] if cols else 0,
                         rows[-1] - rows[0] + 1 if rows else 0, cols[-1] - cols[0] + 1 if cols else 0)
        self.neighbours = [[sum(1 for di in (-1, 0, 1) for dj in (-1, 0, 1)
                                if (di or dj) and 0 <= r + di < h and 0 <= c + dj < w and grid[r + di][c + dj])
                            for c in range(w)] for r in range(h)]
        label = [[-1] * w for _ in range(h)]
        sizes: list[int] = []
        for r in range(h):
            for c in range(w):
                if label[r][c] >= 0:
                    continue
                label[r][c], stack, n = len(sizes), [(r, c)], 0
                while stack:
                    x, y = stack.pop(); n += 1
                    for u, v in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= u < h and 0 <= v < w and label[u][v] < 0 and grid[u][v] == grid[x][y]:
                            label[u][v] = len(sizes); stack.append((u, v))
                sizes.append(n)
        self.components = [[sizes[label[r][c]] for c in range(w)] for r in range(h)]


def context_op(op: str, ctx, i: int | None, j: int | None) -> int | None:
    if ctx is None or i is None or j is None:
        return None
    if not (0 <= i < len(ctx.grid) and 0 <= j < len(ctx.grid[0])):
        return -1
    table = ctx.grid if op == 'at' else ctx.neighbours if op == 'nb' else ctx.components
    return table[i][j]


def operate(op: str, a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    if op == 'add': value = a + b
    elif op == 'sub': value = a - b
    elif op == 'mul': value = a * b
    elif op == 'floordiv':
        if b == 0: return None
        value = a // b
    elif op == 'mod':
        if b == 0: return None
        value = a % b
    elif op == 'min': value = min(a, b)
    elif op == 'max': value = max(a, b)
    else: raise ValueError('Operación no permitida.')
    return value if abs(value) <= LIMIT else None


@dataclass(frozen=True)
class Expr:
    op: str
    value: int | str = 0
    children: tuple[Expr, ...] = ()

    def __post_init__(self) -> None:
        if self.op in ('var', 'const'):
            if self.children or not isinstance(self.value, int):
                raise ValueError('Hoja inválida.')
        elif self.op == 'color':
            # G-39c: a colour is a symbol taken from the data, not a number.
            if self.children or type(self.value) is not int or not 0 <= self.value <= 9:
                raise ValueError('Color inválido.')
        elif self.op == 'call':
            if self.children or not isinstance(self.value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', self.value):
                raise ValueError('Referencia de habilidad inválida.')
        elif self.op == 'pcall':
            if not isinstance(self.value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', self.value):
                raise ValueError('Referencia paramétrica inválida.')
            if not 1 <= len(self.children) <= 4 or any(c.op not in ('var','const') for c in self.children):
                raise ValueError('Los argumentos de una primitiva deben ser variables o constantes simples.')
        elif self.op not in OPS + CONTEXT_OPS or len(self.children) != 2:
            raise ValueError('Programa fuera del DSL permitido.')

    def run(self, args: tuple[int, ...], resolver=None, memo: dict | None = None, stack: tuple[str, ...] = (),
            grid=None) -> int | None:
        if self.op == 'var':
            return args[self.value] if 0 <= self.value < len(args) else None
        if self.op in ('const', 'color'):
            return self.value
        if self.op == 'call':
            if resolver is None:
                return None
            return resolver(self.value, args, memo if memo is not None else {}, stack)
        if self.op == 'pcall':
            if resolver is None:
                return None
            mapped = tuple(child.run(args, None, None, ()) for child in self.children)
            if any(v is None for v in mapped):
                return None
            return resolver(self.value, mapped, memo if memo is not None else {}, stack)
        if self.op in CONTEXT_OPS:
            return context_op(self.op, grid, self.children[0].run(args, resolver, memo, stack, grid),
                              self.children[1].run(args, resolver, memo, stack, grid))
        return operate(self.op, self.children[0].run(args, resolver, memo, stack, grid),
                       self.children[1].run(args, resolver, memo, stack, grid))

    def __str__(self) -> str:
        if self.op == 'var': return f'x{self.value}'
        if self.op == 'const': return str(self.value)
        if self.op == 'color': return f'color{self.value}'
        if self.op == 'call': return '@' + str(self.value)
        if self.op == 'pcall': return '@' + str(self.value) + '(' + ','.join(map(str,self.children)) + ')'
        if self.op in CONTEXT_OPS: return f'{self.op}({self.children[0]}, {self.children[1]})'
        sym = {'add': '+', 'sub': '-', 'mul': '*', 'floordiv': '//', 'mod': '%'}
        a, b = map(str, self.children)
        return f'({a} {sym[self.op]} {b})' if self.op in sym else f'{self.op}({a}, {b})'

    def as_dict(self) -> dict:
        return {'op': self.op, 'value': self.value, 'children': [x.as_dict() for x in self.children]}

    @classmethod
    def from_dict(cls, obj: dict, depth: int = 0) -> Expr:
        if depth > 32:
            raise ValueError('Programa demasiado profundo.')
        return cls(obj['op'], obj.get('value', 0), tuple(cls.from_dict(x, depth + 1) for x in obj.get('children', [])))


@dataclass(frozen=True)
class RecurrenceProgram:
    """Recurrence whose body is itself a synthesized arithmetic program.

    body inputs are x0=n, x1=f(n-1), ..., xL=f(n-L).  The learner chooses L
    (currently up to 3 by default) and synthesizes body from the same arithmetic
    DSL used for ordinary skills.
    """
    lag: int
    bases: tuple[tuple[int, int], ...]
    body: Expr

    def __post_init__(self) -> None:
        if not 1 <= self.lag <= 3 or len(self.bases) < self.lag:
            raise ValueError('Recurrencia general inválida.')

    def run(self, args: tuple[int, ...], resolver=None, memo=None, stack=()) -> int | None:
        if len(args) != 1 or type(args[0]) is not int:
            return None
        n=args[0]; cache=dict(self.bases); lo=min(cache)
        if n in cache:return cache[n]
        if n < lo or n-lo > 100_000:return None
        start=max(cache)+1
        for i in range(start,n+1):
            prev=[]
            for k in range(1,self.lag+1):
                if i-k not in cache:return None
                prev.append(cache[i-k])
            value=self.body.run((i,*prev))
            if value is None:return None
            cache[i]=value
        return cache.get(n)

    def _body_text(self, e: Expr) -> str:
        if e.op=='var':
            return 'n' if e.value==0 else f'f(n-{e.value})'
        if e.op=='const':return str(e.value)
        if e.op=='call':return '@'+str(e.value)
        sym={'add':'+','sub':'-','mul':'*','floordiv':'//','mod':'%'}
        a,b=(self._body_text(x) for x in e.children)
        return f'({a} {sym[e.op]} {b})' if e.op in sym else f'{e.op}({a},{b})'

    def __str__(self) -> str:
        return f'f(n)={self._body_text(self.body)}; base={dict(self.bases)}'

    def as_dict(self) -> dict:
        return {'op':'recurrence_expr','lag':self.lag,'bases':[list(x) for x in self.bases],'body':self.body.as_dict()}

    @classmethod
    def from_dict(cls,obj:dict)->'RecurrenceProgram':
        return cls(int(obj['lag']),tuple((int(a),int(b)) for a,b in obj['bases']),Expr.from_dict(obj['body']))


@dataclass(frozen=True)
class Recurrence:
    """Bounded one-variable recurrence learned from consecutive examples.

    This is a general program schema, not a factorial/Fibonacci special case.
    Supported forms combine f(n-1), f(n-2), n and a small inferred constant.
    """
    op: str
    form: str
    bases: tuple[tuple[int, int], ...]
    const: int = 0

    def __post_init__(self) -> None:
        if self.op not in OPS or self.form not in ('prev_n','n_prev','prev_const','const_prev','prev_prev2','prev2_prev'):
            raise ValueError('Recurrencia fuera del DSL permitido.')
        if not self.bases:
            raise ValueError('La recurrencia requiere casos base.')

    def run(self, args: tuple[int, ...], resolver=None, memo=None, stack=()) -> int | None:
        if len(args) != 1 or type(args[0]) is not int:
            return None
        n = args[0]
        cache = dict(self.bases)
        lo = min(cache); hi = max(cache)
        if n in cache:
            return cache[n]
        if n < lo or n - lo > 100_000:
            return None
        for i in range(lo, n + 1):
            if i in cache:
                continue
            p1 = cache.get(i-1); p2 = cache.get(i-2)
            if self.form == 'prev_n': value = operate(self.op, p1, i)
            elif self.form == 'n_prev': value = operate(self.op, i, p1)
            elif self.form == 'prev_const': value = operate(self.op, p1, self.const)
            elif self.form == 'const_prev': value = operate(self.op, self.const, p1)
            elif self.form == 'prev_prev2': value = operate(self.op, p1, p2)
            else: value = operate(self.op, p2, p1)
            if value is None:
                return None
            cache[i] = value
        return cache.get(n)

    def __str__(self) -> str:
        forms = {
            'prev_n': f'f(n)={self.op}(f(n-1),n)', 'n_prev': f'f(n)={self.op}(n,f(n-1))',
            'prev_const': f'f(n)={self.op}(f(n-1),{self.const})', 'const_prev': f'f(n)={self.op}({self.const},f(n-1))',
            'prev_prev2': f'f(n)={self.op}(f(n-1),f(n-2))', 'prev2_prev': f'f(n)={self.op}(f(n-2),f(n-1))'}
        return forms[self.form] + '; base=' + repr(dict(self.bases))

    def as_dict(self) -> dict:
        return {'op':'recurrence','rec_op':self.op,'form':self.form,'bases':[list(x) for x in self.bases],'const':self.const}

    @classmethod
    def from_dict(cls, obj: dict) -> 'Recurrence':
        return cls(obj['rec_op'], obj['form'], tuple((int(a),int(b)) for a,b in obj['bases']), int(obj.get('const',0)))


class ProgramLearner:
    def __init__(self, max_size: int = 7, max_candidates: int = 120_000, max_seconds: float = 8.0,
                 goal_directed: bool = True, auto_library_top_k: int = 16, allow_recurrence: bool = True,
                 auto_abstraction: bool = True, abstraction_min_support: int = 2,
                 abstraction_max_new: int = 8, max_signature_cells: int = 10_000_000) -> None:
        self.max_size, self.max_candidates, self.max_seconds = max_size, max_candidates, max_seconds
        # G-39b: explicit memory budget of a search (values held in retained
        # signatures); long grid signatures otherwise exhaust RAM first.
        self.max_signature_cells = int(max_signature_cells)
        self.goal_directed = goal_directed
        self.auto_library_top_k = max(0, int(auto_library_top_k))
        self.allow_recurrence = bool(allow_recurrence)
        self.auto_abstraction = bool(auto_abstraction)
        self.abstraction_min_support = max(2, int(abstraction_min_support))
        self.abstraction_max_new = max(0, int(abstraction_max_new))
        self.examples: dict[str, dict[tuple[int, ...], set[int]]] = {}
        self.solutions: dict[str, list[Expr]] = {}
        self.reports: dict[str, dict] = {}
        self.dependencies: dict[str, set[str]] = {}
        self.skill_concepts: dict[str, set[str]] = {}
        self.concept_skills: dict[str, set[str]] = defaultdict(set)
        # Learner-created reusable subprograms.  They are derived from repeated
        # structure across independently learned skills; they are not external examples.
        self.abstractions: dict[str, dict] = {}
        # Bounded evidence table for automatically proposed reusable primitives.
        # Its cardinality depends on the primitive search space, not the number
        # of learned skills.  Sets are serialized explicitly.
        self.abstraction_evidence: dict[str, dict] = {}
        self._abstraction_recipe_cache: dict[int, tuple] = {}
        # G-39: (input, output) grid pairs per grid skill.
        self.grid_examples: dict[str, list[tuple[tuple, tuple]]] = {}

    @staticmethod
    def _expr_calls(expr) -> set[str]:
        if isinstance(expr, Expr) and expr.op in ('call','pcall'):
            return {str(expr.value)}
        out: set[str] = set()
        for child in getattr(expr, 'children', ()):
            out.update(ProgramLearner._expr_calls(child))
        return out

    def _invalidate(self, skill: str) -> set[str]:
        # Changing a base skill invalidates every learned skill that depends on it.
        todo, invalid = [skill], set()
        while todo:
            cur = todo.pop()
            if cur in invalid:
                continue
            invalid.add(cur)
            todo.extend(name for name, deps in self.dependencies.items() if cur in deps)
            # An invented abstraction is epistemically dependent on the source
            # skills from which its repeated subprogram was induced, even when
            # its executable body is copied rather than calling those skills.
            todo.extend(name for name, meta in self.abstractions.items()
                        if cur in set(meta.get('source_skills', ())))
        for evidence in self.abstraction_evidence.values():
            evidence.get('source_skills', set()).difference_update(invalid)
        for name in invalid:
            self.solutions.pop(name, None)
            self.reports.pop(name, None)
            self.dependencies.pop(name, None)
            if name in self.abstractions:
                for concept in self.skill_concepts.get(name, set()):
                    self.concept_skills[concept].discard(name)
                self.skill_concepts.pop(name, None)
                self.abstractions.pop(name, None)
        return invalid

    @staticmethod
    def _expr_call_requests(expr: Expr, args: tuple[int, ...]) -> set[tuple[str, tuple[int, ...]]]:
        if expr.op == 'call':
            return {(str(expr.value), args)}
        if expr.op == 'pcall':
            mapped = tuple(child.run(args, None, None, ()) for child in expr.children)
            return set() if any(v is None for v in mapped) else {(str(expr.value), mapped)}
        out: set[tuple[str, tuple[int, ...]]] = set()
        for child in expr.children:
            out.update(ProgramLearner._expr_call_requests(child, args))
        return out

    def _resolve_call(self, skill: str, args: tuple[int, ...], memo: dict, stack: tuple[str, ...]) -> int | None:
        # General iterative evaluation of the dependency DAG.  Work items carry
        # their own argument tuple, so parameterized learned primitives can be
        # called on a permutation/subset of the caller's inputs without using
        # Python recursion, while 10k-deep ordinary DAGs remain safe.
        root = (skill, args)
        if root in memo:
            return memo[root]
        work = [(skill, args, False)]
        visiting: set[tuple[str, tuple[int, ...]]] = set()
        while work:
            name, current_args, expanded = work.pop()
            key = (name, current_args)
            if key in memo:
                continue
            programs = self.solutions.get(name, ())
            if not programs:
                memo[key] = None
                continue
            if expanded:
                visiting.discard(key)
                resolver = lambda dep, a, m, st: m.get((dep, a))
                values = {p.run(current_args, resolver, memo, ()) for p in programs}
                memo[key] = next(iter(values)) if len(values) == 1 else None
                continue
            if key in visiting:
                memo[key] = None
                continue
            visiting.add(key)
            work.append((name, current_args, True))
            requests: set[tuple[str, tuple[int, ...]]] = set()
            for program in programs:
                if isinstance(program, Expr):
                    requests.update(self._expr_call_requests(program, current_args))
            for dep, dep_args in sorted(requests, key=lambda x:(x[0],x[1]), reverse=True):
                dkey = (dep, dep_args)
                if dkey not in memo:
                    if dkey in visiting:
                        memo[dkey] = None
                    else:
                        work.append((dep, dep_args, False))
        return memo.get(root)

    def _run_expr(self, expr: Expr, args: tuple[int, ...]) -> int | None:
        return expr.run(args, self._resolve_call, {}, ())

    @staticmethod
    def _expr_size(expr: Expr) -> int:
        return 1 + sum(ProgramLearner._expr_size(child) for child in expr.children)

    @staticmethod
    def _compact_expr(expr: Expr) -> tuple[Expr, tuple[int, ...]]:
        """Rename used input variables densely, returning source mapping.

        Example: ``x1*x3`` becomes ``x0*x1`` with mapping ``(1,3)``.  This turns
        an induced fragment into a parameterized primitive rather than tying it
        to the positions where it was first observed.
        """
        used = sorted({int(node.value) for node in ProgramLearner._walk_expr(expr) if node.op == 'var'})
        if not used:
            return expr, ()
        remap = {old: new for new, old in enumerate(used)}
        def rewrite(node: Expr) -> Expr:
            if node.op == 'var':
                return Expr('var', remap[int(node.value)])
            if node.op == 'const':
                return node
            if node.op in ('call','pcall'):
                # Utility primitives are generated before calls are introduced;
                # keep this defensive path deterministic for persistence.
                return Expr(node.op, node.value, tuple(rewrite(c) for c in node.children))
            return Expr(node.op, node.value, tuple(rewrite(c) for c in node.children))
        return rewrite(expr), tuple(used)

    @staticmethod
    def _walk_expr(expr: Expr):
        yield expr
        for child in expr.children:
            yield from ProgramLearner._walk_expr(child)

    @staticmethod
    def _expr_vars(expr: Expr) -> set[int]:
        """Return caller input roles referenced by an expression.

        This is structural only: it does not inspect task names, labels or
        held-out answers.  It lets a cross-mechanism relevance prior reduce the
        variable alphabet without prescribing the operation that combines them.
        """
        out=set()
        for node in ProgramLearner._walk_expr(expr):
            if node.op=='var':
                out.add(int(node.value))
            elif node.op=='pcall':
                for child in node.children:
                    if child.op=='var': out.add(int(child.value))
        return out

    @staticmethod
    def _proper_subexpressions(expr: Expr):
        """Yield structural subprograms below the root, once per occurrence.

        Mining is deliberately structural and auditable: no task names, labels or
        held-out answers influence which candidate fragments are proposed.
        """
        for child in expr.children:
            yield child
            yield from ProgramLearner._proper_subexpressions(child)

    def _expr_dependency_roles(self, expr: Expr, seen: tuple[str, ...] = ()) -> set[int] | None:
        """Return caller input roles that can influence ``expr``.

        Calls are expanded through already learned programs so the result is a
        representation-level dependency certificate rather than a textual scan
        of one expression.  ``None`` means the dependency cannot be certified.
        """
        if expr.op=='var': return {int(expr.value)}
        if expr.op=='const': return set()
        if expr.op in OPS:
            left=self._expr_dependency_roles(expr.children[0],seen)
            right=self._expr_dependency_roles(expr.children[1],seen)
            return None if left is None or right is None else left|right
        if expr.op=='call':
            name=str(expr.value)
            if name in seen: return None
            deps=self.dependency_roles(name,seen+(name,))
            return None if deps is None else set(deps)
        if expr.op=='pcall':
            name=str(expr.value)
            if name in seen: return None
            deps=self.dependency_roles(name,seen+(name,))
            if deps is None: return None
            out=set()
            for i in deps:
                if i < 0 or i >= len(expr.children): return None
                child=expr.children[i]
                if child.op=='var': out.add(int(child.value))
                elif child.op=='const': pass
                else: return None
            return out
        return None

    def dependency_roles(self, skill: str, seen: tuple[str, ...] = ()) -> tuple[int, ...] | None:
        """Certify a stable unordered input-dependency set for a learned skill.

        Every retained minimum-size hypothesis must agree on the same dependency
        set.  If alternatives disagree, no cross-task representation is emitted.
        """
        bodies=self.solutions.get(skill,())
        if not bodies or any(not isinstance(x,Expr) for x in bodies):
            return None
        rows=[]
        for body in bodies:
            deps=self._expr_dependency_roles(body,seen)
            if deps is None: return None
            rows.append(tuple(sorted(deps)))
        return rows[0] if rows and all(x==rows[0] for x in rows) else None

    def _skill_arity(self, skill: str) -> int | None:
        examples = self.examples.get(skill)
        if examples:
            return len(next(iter(examples)))
        meta = self.abstractions.get(skill)
        return int(meta['arity']) if meta and 'arity' in meta else None

    def _primitive_recipe_index(self, arity: int):
        """Precompute a bounded library-learning index for one arity.

        Candidate primitives are all semantically distinct size-3 expressions
        over input variables and {-1,0,1}.  For each candidate we index every
        one-operation composition with a leaf.  A learned skill can therefore
        vote for a primitive by its behaviour on fixed, label-free probes.
        """
        cached = self._abstraction_recipe_cache.get(arity)
        if cached is not None:
            return cached
        points = tuple(self.probes(arity))
        leaves = [Expr('var', i) for i in range(arity)] + [Expr('const', c) for c in (-1, 0, 1)]
        leaf_sigs = {str(e): tuple(e.run(x) for x in points) for e in leaves}
        leaf_signature_set = set(leaf_sigs.values())
        primitive_by_sig: dict[tuple, Expr] = {}
        for left in leaves:
            for right in leaves:
                for op in OPS:
                    if op in COMMUTATIVE and str(left) > str(right):
                        continue
                    sig = tuple(operate(op, a, b) for a, b in zip(leaf_sigs[str(left)], leaf_sigs[str(right)]))
                    if any(v is None for v in sig) or sig in leaf_signature_set:
                        continue
                    expr = Expr(op, children=(left, right))
                    prev = primitive_by_sig.get(sig)
                    if prev is None or str(expr) < str(prev):
                        primitive_by_sig[sig] = expr

        recipes: dict[tuple, list[tuple[Expr, str, Expr, int, tuple]]] = defaultdict(list)
        for psig, primitive in primitive_by_sig.items():
            for leaf in leaves:
                lsig = leaf_sigs[str(leaf)]
                for op in OPS:
                    orientations = (0,) if op in COMMUTATIVE else (0, 1)
                    for orientation in orientations:
                        sig = tuple(operate(op, a, b) if orientation == 0 else operate(op, b, a)
                                    for a, b in zip(psig, lsig))
                        if any(v is None for v in sig):
                            continue
                        recipes[sig].append((primitive, op, leaf, orientation, psig))
        result = (points, recipes)
        self._abstraction_recipe_cache[arity] = result
        return result

    def _materialize_abstractions(self, support_needed: int, limit: int) -> list[dict]:
        if limit <= 0:
            return []
        ranked = []
        for key, item in self.abstraction_evidence.items():
            support = len(item.get('source_skills', ()))
            if support < support_needed:
                continue
            arity = int(item['arity']); text = str(item['program'])
            # If an ordinary learned skill already represents exactly this
            # primitive, reuse that skill instead of inventing a duplicate.
            duplicate = False
            points = tuple(self.probes(arity))
            expr = Expr.from_dict(item['expr'])
            psig = tuple(expr.run(x) for x in points)
            for skill in self.solutions:
                if skill in self.abstractions or self._skill_arity(skill) != arity:
                    continue
                sig = tuple(self._resolve_call(skill, x, {}, ()) for x in points)
                if sig == psig:
                    duplicate = True; break
            if duplicate:
                continue
            size = self._expr_size(expr)
            gain = (size - 1) * support
            ranked.append((-gain, -support, -size, key, item, expr))
        ranked.sort(key=lambda row: row[:4])

        created = []
        for _, _, neg_size, key, item, expr in ranked:
            arity = int(item['arity']); text = str(item['program'])
            digest = hashlib.blake2s(f'{arity}|{text}'.encode('utf8'), digest_size=6).hexdigest()
            name = f'abs_{digest}'
            if name in self.abstractions:
                continue
            source_skills = sorted(item['source_skills'])
            self.solutions[name] = [expr]
            self.dependencies[name] = self._expr_calls(expr)
            shared_concepts = None
            for source in source_skills:
                concepts = set(self.skill_concepts.get(source, set()))
                shared_concepts = concepts if shared_concepts is None else shared_concepts & concepts
            if shared_concepts:
                self.set_concepts(name, sorted(shared_concepts))
            meta = {'arity': arity, 'program': text, 'size': -neg_size,
                    'support': len(source_skills), 'source_skills': source_skills,
                    'kind': 'learned_utility_primitive'}
            self.abstractions[name] = meta
            created.append({'name': name, **meta})
            if len(created) >= limit:
                break
        return created

    def discover_abstractions(self, source_skill: str | None = None,
                              min_support: int | None = None, max_new: int | None = None) -> dict:
        """Incrementally invent reusable primitives from learned behaviour.

        Unlike structural common-subexpression mining, this can discover a
        primitive even when algebraically equivalent source programs were learned
        in different surface forms.  It asks which small primitive would compress
        at least two independently learned behaviours into one extra operation.
        Future/held-out target labels are never consulted.
        """
        support_needed = self.abstraction_min_support if min_support is None else max(2, int(min_support))
        limit = self.abstraction_max_new if max_new is None else max(0, int(max_new))
        if limit <= 0:
            return {'status': 'disabled', 'created': [], 'candidates': 0}
        sources = [source_skill] if source_skill is not None else [s for s in self.solutions if s not in self.abstractions]
        votes = 0
        for skill in sources:
            if skill in self.abstractions or skill not in self.solutions:
                continue
            arity = self._skill_arity(skill)
            examples = self.examples.get(skill, {})
            if arity is None or not examples or any(len(v) != 1 for v in examples.values()):
                continue
            points, recipes = self._primitive_recipe_index(arity)
            target_sig = tuple(self._resolve_call(skill, x, {}, ()) for x in points)
            if any(v is None for v in target_sig):
                continue
            for primitive, op, leaf, orientation, primitive_sig in recipes.get(target_sig, ()): 
                # Do not count a primitive that is merely the whole learned skill.
                if primitive_sig == target_sig:
                    continue
                ok = True
                for args, labels in examples.items():
                    expected = next(iter(labels))
                    pv = primitive.run(args); lv = leaf.run(args)
                    got = operate(op, pv, lv) if orientation == 0 else operate(op, lv, pv)
                    if got != expected:
                        ok = False; break
                if not ok:
                    continue
                compact, source_mapping = self._compact_expr(primitive)
                if not source_mapping:
                    continue
                primitive_arity = len(source_mapping)
                key = f'{primitive_arity}|{str(compact)}'
                evidence = self.abstraction_evidence.setdefault(key,
                    {'arity': primitive_arity, 'program': str(compact), 'expr': compact.as_dict(),
                     'source_skills': set(), 'observed_mappings': []})
                mapping_row = {'skill': skill, 'source_arity': arity, 'mapping': list(source_mapping)}
                if mapping_row not in evidence['observed_mappings'] and len(evidence['observed_mappings']) < 16:
                    evidence['observed_mappings'].append(mapping_row)
                before = len(evidence['source_skills'])
                evidence['source_skills'].add(skill)
                votes += len(evidence['source_skills']) > before
        created = self._materialize_abstractions(support_needed, limit)
        return {'status': 'created' if created else 'no_new_abstraction',
                'created': created, 'candidates': len(self.abstraction_evidence),
                'new_votes': votes, 'support_required': support_needed}

    def _library_call_variants(self, name: str, target_arity: int, points: list[tuple[int, ...]] | tuple[tuple[int, ...], ...]):
        """Return executable call forms for a reusable skill in a new task.

        Ordinary learned skills retain exact-arity calls.  Learner-invented
        primitives are parameterized: their compact arguments may be mapped to
        any distinct caller inputs, so a primitive first seen on (x0,x1) can be
        reused on (x1,x2) without copying or relearning its body.
        """
        if name not in self.solutions:
            return []
        source_arity = self._skill_arity(name)
        if source_arity is None:
            return []
        variants = []
        if name in self.abstractions:
            if source_arity > target_arity:
                return []
            seen: set[tuple] = set()
            for mapping in permutations(range(target_arity), source_arity):
                expr = Expr('pcall', name, tuple(Expr('var', i) for i in mapping))
                sig = tuple(self._run_expr(expr, x) for x in points)
                if any(v is None for v in sig) or sig in seen:
                    continue
                seen.add(sig); variants.append((expr, sig))
            return variants
        if source_arity != target_arity:
            return []
        expr = Expr('call', name)
        sig = tuple(self._resolve_call(name, x, {}, ()) for x in points)
        return [] if any(v is None for v in sig) else [(expr, sig)]

    def _auto_library(self, skill: str, inputs: list[tuple[int, ...]], outputs: tuple[int, ...], arity: int) -> list[str]:
        if self.auto_library_top_k <= 0:
            return []
        ranked = []
        constants = (-2, -1, 0, 1, 2, 3)
        concepts = self.skill_concepts.get(skill, set())
        if concepts:
            pool = set().union(*(self.concept_skills.get(c, set()) for c in concepts))
            # Include direct dependencies of semantically related skills; useful
            # when the best reusable abstraction sits one layer below a tagged skill.
            pool.update(d for name in list(pool) for d in self.dependencies.get(name, ()))
            candidates = sorted(pool)
            self._last_library_pool = {'mode':'concept_index','candidates':len(candidates),'total_skills':len(self.solutions)}
        else:
            candidates = list(self.solutions)
            self._last_library_pool = {'mode':'fallback_scan','candidates':len(candidates),'total_skills':len(self.solutions)}
        for name in candidates:
            if name == skill or name not in self.solutions:
                continue
            variants = self._library_call_variants(name, arity, inputs)
            if not variants:
                continue
            name_best = None
            for _, sig in variants:
                exact = sum(a == b for a, b in zip(sig, outputs))
                best = exact
                # Cheap goal-affinity probes: a relevant reusable skill often reaches
                # the target through one simple operation.  This is ranking only; the
                # synthesizer still verifies every training example exactly.
                for op in OPS:
                    best = max(best, sum(operate(op, a, a) == y for a, y in zip(sig, outputs)))
                    for c in constants:
                        best = max(best, sum(operate(op, a, c) == y for a, y in zip(sig, outputs)))
                        best = max(best, sum(operate(op, c, a) == y for a, y in zip(sig, outputs)))
                residual = sum(min(abs(y-a), LIMIT) for a, y in zip(sig, outputs))
                row = (-best, residual, name)
                if name_best is None or row < name_best:
                    name_best = row
            if name_best is not None:
                ranked.append(name_best)
        ranked.sort()
        return [name for _, _, name in ranked[:self.auto_library_top_k]]

    def set_concepts(self, skill: str, concepts) -> None:
        clean = {str(c).strip().casefold() for c in concepts if str(c).strip()}
        old = self.skill_concepts.get(skill, set())
        for c in old - clean:
            self.concept_skills[c].discard(skill)
        for c in clean:
            self.concept_skills[c].add(skill)
        self.skill_concepts[skill] = clean

    def add_example(self, skill: str, args: tuple[int, ...], result: int, concepts=None) -> bool:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', skill):
            raise ValueError('Nombre de habilidad inválido.')
        if concepts is not None:
            self.set_concepts(skill, concepts)
        if not 1 <= len(args) <= 4 or any(type(v) is not int or abs(v) > LIMIT for v in (*args, result)):
            raise ValueError('Se requieren de 1 a 4 enteros; magnitud máxima 10^12.')
        ex = self.examples.setdefault(skill, {})
        if ex and len(next(iter(ex))) != len(args):
            raise ValueError('Aridad inconsistente.')
        labels = ex.setdefault(tuple(args), set())
        if result in labels:
            return False
        labels.add(result)
        self._invalidate(skill)
        return True

    @staticmethod
    def probes(arity: int) -> list[tuple[int, ...]]:
        # No output labels, test cases or task names influence these probes.
        rng = Random(731)
        base = list(product((-2, -1, 0, 1, 2, 3), repeat=arity))
        if len(base) > 24:
            base = rng.sample(base, 24)
        return base

    def _fit_recurrences(self, inputs: list[tuple[int, ...]], outputs: tuple[int, ...]):
        if not self.allow_recurrence or not inputs or len(inputs[0]) != 1 or len(inputs) < 5:
            return []
        pairs=sorted((x[0],y) for x,y in zip(inputs,outputs))
        xs=[x for x,_ in pairs]
        if xs != list(range(xs[0],xs[-1]+1)):
            return []
        candidates=[]
        max_lag=min(3,len(pairs)-3)
        for lag in range(1,max_lag+1):
            derived=[]
            values=dict(pairs)
            for n,y in pairs[lag:]:
                args=(n,*[values[n-k] for k in range(1,lag+1)])
                derived.append((args,y))
            # At least three recurrence equations reduce trivial overfitting.
            if len(derived) < 3:
                continue
            local=ProgramLearner(max_size=min(self.max_size,7),
                                 max_candidates=min(self.max_candidates,120_000),
                                 max_seconds=min(self.max_seconds,3.0),
                                 goal_directed=self.goal_directed,
                                 auto_library_top_k=0,allow_recurrence=False,auto_abstraction=False)
            for args,y in derived:
                local.add_example('body',args,y)
            rep=local.fit('body',library=[])
            if rep['status'] != 'learned_hypothesis':
                continue
            bases=tuple(pairs[:lag])
            for body in local.solutions.get('body',[]):
                if isinstance(body,Expr):
                    rp=RecurrenceProgram(lag,bases,body)
                    if all(rp.run((n,))==y for n,y in pairs):
                        candidates.append(rp)
        # Shorter body / fewer base cases first. Preserve semantic alternatives.
        uniq={str(c):c for c in candidates}
        return [uniq[k] for k in sorted(uniq,key=lambda k:(len(k),k))]

    def fit(self, skill: str, library: list[str] | None = None, allowed_vars=None, *,
            examples: dict | None = None, probe_points=None, contexts: list | None = None,
            context_ops: tuple[str, ...] = CONTEXT_OPS, goal_context: bool = True,
            var_types: dict[int, str] | None = None, color_constants: tuple[int, ...] = (),
            output_type: str | None = None, abstract: bool = True) -> dict:
        """Search the smallest programs agreeing with the examples.

        G-39: ``examples``/``probe_points`` replace the stored examples and the
        generic probes (e.g. grid cells, whose unlabelled test cells are probes);
        with ``contexts`` (``GridContext`` objects) the last argument of every
        point indexes the grid that ``context_ops`` read.  The search itself is
        the same; G-39b adds the inversion of ``at`` to the goal-directed join.
        G-39c: with ``var_types`` the search is typed: ``color`` values (typed
        variables, ``color_constants``, ``at``) are only copied; arithmetic and
        indices take ``num``; a solution must have ``output_type``.
        """
        start = perf_counter()
        # Re-fitting a target invalidates only its previous implementation and dependents.
        self._invalidate(skill)
        examples = self.examples.get(skill, {}) if examples is None else examples
        report = {'status': 'no_solution', 'examples': len(examples), 'candidates': 0, 'search_complete': True,
                  'programs': [], 'notice': 'Acuerdo dentro de candidatos de menor tamaño; no certeza universal.',
                  'library_requested': None if library is None else list(library), 'library_seeded': 0,
                  'library_mode': 'auto' if library is None else 'explicit'}
        if not examples:
            return {**report, 'status': 'need_examples', 'ms': 0.0}
        if any(len(v) > 1 for v in examples.values()):
            report.update(status='contradictory_examples', ms=0.0)
            self.reports[skill] = report
            return report
        inputs = list(examples)
        outputs = tuple(next(iter(examples[x])) for x in inputs)
        arity = len(inputs[0])
        if allowed_vars is None:
            variable_ids=tuple(range(arity))
        else:
            try:
                variable_ids=tuple(sorted(set(int(i) for i in allowed_vars)))
            except Exception as exc:
                raise ValueError('Roles permitidos inválidos.') from exc
            if not variable_ids or any(i < 0 or i >= arity for i in variable_ids):
                raise ValueError('Roles permitidos fuera de la aridad del programa.')
        report['allowed_vars']=list(variable_ids)
        probes = [x for x in (self.probes(arity) if probe_points is None else probe_points) if x not in examples]
        points = inputs + probes
        point_grids = None if contexts is None else [contexts[x[-1]] for x in points]
        selected_library = self._auto_library(skill, inputs, outputs, arity) if library is None else list(library)
        report['library_selected'] = selected_library
        if library is None:
            report['library_retrieval'] = getattr(self, '_last_library_pool', {'mode':'fallback_scan'})
        seen: set[tuple] = set()
        levels: dict[int, list[tuple[Expr, tuple]]] = {}
        solutions: list[Expr] = []
        solution_levels: list[int] = []
        stored_cells = 0
        attempts, truncated, reason = 0, False, None
        constraint_checks = 0
        goal_hits = False
        typed = var_types is not None

        def kind(expr: Expr) -> str:
            if not typed:
                return 'num'
            if expr.op == 'var':
                return var_types.get(expr.value, 'num')
            return 'color' if expr.op in ('color', 'at') else 'num'

        def consider(expr: Expr, sig: tuple, level: int) -> None:
            nonlocal stored_cells
            key = (kind(expr), sig) if typed else sig
            if any(v is None for v in sig[:len(inputs)]) or key in seen:
                return
            seen.add(key)
            levels.setdefault(level, []).append((expr, sig))
            if sig[:len(inputs)] == outputs and (output_type is None or kind(expr) == output_type):
                solutions.append(expr)
                solution_levels.append(level)
            stored_cells += len(sig)
            if stored_cells > self.max_signature_cells:
                raise RuntimeError('Presupuesto de memoria de la búsqueda agotado.')

        for i in variable_ids:
            e = Expr('var', i)
            consider(e, tuple(x[i] for x in points), 1)
        for c in (-1, 0, 1):
            e = Expr('const', c)
            consider(e, tuple(c for _ in points), 1)
        for c in color_constants:
            consider(Expr('color', c), tuple(c for _ in points), 1)

        # Learned programs can be reused as abstract library primitives.  They
        # are EXECUTED as their learned expression, but count as one search unit
        # for synthesis.  This changes search representation, not the result.
        # Only same-arity skills are eligible; the current target is excluded.
        seeded = 0
        for libskill in selected_library:
            if libskill == skill or libskill not in self.solutions:
                continue
            for e, sig in self._library_call_variants(libskill, arity, points):
                if allowed_vars is not None and not self._expr_vars(e).issubset(set(variable_ids)):
                    continue
                before = len(levels.get(1, []))
                consider(e, sig, 1)
                if len(levels.get(1, [])) > before:
                    seeded += 1
        report['library_seeded'] = seeded
        winning_size = 1 if solutions else None

        def check_budget() -> None:
            if attempts > self.max_candidates:
                raise RuntimeError('Presupuesto de candidatos agotado.')
            if constraint_checks > self.max_candidates * 20:
                raise RuntimeError('Presupuesto de restricciones agotado.')
            if perf_counter() - start > self.max_seconds:
                raise RuntimeError('Tiempo de búsqueda agotado.')

        def goal_join(size: int) -> None:
            """Meet in the middle at the desired root, preserving every retained
            minimum-size solution, not just the first one. Algebraic inverses and
            scalar indexes reject incompatible operands BEFORE vector execution.
            This is generic for all skills and all seven operators.
            """
            nonlocal attempts, constraint_checks
            n = len(inputs)
            for left_size in range(1, size - 1, 2):
                right_size = size - left_size - 1
                lefts = levels.get(left_size, [])
                rights = levels.get(right_size, [])
                if not lefts or not rights:
                    continue
                by_vector: dict[tuple, list[int]] = {}
                by_coordinate: dict[int, dict[int, set[int]]] = {}
                for j, (_, signature) in enumerate(rights):
                    by_vector.setdefault(signature[:n], []).append(j)

                def index_at(coordinate: int) -> dict[int, set[int]]:
                    if coordinate not in by_coordinate:
                        index: dict[int, set[int]] = {}
                        for j, (_, signature) in enumerate(rights):
                            index.setdefault(signature[coordinate], set()).add(j)
                        by_coordinate[coordinate] = index
                    return by_coordinate[coordinate]

                for left, ls in lefts:
                    lv = ls[:n]
                    for op in OPS:
                        if op in COMMUTATIVE and left_size > right_size:
                            continue
                        check_budget()
                        ids: list[int] | set[int]
                        if op in ('add', 'sub'):
                            required = tuple(y - x if op == 'add' else x - y for x, y in zip(lv, outputs))
                            constraint_checks += n
                            ids = by_vector.get(required, [])
                        elif op == 'mul':
                            required = []
                            invalid = False
                            for x, y in zip(lv, outputs):
                                constraint_checks += 1
                                if x == 0:
                                    if y != 0:
                                        invalid = True; break
                                    required.append(None)
                                elif y % x:
                                    invalid = True; break
                                else:
                                    required.append(y // x)
                            if invalid:
                                continue
                            if None not in required:
                                ids = by_vector.get(tuple(required), [])
                            else:
                                constraints = [(i, v) for i, v in enumerate(required) if v is not None]
                                if not constraints:
                                    ids = range(len(rights))
                                else:
                                    i, v = min(constraints, key=lambda iv: len(index_at(iv[0]).get(iv[1], ())))
                                    ids = index_at(i).get(v, set())
                        elif op in ('min', 'max'):
                            impossible = any((y > x if op == 'min' else y < x) for x, y in zip(lv, outputs))
                            constraint_checks += n
                            if impossible:
                                continue
                            fixed = [(i, y) for i, (x, y) in enumerate(zip(lv, outputs)) if x != y]
                            if fixed:
                                i, value = min(fixed, key=lambda iv: len(index_at(iv[0]).get(iv[1], ())))
                                ids = index_at(i).get(value, set())
                            else:
                                ids = range(len(rights))
                        else:
                            # floor division and remainder: filter with up to two
                            # scalar constraints before checking the full vector.
                            ids = None
                            coords = sorted(range(n), key=lambda i: -abs(outputs[i]))[:2]
                            for coordinate in coords:
                                allowed: set[int] = set()
                                for value, members in index_at(coordinate).items():
                                    constraint_checks += 1
                                    if operate(op, lv[coordinate], value) == outputs[coordinate]:
                                        allowed.update(members)
                                ids = allowed if ids is None else ids & allowed
                                if not ids:
                                    break
                            ids = ids or set()
                        for j in sorted(ids):
                            right, rs = rights[j]
                            if op in COMMUTATIVE and left_size == right_size and str(left) > str(right):
                                continue
                            attempts += 1
                            check_budget()
                            # Important: validate ALL examples, not just indexes.
                            training_sig = tuple(operate(op, a, b) for a, b in zip(lv, rs[:n]))
                            if training_sig != outputs:
                                continue
                            signature = training_sig + tuple(operate(op, a, b) for a, b in zip(ls[n:], rs[n:]))
                            consider(Expr(op, children=(left, right)), signature, size)
        rowmaps = None
        goal_splits_done: set[tuple[int, int]] = set()

        def goal_at(size: int, built: int) -> None:
            """G-39b: ``at(i, j)`` as the root, by inversion.  A row expression
            survives alone only if every target colour occurs in that input row;
            then only column expressions landing on such cells are checked.
            Only splits whose children are already complete levels (< ``built``)
            are tried, each once; every solution found is kept."""
            nonlocal attempts, rowmaps, constraint_checks
            n = len(inputs)
            if rowmaps is None:
                rowmaps = [{i: frozenset(j for j, v in enumerate(row) if v == y)
                            for i, row in enumerate(point_grids[p].grid) if y in row}
                           for p, y in zip(range(n), outputs)]
            for left_size in range(1, size - 1, 2):
                right_size = size - 1 - left_size
                if left_size >= built or right_size >= built or (size, left_size) in goal_splits_done:
                    continue
                goal_splits_done.add((size, left_size))
                rights = levels.get(right_size, [])
                if not rights:
                    continue
                by_first: dict[int, list] = {}
                for right, rs in rights:
                    if kind(right) == 'num':
                        by_first.setdefault(rs[0], []).append((right, rs))
                for left, ls in levels.get(left_size, []):
                    if kind(left) != 'num':
                        continue
                    check_budget()
                    allowed = []
                    for rowmap, i in zip(rowmaps, ls):
                        constraint_checks += 1
                        cols = rowmap.get(i)
                        if not cols:
                            break
                        allowed.append(cols)
                    else:
                        for j0 in allowed[0]:
                            for right, rs in by_first.get(j0, ()):
                                attempts += 1
                                if all(j in cols for j, cols in zip(rs, allowed)):
                                    sig = tuple(context_op('at', g, a, b) for g, a, b in zip(point_grids, ls, rs))
                                    consider(Expr('at', children=(left, right)), sig, size)

        try:
            for size in range(3, self.max_size + 1, 2):
                if solutions and min(solution_levels) < size:
                    break
                if point_grids is not None and goal_context and 'at' in context_ops:
                    # G-39b: pruned inversions for every size reachable with the
                    # complete levels, before the expensive enumeration of this
                    # size; a larger solution found early is replaced below by
                    # any smaller one the enumeration still finds.
                    for target in range(size, self.max_size + 1, 2):
                        goal_at(target, size)
                    if solutions and min(solution_levels) == size:
                        goal_hits = True
                        break
                # An arithmetic root cannot yield a colour in a typed search.
                if self.goal_directed and not (typed and output_type == 'color'):
                    goal_join(size)
                    if solutions and min(solution_levels) == size:
                        goal_hits = True
                        break
                for left_size in range(1, size - 1, 2):
                    right_size = size - 1 - left_size
                    for left, ls in levels.get(left_size, []):
                        if typed and kind(left) != 'num':
                            continue
                        for right, rs in levels.get(right_size, []):
                            if typed and kind(right) != 'num':
                                continue
                            for op in OPS:
                                if op in COMMUTATIVE and (left_size > right_size or (left_size == right_size and str(left) > str(right))):
                                    continue
                                attempts += 1
                                if attempts > self.max_candidates:
                                    raise RuntimeError('Presupuesto de candidatos agotado.')
                                if attempts % 256 == 0 and perf_counter() - start > self.max_seconds:
                                    raise RuntimeError('Tiempo de búsqueda agotado.')
                                sig = tuple(operate(op, a, b) for a, b in zip(ls, rs))
                                consider(Expr(op, children=(left, right)), sig, size)
                            if point_grids is not None:
                                for op in context_ops:
                                    attempts += 1
                                    if attempts > self.max_candidates:
                                        raise RuntimeError('Presupuesto de candidatos agotado.')
                                    sig = tuple(context_op(op, g, a, b) for g, a, b in zip(point_grids, ls, rs))
                                    consider(Expr(op, children=(left, right)), sig, size)
        except RuntimeError as exc:
            truncated, reason = True, str(exc)
        if solutions and solution_levels:
            # Keep every retained solution of the smallest size found.
            smallest = min(solution_levels)
            solutions = [e for e, level in zip(solutions, solution_levels) if level == smallest]
            winning_size = smallest
        recurrence_solutions = []
        if not solutions and not truncated:
            recurrence_solutions = self._fit_recurrences(inputs, outputs)
            if recurrence_solutions:
                solutions = recurrence_solutions
                winning_size = 'recurrence'
                report['recurrence_discovered'] = True
        if solutions:
            # Do not discard distinct retained solutions in order to fake confidence.
            self.solutions[skill] = solutions
            deps = set().union(*(self._expr_calls(e) for e in solutions)) if solutions else set()
            self.dependencies[skill] = deps
            report['dependencies'] = sorted(deps)
            report.update(status='learned_hypothesis', programs=[str(x) for x in solutions], size=winning_size)
            if abstract and self.auto_abstraction and skill not in self.abstractions:
                report['abstraction_learning'] = self.discover_abstractions(source_skill=skill)
        report.update(candidates=attempts, constraint_checks=constraint_checks, goal_directed=self.goal_directed,
                      goal_join_solved=goal_hits, search_complete=not truncated, reason=reason,
                      semantic_states=len(seen), ms=(perf_counter() - start) * 1000)
        self.reports[skill] = report
        return report

    def predict(self, skill: str, args: tuple[int, ...]) -> dict:
        examples = self.examples.get(skill, {})
        if not examples:
            return {'status': 'unknown', 'value': None}
        if len(args) != len(next(iter(examples))) or any(type(x) is not int or abs(x) > LIMIT for x in args):
            raise ValueError('Entradas incompatibles con la habilidad.')
        if any(len(v) > 1 for v in examples.values()):
            return {'status': 'contradictory_examples', 'value': None}
        programs = self.solutions.get(skill, [])
        if not programs:
            return {'status': 'unknown', 'value': None}
        values = {self._run_expr(p, tuple(args)) for p in programs}
        common = {'programs': [str(p) for p in programs], 'examples': len(examples),
                  'search_complete': self.reports.get(skill, {}).get('search_complete', False)}
        if len(values) != 1:
            return {**common, 'status': 'ambiguous', 'value': None,
                    'alternatives': sorted(v for v in values if v is not None)}
        value = next(iter(values))
        return {**common, 'status': 'hypothesis' if value is not None else 'undefined', 'value': value}

    def request_example(self, skill: str) -> tuple[int, ...] | None:
        ex = self.examples.get(skill, {})
        programs = self.solutions.get(skill, [])
        if not ex or len(programs) < 2:
            return None
        best, diversity = None, 1
        for args in self.probes(len(next(iter(ex)))):
            if args in ex:
                continue
            values = {self._run_expr(p, args) for p in programs}
            if len(values) > diversity:
                best, diversity = args, len(values)
        return best

    @staticmethod
    def _grid(value) -> tuple[tuple[int, ...], ...]:
        grid = tuple(tuple(row) for row in value)
        if (not grid or not grid[0] or len(grid) > 30 or any(len(row) != len(grid[0]) for row in grid)
                or any(type(v) is not int or not 0 <= v <= 9 for row in grid for v in row)):
            raise ValueError('Una cuadrícula es rectangular, de hasta 30×30, con colores 0–9.')
        return grid

    def add_grid_example(self, skill: str, source, target) -> bool:
        """G-39: one demonstration of a grid-to-grid transformation."""
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', skill):
            raise ValueError('Nombre de habilidad inválido.')
        pair = (self._grid(source), self._grid(target))
        pairs = self.grid_examples.setdefault(skill, [])
        if pair in pairs:
            return False
        pairs.append(pair)
        for part in ('alto', 'ancho', 'celda'):
            self._invalidate(f'{skill}__{part}')
        return True

    def fit_grid(self, skill: str, test_inputs=(), *, use_context: bool = True, use_test_probes: bool = True,
                 use_aggregation: bool = True, use_goal: bool = True, use_types: bool = True) -> dict:
        """G-39/G-39b: learn output height, width and cell colour as integer programs.

        Height and width are skills of (height, width, whole-grid aggregates) of
        the input; the cell colour is a skill of (row, col, height, width,
        aggregates) read against the input grid with the context operations.
        Test inputs are given information, not answers: their sizes and cells
        enter only as unlabelled probes, so programs that agree on the
        demonstrations but differ on the test stay distinct (ambiguity).
        The keyword switches exist for ablations; arguments always keep the
        full layout, the switches only restrict what the search may use.
        """
        pairs = self.grid_examples.get(skill, [])
        if not pairs:
            return {'status': 'need_examples'}
        tests = [self._grid(g) for g in test_inputs]
        report: dict = {'pairs': len(pairs), 'tests': len(tests)}
        contexts = [GridContext(a) for a, _ in pairs] + [GridContext(g) for g in tests]
        width = 2 + len(GRID_FEATURES)
        # G-39c: colour-valued aggregates are symbols; sizes may not use them.
        colour_features = {i for i, name in enumerate(GRID_FEATURES)
                           if name in ('moda', 'mas_frecuente', 'menos_frecuente')}
        shape_vars = tuple(i for i in range(width) if not (use_types and i - 2 in colour_features)) \
            if use_aggregation else (0, 1)
        for k, part in enumerate(('alto', 'ancho')):
            ex = {}
            for (a, b), ctx in zip(pairs, contexts):
                ex.setdefault((len(a), len(a[0]), *ctx.features), set()).add(len(b) if k == 0 else len(b[0]))
            probes = [(len(g), len(g[0]), *ctx.features) for g, ctx in zip(tests, contexts[len(pairs):])] \
                if use_test_probes else []
            rep = self.fit(f'{skill}__{part}', library=[], allowed_vars=shape_vars, examples=ex,
                           probe_points=probes, abstract=False)
            report[part] = rep
            if rep['status'] != 'learned_hypothesis':
                return {**report, 'status': rep['status'], 'stage': part}
        shapes = []
        for g in tests:
            shape = self._grid_shape(skill, g)
            if shape['status'] != 'hypothesis':
                return {**report, 'status': shape['status'], 'stage': 'tamaño de prueba'}
            shapes.append(shape['value'])
        ex, probes = {}, []
        for k, ((a, b), ctx) in enumerate(zip(pairs, contexts)):
            for r, row in enumerate(b):
                for c, v in enumerate(row):
                    ex[(r, c, len(a), len(a[0]), *ctx.features, k)] = {v}
        for t, (g, (h, w)) in enumerate(zip(tests, shapes) if use_test_probes else ()):
            ctx = contexts[len(pairs) + t]
            probes.extend((r, c, len(g), len(g[0]), *ctx.features, len(pairs) + t) for r in range(h) for c in range(w))
        cell_vars = tuple(range(2 + width)) if use_aggregation else (0, 1, 2, 3)
        ops = CONTEXT_OPS if use_aggregation else ('at',)
        typing = {}
        if use_types:
            typing['var_types'] = {4 + i: 'color' for i in colour_features}
            # Colour constants come from the demonstrations, in order of appearance.
            seen_colours = dict.fromkeys(v for _, b in pairs for row in b for v in row)
            typing['color_constants'] = tuple(seen_colours)
            typing['output_type'] = 'color'
        rep = self.fit(f'{skill}__celda', library=[], allowed_vars=cell_vars, examples=ex, probe_points=probes,
                       contexts=contexts if use_context else None, context_ops=ops, goal_context=use_goal,
                       abstract=False, **typing)
        report['celda'] = rep
        return {**report, 'status': rep['status'], 'stage': 'celda'}

    def _grid_shape(self, skill: str, grid) -> dict:
        args = (len(grid), len(grid[0]), *GridContext(grid).features)
        shape = []
        for part in ('alto', 'ancho'):
            programs = self.solutions.get(f'{skill}__{part}', [])
            if not programs:
                return {'status': 'unknown', 'value': None}
            values = {self._run_expr(p, args) for p in programs}
            if len(values) != 1:
                return {'status': 'ambiguous', 'value': None}
            value = next(iter(values))
            if value is None or not 1 <= value <= 30:
                return {'status': 'undefined', 'value': None}
            shape.append(value)
        return {'status': 'hypothesis', 'value': tuple(shape)}

    def predict_grid(self, skill: str, source) -> dict:
        """Answer only when every retained minimal program agrees on every cell."""
        grid = self._grid(source)
        shape = self._grid_shape(skill, grid)
        if shape['status'] != 'hypothesis':
            return {'status': shape['status'], 'grid': None}
        programs = self.solutions.get(f'{skill}__celda', [])
        if not programs:
            return {'status': 'unknown', 'grid': None}
        ctx = GridContext(grid)
        h, w = shape['value']
        out = []
        for r in range(h):
            row = []
            for c in range(w):
                args = (r, c, len(grid), len(grid[0]), *ctx.features, 0)
                values = {p.run(args, None, {}, (), ctx) for p in programs}
                if len(values) != 1:
                    return {'status': 'ambiguous', 'grid': None, 'programs': [str(p) for p in programs]}
                value = next(iter(values))
                if value is None or not 0 <= value <= 9:
                    return {'status': 'undefined', 'grid': None}
                row.append(value)
            out.append(row)
        return {'status': 'hypothesis', 'grid': out, 'programs': [str(p) for p in programs]}

    def as_dict(self) -> dict:
        return {'config': {'max_size': self.max_size, 'max_candidates': self.max_candidates, 'max_seconds': self.max_seconds,
                           'goal_directed': self.goal_directed, 'auto_library_top_k': self.auto_library_top_k,
                           'allow_recurrence': self.allow_recurrence, 'auto_abstraction': self.auto_abstraction,
                           'abstraction_min_support': self.abstraction_min_support,
                           'abstraction_max_new': self.abstraction_max_new,
                           'max_signature_cells': self.max_signature_cells}, 'examples': {s: [{'args': list(x), 'labels': sorted(y)} for x, y in ex.items()] for s, ex in self.examples.items()},
                'solutions': {s: [e.as_dict() for e in es] for s, es in self.solutions.items()}, 'reports': self.reports,
                'dependencies': {s: sorted(v) for s, v in self.dependencies.items()},
                'skill_concepts': {s: sorted(v) for s, v in self.skill_concepts.items()},
                'abstractions': self.abstractions,
                'grid_examples': {s: [[list(map(list, a)), list(map(list, b))] for a, b in ps]
                                  for s, ps in self.grid_examples.items()},
                'abstraction_evidence': {k: {**v, 'source_skills': sorted(v.get('source_skills', ())) }
                                         for k, v in self.abstraction_evidence.items()}}

    @classmethod
    def from_dict(cls, data: dict) -> ProgramLearner:
        pl = cls(**data.get('config', {}))
        for skill, examples in data.get('examples', {}).items():
            for ex in examples:
                for y in ex['labels']:
                    pl.add_example(skill, tuple(ex['args']), y)
        for skill, programs in data.get('solutions', {}).items():
            pl.solutions[skill] = [RecurrenceProgram.from_dict(p) if p.get('op') == 'recurrence_expr' else (Recurrence.from_dict(p) if p.get('op') == 'recurrence' else Expr.from_dict(p)) for p in programs]
        pl.reports = data.get('reports', {})
        pl.abstractions = {s: dict(v) for s, v in data.get('abstractions', {}).items()}
        pl.abstraction_evidence = {k: {**v, 'source_skills': set(v.get('source_skills', ())) }
                                   for k, v in data.get('abstraction_evidence', {}).items()}
        pl.dependencies = {s: set(v) for s, v in data.get('dependencies', {}).items()}
        if not pl.dependencies:
            pl.dependencies = {s: set().union(*(pl._expr_calls(e) for e in es)) if es else set()
                               for s, es in pl.solutions.items()}
        for skill, concepts in data.get('skill_concepts', {}).items():
            pl.set_concepts(skill, concepts)
        for skill, ps in data.get('grid_examples', {}).items():
            pl.grid_examples[skill] = [(pl._grid(a), pl._grid(b)) for a, b in ps]
        return pl

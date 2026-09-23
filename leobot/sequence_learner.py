"""Bounded, data-derived programs over token sequences.

This DSL has no vocabulary, execution hooks or task identifiers.  Input context
and output constants come only from observed pairs.  Consolidation happens at
teaching time; prediction evaluates persisted data without searching hypotheses.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json


def _tokens(value):
    if isinstance(value, str):
        tokens = tuple(value.split())
    elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        tokens = tuple(value)
    else:
        raise ValueError('La secuencia debe contener símbolos de texto.')
    if not 1 <= len(tokens) <= 128 or any(not token or len(token) > 80 for token in tokens):
        raise ValueError('Secuencia fuera del presupuesto.')
    return tokens


def _starts(value, prefix):
    return value[:len(prefix)] == prefix


def _ends(value, suffix):
    return not suffix or value[-len(suffix):] == suffix


def _unary_candidates(base, target):
    """Infer typed list programs, including constants from the observed output."""
    found = set()
    if target == base:
        found.add(('identity',))
    for count in (2, 3, 4):
        if target == base * count:
            found.add(('repeat', count))
    width = len(base)
    for start in range(len(target) - width + 1):
        if target[start:start + width] != base:
            continue
        prefix, suffix = target[:start], target[start + width:]
        if prefix and not suffix and len(prefix) <= 4:
            found.add(('prefix', prefix))
        if suffix and not prefix and len(suffix) <= 4:
            found.add(('suffix', suffix))
    for count in (2, 3, 4):
        if len(target) % count:
            continue
        unit = target[:len(target) // count]
        if unit * count != target or len(unit) <= width:
            continue
        if unit[-width:] == base and len(unit) - width <= 4:
            found.add(('repeat_prefix', unit[:-width], count))
        if unit[:width] == base and len(unit) - width <= 4:
            found.add(('repeat_suffix', unit[width:], count))
    return found


def _execute_unary(program, value):
    kind = program[0]
    if kind == 'identity':
        return value
    if kind == 'repeat':
        return value * program[1]
    if kind == 'prefix':
        return program[1] + value
    if kind == 'suffix':
        return value + program[1]
    if kind == 'repeat_prefix':
        return (program[1] + value) * program[2]
    if kind == 'repeat_suffix':
        return (value + program[1]) * program[2]
    return ()


class SequenceLearner:
    def __init__(self, enabled=True, max_examples=512, max_candidates=20_000,
                 enable_composition=True):
        self.enabled = bool(enabled)
        self.enable_composition = bool(enable_composition)
        self.max_examples = max(1, min(512, int(max_examples)))
        self.max_candidates = max(1, min(20_000, int(max_candidates)))
        self.examples: dict[tuple[str, ...], set[tuple[str, ...]]] = {}
        self.rules: list[dict] = []
        self.candidates_examined = 0
        self.dirty = False

    def observe(self, source, target):
        left, right = _tokens(source), _tokens(target)
        if len(self.examples) >= self.max_examples and left not in self.examples:
            return {'status': 'sequence_budget', 'examples': len(self.examples)}
        outputs = self.examples.setdefault(left, set())
        changed = right not in outputs
        outputs.add(right)
        if changed:
            self.rules = []
            self.dirty = True
        return {'status': 'sequence_conflict' if len(outputs) > 1 else
                'sequence_observed' if changed else 'sequence_duplicate',
                'examples': len(self.examples), 'alternatives': len(outputs)}

    def consolidate(self):
        """Intersect per-context version spaces across independent examples."""
        if not self.enabled or not self.enable_composition:
            self.rules = []; self.dirty = False
            return {'status': 'sequence_disabled', 'rules': 0, 'candidates': 0}
        clean = {source: next(iter(outputs)) for source, outputs in self.examples.items()
                 if len(outputs) == 1}
        unary = defaultdict(lambda: defaultdict(set))
        binary = defaultdict(lambda: defaultdict(set))
        blocked = set()
        examined = 0
        for source in sorted(self.examples, key=lambda row: (len(row), row)):
            variants = self.examples[source]
            n = len(source)
            for start in range(n):
                for stop in range(start + 1, n + 1):
                    base = source[start:stop]
                    if base == source or base not in clean:
                        continue
                    prefix, suffix = source[:start], source[stop:]
                    if not (prefix or suffix) or len(prefix) + len(suffix) > 3:
                        continue
                    key = ('unary', prefix, suffix)
                    if len(variants) > 1:
                        blocked.add(key); continue
                    for program in _unary_candidates(clean[base], clean[source]):
                        unary[key][program].add((source, base))
                        examined += 1
                        if examined > self.max_candidates:
                            self.rules = []; self.dirty = False
                            self.candidates_examined = examined
                            return {'status': 'sequence_search_budget', 'rules': 0,
                                    'candidates': examined}
            for first_end in range(1, n - 1):
                left = source[:first_end]
                if left not in clean:
                    continue
                for second_start in range(first_end + 1, min(n, first_end + 4)):
                    right = source[second_start:]
                    if right not in clean:
                        continue
                    marker = source[first_end:second_start]
                    key = ('binary', marker)
                    if len(variants) > 1:
                        blocked.add(key); continue
                    for order, result in (('forward', clean[left] + clean[right]),
                                          ('reverse', clean[right] + clean[left])):
                        if result == clean[source]:
                            binary[key][(order,)].add((source, left, right))
                            examined += 1
                            if examined > self.max_candidates:
                                self.rules = []; self.dirty = False
                                self.candidates_examined = examined
                                return {'status': 'sequence_search_budget', 'rules': 0,
                                        'candidates': examined}
        promoted = []
        for evidence in (unary, binary):
            for key, programs in sorted(evidence.items()):
                if key in blocked:
                    continue
                sources = {row[0] for supports in programs.values() for row in supports}
                viable = [(program, supports) for program, supports in programs.items()
                          if {row[0] for row in supports} == sources and
                          len({row[0] for row in supports}) >= 3 and
                          len({row[1] for row in supports}) >= 3]
                if len(viable) != 1:
                    continue
                program, supports = viable[0]
                row = {'kind': key[0],
                       'context': [list(part) if isinstance(part, tuple) else part
                                   for part in key[1:]],
                       'program': [list(part) if isinstance(part, tuple) else part
                                   for part in program],
                       'support': len(sources),
                       'dependencies': [' '.join(part[0]) for part in sorted(supports)]}
                row['id'] = hashlib.blake2b(json.dumps(
                    (row['kind'], row['context'], row['program']),
                    ensure_ascii=False, separators=(',', ':')).encode(), digest_size=8).hexdigest()
                promoted.append(row)
        self.rules = promoted
        self.candidates_examined = examined
        self.dirty = False
        return {'status': 'sequence_consolidated', 'rules': len(promoted),
                'candidates': examined, 'examples': len(self.examples)}

    def predict(self, source, max_depth=8, max_states=128):
        tokens = _tokens(source)
        if not self.enabled or self.dirty:
            return {'status': 'sequence_pending'}
        states = 0
        memo = {}

        def solve(current, depth):
            nonlocal states
            if current in memo:
                return memo[current]
            states += 1
            if states > max_states or depth > max_depth:
                return set()
            outputs = self.examples.get(current)
            if outputs:
                if len(outputs) == 1:
                    only = next(iter(outputs))
                    memo[current] = {(only, 'memory', (), ())}
                else:
                    memo[current] = set()
                return memo[current]
            predictions = set()
            for rule in self.rules:
                if rule['kind'] == 'unary':
                    prefix, suffix = map(tuple, rule['context'])
                    if (not _starts(current, prefix) or not _ends(current, suffix)
                            or len(current) <= len(prefix) + len(suffix)):
                        continue
                    end = len(current) - len(suffix) if suffix else len(current)
                    base = current[len(prefix):end]
                    if base == current:
                        continue
                    for value, _, dependencies, used_rules in solve(base, depth + 1):
                        program = tuple(tuple(part) if isinstance(part, list) else part
                                        for part in rule['program'])
                        result = _execute_unary(program, value)
                        if 1 <= len(result) <= 256:
                            predictions.add((result, 'rule', tuple(sorted(
                                set(dependencies) | set(rule['dependencies']))),
                                tuple(sorted(set(used_rules) | {rule['id']}))))
                else:
                    marker = tuple(rule['context'][0])
                    for start in range(1, len(current) - len(marker)):
                        if current[start:start + len(marker)] != marker:
                            continue
                        left = solve(current[:start], depth + 1)
                        right = solve(current[start + len(marker):], depth + 1)
                        for a, _, deps_a, rules_a in left:
                            for b, _, deps_b, rules_b in right:
                                result = a + b if rule['program'][0] == 'forward' else b + a
                                if 1 <= len(result) <= 256:
                                    predictions.add((result, 'rule', tuple(sorted(
                                        set(deps_a) | set(deps_b) | set(rule['dependencies']))),
                                        tuple(sorted(set(rules_a) | set(rules_b) | {rule['id']}))))
            memo[current] = predictions
            return predictions

        rows = solve(tokens, 0)
        alternatives = {row[0] for row in rows}
        if len(alternatives) != 1:
            return {'status': 'sequence_ambiguous' if alternatives else 'sequence_unknown',
                    'alternatives': len(alternatives), 'states': states}
        answer = next(iter(alternatives))
        kinds = {row[1] for row in rows if row[0] == answer}
        evidence = sorted({dependency for row in rows if row[0] == answer
                           for dependency in row[2]})
        rules_used = sorted({identifier for row in rows if row[0] == answer
                             for identifier in row[3]})
        return {'status': 'sequence_memory' if kinds == {'memory'} else 'sequence_program',
                'output': list(answer), 'dependencies': evidence,
                'rules_used': rules_used, 'states': states}

    def as_dict(self):
        return {'enabled': self.enabled, 'enable_composition': self.enable_composition,
                'max_examples': self.max_examples,
                'max_candidates': self.max_candidates,
                'examples': [{'input': list(source), 'outputs': [list(value) for value in sorted(outputs)]}
                             for source, outputs in sorted(self.examples.items())],
                'rules': self.rules, 'candidates_examined': self.candidates_examined,
                'dirty': self.dirty}

    @classmethod
    def from_dict(cls, data):
        obj = cls(data.get('enabled', True), data.get('max_examples', 512),
                  data.get('max_candidates', 20_000),
                  data.get('enable_composition', True))
        for row in data.get('examples', []):
            obj.examples[_tokens(row['input'])] = {_tokens(value) for value in row['outputs']}
        # Recompute from examples: serialized rules cannot smuggle executable policy.
        if not data.get('dirty') and obj.enabled:
            obj.consolidate()
        else:
            obj.dirty = bool(data.get('dirty'))
        return obj

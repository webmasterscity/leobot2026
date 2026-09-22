"""Supervised slot-construction learner, NOT unrestricted Spanish understanding.

Given an utterance paired with a semantic frame, concrete arguments are aligned
to text spans. The surrounding words become a reusable construction. No neural
parser or model is called. Rephrasing must be taught; ambiguity is reported.
"""
from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
import re
import unicodedata
import json
from collections import defaultdict, deque
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    text = ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))
    return ' '.join(text.strip().strip('¿?¡!.').split())


def put_path(frame: dict, path: tuple, value: str | int) -> None:
    node = frame
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value


@dataclass
class Construction:
    pattern: str
    frame: dict
    slots: list[dict]
    surface: str

    def parse(self, text: str) -> dict | None:
        match = re.fullmatch(self.pattern, normalize(text))
        if match is None:
            return None
        result = deepcopy(self.frame)
        for slot in self.slots:
            value = match[slot['name']]
            put_path(result, tuple(slot['path']), int(value) if slot['type'] == 'int' else value.strip())
        return result

    def render(self, frame: dict) -> str | None:
        expected, actual = deepcopy(self.frame), deepcopy(frame)
        if expected.get('act') != actual.get('act') or expected.get('pred') != actual.get('pred'):
            return None
        values = {}
        try:
            for slot in self.slots:
                node = frame
                for part in slot['path']:
                    node = node[part]
                values[slot['name']] = str(node)
                put_path(expected, tuple(slot['path']), '__SLOT__')
                put_path(actual, tuple(slot['path']), '__SLOT__')
        except (KeyError, IndexError, TypeError):
            return None
        if expected != actual:
            return None
        out = self.surface
        for name, value in values.items():
            out = out.replace('{' + name + '}', value)
        return out

    def as_dict(self) -> dict:
        return {'pattern': self.pattern, 'frame': self.frame, 'slots': self.slots, 'surface': self.surface}


class Language:
    def __init__(self, max_rewrite_states: int = 64, max_rewrite_steps: int = 3) -> None:
        self.constructions: list[Construction] = []
        self.examples: list[dict] = []
        self.max_rewrite_states = max_rewrite_states
        self.max_rewrite_steps = max_rewrite_steps
        self.rewrites: dict[str, set[tuple[tuple[str, ...], tuple[str, ...]]]] = defaultdict(set)
        # Rewrites are discovered only from constructions with the same semantic
        # schema, then may be reused by other constructions of the same predicate.
        # This lets lexical knowledge transfer across assertion/query acts without
        # inferring synonymy from unrelated sentence pairs.
        self.predicate_rewrites: dict[str, set[tuple[tuple[str, ...], tuple[str, ...]]]] = defaultdict(set)

    @staticmethod
    def _schema(c: Construction) -> str:
        return json.dumps(c.frame, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

    @staticmethod
    def _surface_tokens(c: Construction) -> tuple[str, ...]:
        text = c.surface
        for slot in c.slots:
            text = text.replace('{' + slot['name'] + '}', '<' + slot['name'] + '>')
        return tuple(text.split())

    def _learn_rewrites(self, new: Construction) -> None:
        schema = self._schema(new)
        a = self._surface_tokens(new)
        for old in self.constructions:
            if old is new or self._schema(old) != schema:
                continue
            b = self._surface_tokens(old)
            matcher = SequenceMatcher(a=a, b=b, autojunk=False)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag != 'replace':
                    continue
                left, right = a[i1:i2], b[j1:j2]
                if not left or not right or any(x.startswith('<s') for x in (*left, *right)):
                    continue
                # Keep rewrites local: very long replacements are effectively
                # memorized sentences, not useful compositional knowledge.
                if len(left) <= 4 and len(right) <= 4:
                    pair = (left, right) if left <= right else (right, left)
                    self.rewrites[schema].add(pair)
                    pred=new.frame.get('pred')
                    if isinstance(pred,str):
                        self.predicate_rewrites[pred].add(pair)

    @staticmethod
    def _replace_phrase(tokens: tuple[str, ...], old: tuple[str, ...], new: tuple[str, ...]):
        n = len(old)
        for i in range(len(tokens) - n + 1):
            if tokens[i:i+n] == old:
                yield tokens[:i] + new + tokens[i+n:]

    def _rewrite_variants(self, text: str, schema: str, pred: str | None = None):
        start = tuple(normalize(text).split())
        yield ' '.join(start)
        rules=set(self.rewrites.get(schema, ()))
        if pred:
            rules.update(self.predicate_rewrites.get(pred, ()))
        if not rules:
            return
        queue = deque([(start, 0)])
        seen = {start}
        while queue and len(seen) < self.max_rewrite_states:
            tokens, depth = queue.popleft()
            if depth >= self.max_rewrite_steps:
                continue
            for left, right in rules:
                for old, new in ((left, right), (right, left)):
                    for nxt in self._replace_phrase(tokens, old, new):
                        if nxt in seen:
                            continue
                        seen.add(nxt)
                        yield ' '.join(nxt)
                        queue.append((nxt, depth + 1))
                        if len(seen) >= self.max_rewrite_states:
                            return

    def teach(self, text: str, frame: dict, source: str = 'explicit_annotation', evidence=None) -> bool:
        if len(text) > 2048:
            raise ValueError('La construcción excede 2048 caracteres.')
        if not isinstance(frame, dict) or 'act' not in frame:
            raise ValueError('Falta el acto comunicativo en la anotación.')
        normalized = normalize(text)
        work = deepcopy(frame)
        values: list[tuple[tuple, str | int]] = []
        for key in ('args', 'values'):
            for i, v in enumerate(work.get(key, [])):
                if not (isinstance(v, str) and v.startswith('?')):
                    values.append(((key, i), v))
        if 'value' in work:
            values.append((('value',), work['value']))
        used: set[int] = set()
        spans = []
        for path, value in sorted(values, key=lambda x: -len(str(x[1]))):
            if type(value) not in (str, int):
                raise ValueError('Los argumentos anotados deben ser texto o enteros.')
            needle = normalize(str(value))
            hits = [m for m in re.finditer(r'(?<!\w)' + re.escape(needle) + r'(?!\w)', normalized)
                    if not used.intersection(range(m.start(), m.end()))]
            if len(hits) != 1:
                raise ValueError(f'No se puede alinear de forma inequívoca: {value!r}. Usa un ejemplo con valores distintos.')
            m = hits[0]
            used.update(range(m.start(), m.end()))
            spans.append((m.start(), m.end(), path, type(value) is int))
        spans.sort()
        pattern, surface, slots, pos = [], [], [], 0
        for i, (a, b, path, numeric) in enumerate(spans):
            fixed, name = normalized[pos:a], f's{i}'
            pattern.append(re.escape(fixed).replace(r'\ ', r'\s+'))
            pattern.append(f'(?P<{name}>' + (r'-?\d+' if numeric else r'.+?') + ')')
            surface.extend((fixed, '{' + name + '}'))
            slots.append({'name': name, 'path': list(path), 'type': 'int' if numeric else 'str'})
            put_path(work, path, 0 if numeric else '__SLOT__')
            pos = b
        pattern.append(re.escape(normalized[pos:]).replace(r'\ ', r'\s+'))
        surface.append(normalized[pos:])
        c = Construction(''.join(pattern), work, slots, ''.join(surface))
        signature = (c.pattern, str(c.frame), str(c.slots))
        if any((v.pattern, str(v.frame), str(v.slots)) == signature for v in self.constructions):
            return False
        if c.parse(text) != self._canonical_frame(frame):
            raise ValueError('La construcción no reproduce la anotación de entrenamiento.')
        self.constructions.append(c)
        self._learn_rewrites(c)
        self.examples.append({'text': text, 'frame': deepcopy(frame), 'source': str(source),
                              'evidence': list(evidence or [])})
        return True

    @staticmethod
    def _canonical_frame(frame: dict) -> dict:
        out = deepcopy(frame)
        for key in ('args', 'values'):
            if key in out:
                out[key] = [normalize(v) if isinstance(v, str) and not v.startswith('?') else v for v in out[key]]
        if isinstance(out.get('value'), str):
            out['value'] = normalize(out['value'])
        return out

    @staticmethod
    def _specificity(c: Construction) -> tuple[int, int]:
        """Prefer constructions that explain more surface text as fixed structure.

        A generic slot must not beat a construction that accounts for additional
        words explicitly.  The score is independent of particular vocabulary:
        fixed token count first, then fixed character count.
        """
        surface=c.surface
        for slot in c.slots:
            surface=surface.replace('{' + slot['name'] + '}', ' ')
        tokens=surface.split()
        return (len(tokens), sum(len(x) for x in tokens))

    def parse(self, text: str) -> dict:
        if len(text) > 2048:
            return {'status': 'unrecognized', 'frame': None, 'alternatives': [], 'reason': 'Entrada demasiado larga.'}
        matches: list[tuple[dict, tuple[int,int], bool]] = []
        for c in self.constructions:
            frame = c.parse(text)
            if frame is not None:
                matches.append((frame,self._specificity(c),False))
        if not matches and self.rewrites:
            by_schema: dict[str, list[Construction]] = defaultdict(list)
            for c in self.constructions:
                by_schema[self._schema(c)].append(c)
            for schema, constructions in by_schema.items():
                pred=constructions[0].frame.get('pred') if constructions else None
                for variant in self._rewrite_variants(text, schema, pred):
                    if variant == normalize(text):
                        continue
                    for c in constructions:
                        frame = c.parse(variant)
                        if frame is not None:
                            matches.append((frame,self._specificity(c),True))
        if not matches:
            return {'status':'unrecognized','frame':None,'alternatives':[],'composed_paraphrase':False}
        best=max(score for _,score,_ in matches)
        found=[]; rewritten=False
        for frame,score,rw in matches:
            if score != best:
                continue
            if frame not in found:
                found.append(frame)
            rewritten = rewritten or rw
        return {'status': 'parsed' if len(found) == 1 else 'ambiguous',
                'frame': found[0] if len(found) == 1 else None, 'alternatives': found,
                'composed_paraphrase': rewritten}

    def describe(self, pred: str, args: tuple[str, ...]) -> str:
        frame = {'act': 'assert', 'pred': pred, 'args': list(args)}
        for c in self.constructions:
            text = c.render(frame)
            if text is not None:
                return text
        return f'{pred}({", ".join(args)})'

    def as_dict(self) -> dict:
        # Persist annotations, not arbitrary executable regex supplied by files.
        return {'examples': self.examples}

    @classmethod
    def from_dict(cls, data: dict) -> Language:
        language = cls()
        for ex in data.get('examples', []):
            language.teach(ex['text'], ex['frame'], ex.get('source','explicit_annotation'), ex.get('evidence', []))
        return language

"""G-57: answering from a loaded text (a business, a manual, any document).

The text is cut into units by its layout alone: lines, list items, table rows
and the sentences of long lines.  Each unit keeps the heading that governs it
(the short line above it, a line ending in a colon, or a question of a
frequently-asked-questions section) and the document's title.

A question is answered with the unit that best explains it under counted
statistics, both counted in question–answer pairs written by people (MFAQ):
- how often an answer repeats a word of its question (``pi``);
- which answer words a question word calls for (``bridge``).

The unit is given only when its calibration cell, counted on held-out pages,
keeps the error among answered questions within the preregistered bound.
Otherwise the engine says it does not know.  Nothing is cut or generated: the
answer is the document's own text.
"""
from __future__ import annotations

import math
import re
import unicodedata

_TOKEN = re.compile(r'\w+|[^\w\s]')
_LIST_MARK = re.compile(r'^\s*(?:[-*•·–—]+|\d{1,3}[.)])\s+')
_MD_HEADING = re.compile(r'^#{1,6}\s*')
_RULE_ROW = re.compile(r'^[\s|:+=-]+$')
# A sentence ends after a word of four or more letters, a number or a closing
# mark, never after a run of dots or a short abbreviation («Av.», «Lic.»).
_SENTENCE_END = re.compile(r'(?:(?<=\w{4}[.!?])|(?<=\d[.!?])|(?<=[)"»][.!?]))\s+(?=[¿¡"«(]?[A-ZÁÉÍÓÚÑ0-9])')
# The shape of a figure («$», «9», «9:9», «9,9»): format, not words.
_FIGURE = re.compile(r'\d+(?:[:.,/-]\d+)*|[$€£%]')
_FIELD = re.compile(r'^[^:]{1,60}:\s+\S')
# Layout conventions, not words: a heading is a short line without closing
# punctuation; longer lines are content.
HEADING_WORDS = 8
SECTION_MAX = 8
LEMMA_ENDING = 4
LEMMA_RULE_SUPPORT = 20
LEMMA_RULE_SHARE = 0.8
PI_BINS = (0.2, 0.4, 0.6, 0.8)
MARGIN_BINS = (0.5, 1.0, 2.0, 4.0)
UNKNOWN_TEXT = 'No lo sé: no encontré esa información en el texto que tengo.'


def _plain(word: str) -> str:
    decomposed = unicodedata.normalize('NFKD', word.lower())
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


def _bin(value: float, edges) -> int:
    return sum(value >= edge for edge in edges)


def cell_key(unaddressed: float, margin: float) -> str:
    """The calibration cell of an answer: the largest counted δ among the
    question words the unit leaves unexplained, and its lead over the
    runner-up (both binned)."""
    return f'{_bin(unaddressed, PI_BINS)},{_bin(margin, MARGIN_BINS)}'


def _empty_context_model() -> dict:
    return {'delta': {}, 'rare_delta': 0.5, 'bridge': {}, 'admitted': [], 'cells': {}}


class ContextMixin:
    """Load a text with its instructions and answer questions from it."""

    # ----- words --------------------------------------------------------
    def _plain_lemmas(self):
        """Dictionary forms learned from AnCora (G-44), looked up without
        accents (people write «cuanto», «alcoholicas»), and ending rules
        induced from the same annotations for words AnCora never saw: the
        change from form to lemma that an ending takes in at least
        LEMMA_RULE_SHARE of the LEMMA_RULE_SUPPORT or more forms that end so."""
        counts = self.syntax_model.get('lemma_counts', {})
        cache = getattr(self, '_plain_lemma_cache', None)
        if cache is not None and cache[0] == len(counts):
            return cache
        forms, rules = {}, {}
        for form, row in counts.items():
            total = sum(row.values())
            lemma = max(sorted(row), key=lambda k: row[k])
            plain_form, plain_lemma = _plain(form), _plain(lemma)
            if plain_form not in forms or forms[plain_form][0] < total:
                forms[plain_form] = (total, plain_lemma)
            common = 0
            while common < min(len(plain_form), len(plain_lemma)) and plain_form[common] == plain_lemma[common]:
                common += 1
            change = (len(plain_form) - common, plain_lemma[common:])
            for size in range(1, LEMMA_ENDING + 1):
                if len(plain_form) > size + 1:
                    row_rules = rules.setdefault(plain_form[-size:], {})
                    row_rules[change] = row_rules.get(change, 0) + 1
        kept = {}
        for ending, row in rules.items():
            seen = sum(row.values())
            change, top = max(sorted(row.items()), key=lambda kv: kv[1])
            if seen >= LEMMA_RULE_SUPPORT and top >= LEMMA_RULE_SHARE * seen:
                kept[ending] = change
        cache = (len(counts), {f: l for f, (_, l) in forms.items()}, kept)
        self._plain_lemma_cache = cache
        return cache

    def _term(self, word: str) -> str:
        _, forms, rules = self._plain_lemmas()
        plain = _plain(word)
        if plain in forms:
            return forms[plain]
        for size in range(LEMMA_ENDING, 0, -1):
            change = rules.get(plain[-size:]) if len(plain) > size + 1 else None
            if change is not None:
                cut, add = change
                return plain[:len(plain) - cut] + add
        return plain

    def context_terms(self, text: str) -> list[str]:
        """The learned dictionary forms of the words of a text, and the shape
        of each figure in it."""
        shapes = [re.sub(r'\d+', '9', m) for m in _FIGURE.findall(text)] if getattr(self, 'figure_shapes', True) else []
        if self.syntax_model.get('sentences'):
            words = self.split_words(text)
            return [self._term(w) for w in words if w[:1].isalnum()] + shapes
        return [_plain(w) for w in _TOKEN.findall(text) if w[:1].isalnum()] + shapes

    def _bridge(self) -> dict:
        """The counted associations, stored compactly as ``'a:p|a:p'``."""
        cache = getattr(self, '_bridge_cache', None)
        stored = self.context_model.get('bridge', {})
        if cache is None or cache[0] is not stored:
            parsed = {q: [(a, float(p)) for a, p in (item.rsplit(':', 1) for item in row.split('|') if item)]
                      for q, row in stored.items()}
            cache = (stored, parsed)
            self._bridge_cache = cache
        return cache[1]

    def _delta(self, term: str) -> float:
        """How often an answer repeats this word *because* its question has it:
        (π − P_A) / (1 − P_A), with π the counted rate at which answers repeat a
        word of their question and P_A the rate of the word in any answer."""
        model = self.context_model
        return model.get('delta', {}).get(term, model.get('rare_delta', 0.5))

    # ----- loading ------------------------------------------------------
    @staticmethod
    def _heading_like(line: str) -> bool:
        words = line.split()
        if not words or len(words) > HEADING_WORDS:
            return False
        if line.endswith(':'):
            return True
        if line[-1] in '.,;!?…' or _FIELD.match(line):
            return False
        return True

    @staticmethod
    def _cells(line: str) -> list[str] | None:
        if '\t' in line:
            cells = [c.strip() for c in line.split('\t')]
        elif line.count('|') >= 1:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
        else:
            return None
        return cells if sum(bool(c) for c in cells) >= 2 else None

    def _layout_units(self, text: str, source: str) -> list[dict]:
        units, title, section, question, header = [], '', '', '', None
        block = [0]

        def add(display: str, kind: str) -> None:
            heading = question or section
            units.append({'text': display, 'heading': heading, 'kind': kind, 'source': source, 'section': block[0],
                          'heading_terms': sorted(set(self.context_terms(' '.join(filter(None, (section, question)))))),
                          'terms': sorted(set(self.context_terms(display)))})

        lines = [raw.strip() for raw in str(text).splitlines()]
        following = [''] * len(lines)
        upcoming = ''
        for k in range(len(lines) - 1, -1, -1):
            following[k] = upcoming
            if lines[k]:
                upcoming = lines[k]
        for k, line in enumerate(lines):
            if not line:
                if question:
                    # A question's answer ends at the blank line after it.
                    block[0] += 1
                question, header = '', None
                continue
            cells = self._cells(line)
            if cells is not None:
                if _RULE_ROW.match(line):
                    continue
                if header is None:
                    header = cells
                    continue
                pairs = [f'{h}: {c}' if h else c for h, c in zip(header + [''] * len(cells), cells) if c]
                add('; '.join(pairs), 'row')
                continue
            header = None
            marked = _LIST_MARK.match(line)
            if marked:
                add(line[marked.end():].strip(), 'item')
                continue
            # Typography marks a heading (markdown, capitals, a closing colon);
            # otherwise a short line heads what follows only when content follows it.
            nxt = following[k]
            heads = bool(nxt) and (_LIST_MARK.match(nxt) or self._cells(nxt) is not None
                                   or not self._heading_like(nxt))
            if line.endswith('?') and nxt.endswith('?'):
                heads = False
            letters = [ch for ch in line if ch.isalpha()]
            strong = bool(_MD_HEADING.match(line)) or (self._heading_like(line) and (
                line.endswith(':') or (len(letters) > 1 and all(ch.isupper() for ch in letters))))
            if strong or (heads and (self._heading_like(line) or line.endswith('?'))):
                body = _MD_HEADING.sub('', line).rstrip(':').strip()
                if not title and not units:
                    title = body
                    continue
                if line.endswith('?'):
                    question = body
                else:
                    section, question = body, ''
                block[0] += 1
                # The heading is also a unit: meeting it asks for its section.
                units.append({'text': body, 'heading': '', 'kind': 'question' if line.endswith('?') else 'heading',
                              'source': source, 'section': block[0], 'heading_terms': [],
                              'terms': sorted(set(self.context_terms(body)))})
                continue
            for sentence in _SENTENCE_END.split(line):
                if sentence.strip():
                    add(sentence.strip(), 'sentence' if sentence != line else 'line')
        self._layout_title = title
        return units

    def load_context(self, text: str, instructions: str = '') -> dict:
        """Replace the loaded context with a text and its instructions."""
        self.context_units = self._layout_units(text, 'context')
        # The title covers every unit: its words are explained, never ranked.
        self.context_title = sorted(set(self.context_terms(self._layout_title)))
        self.context_instructions = self._layout_units(instructions, 'instructions') if instructions else []
        self._context_index = None
        return {'status': 'context_loaded', 'units': len(self.context_units),
                'instructions': len(self.context_instructions)}

    def _index(self):
        if getattr(self, '_context_index', None) is None:
            postings: dict = {}
            for i, unit in enumerate(self.context_units):
                words = set(unit['terms'])
                if getattr(self, 'unit_headings', True):
                    words |= set(unit['heading_terms'])
                for term in words:
                    postings.setdefault(term, []).append(i)
            self._context_index = postings
        return self._context_index

    # ----- retrieval ----------------------------------------------------
    def _rank(self, terms: list[str]) -> dict | None:
        """The best unit for these question words and its calibration cell."""
        units = self.context_units
        if not units:
            return None
        postings, total = self._index(), len(units)
        bridge = self._bridge() if getattr(self, 'bridge', True) else {}
        title = set(getattr(self, 'context_title', ()))
        base, gains, how, met = 0.0, {}, {}, {}
        # Mixture model: the answer unit holds q because the question asks for
        # it (probability δ) or by chance, like any unit of this text (p0).
        for q in dict.fromkeys(terms):
            delta = min(max(self._delta(q), 0.0), 1 - 1e-4)
            p0 = (len(postings.get(q, ())) + 0.5) / (total + 1)
            absent = 0.0 if q in title else math.log(1 - delta)
            base += absent
            best: dict = {}
            for i in postings.get(q, ()):
                best[i] = (math.log(delta / p0 + 1 - delta) - absent, 'direct', q)
            for a, d_a in bridge.get(q, ()):
                pa0 = (len(postings.get(a, ())) + 0.5) / (total + 1)
                gain = math.log(d_a / pa0 + 1 - d_a)
                for i in postings.get(a, ()):
                    if i not in best or best[i][0] < gain:
                        best[i] = (gain, 'bridge', a)
            for i, (gain, kind, word) in best.items():
                gains[i] = gains.get(i, 0.0) + gain
                how.setdefault(i, {})[q] = kind
                met.setdefault(i, set()).add(word)
            how.setdefault(None, {})[q] = 0.0 if q in title else delta
        if not gains:
            order = [(base, 0)]
        else:
            order = sorted(((base + g, i) for i, g in gains.items()), key=lambda x: (-x[0], x[1]))
        top_score, top = order[0]
        explained = how.get(top, {})
        # A question that meets a heading, or meets a unit only through its
        # heading, asks for the heading's whole section.
        unit = units[top]
        own = set(unit['terms'])
        section = None
        if getattr(self, 'unit_headings', True) and explained and (
                unit['kind'] in ('heading', 'question') or (unit['heading'] and not (met.get(top, set()) & own))):
            members = [i for i, u in enumerate(units) if u['section'] == unit['section']
                       and u['kind'] not in ('heading', 'question')]
            if 0 < len(members) <= SECTION_MAX:
                section = members
        rivals = [s for s, i in order[1:] if section is None or i not in section]
        runner = rivals[0] if rivals else base
        unaddressed = max((pi for q, pi in how[None].items() if q not in explained), default=0.0)
        margin = top_score - runner
        return {'unit': top, 'score': top_score, 'margin': margin, 'unaddressed': unaddressed,
                'cell': cell_key(unaddressed, margin), 'explained': explained, 'section': section}

    def _admitted(self, ranked: dict | None) -> bool:
        if ranked is None:
            return False
        if not getattr(self, 'calibrated', True):
            return True
        return ranked['cell'] in set(self.context_model.get('admitted', ()))

    def _shown(self, ranked: dict) -> str:
        unit = self.context_units[ranked['unit']]
        if ranked.get('section'):
            members = [self.context_units[i] for i in ranked['section']]
            heading = members[0]['heading']
            listed = '; '.join(m['text'].rstrip('.;') for m in members) + '.'
            if heading.endswith('?') or members[0]['text'] == heading:
                return listed
            return (heading.capitalize() if heading.isupper() else heading) + ': ' + listed

        own = set(unit['terms'])
        heading = unit['heading']
        needs_heading = heading and any(q not in own for q, kind in ranked['explained'].items() if kind == 'direct')
        text = unit['text']
        return f'{heading}: {text}' if needs_heading and getattr(self, 'unit_headings', True) else text

    # ----- turns --------------------------------------------------------
    def _asks(self, text: str) -> bool:
        if '?' in text or '¿' in text:
            return True
        words = [_plain(w) for w in _TOKEN.findall(text) if w[:1].isalnum()]
        interrogatives = {_plain(w) for w in self.syntax_model.get('interrogatives', ())}
        return bool(words) and words[0] in interrogatives

    def _phatic(self, text: str) -> bool:
        """A turn that asks nothing and names nothing the text talks about."""
        if not text.strip(' ,.;:!¡'):
            return True
        if self._asks(text):
            return False
        postings = self._index()
        return not any(t in postings for t in self.context_terms(text))

    @staticmethod
    def _client_turns(history) -> list[str]:
        turns = []
        for turn in history or ():
            if isinstance(turn, str):
                turns.append(turn)
            elif isinstance(turn, dict):
                role = str(turn.get('role', turn.get('rol', 'user'))).lower()
                if role in ('user', 'client', 'cliente', 'usuario', 'persona', 'human'):
                    turns.append(str(turn.get('text', turn.get('content', turn.get('texto', '')))))
            elif isinstance(turn, (list, tuple)) and turn:
                turns.append(str(turn[0]))
        return turns

    def answer(self, question: str, history=None) -> dict:
        """Answer one turn of a person from the loaded text, or say it is not there."""
        text = str(question).strip()
        opening = ''
        cut = text.find('¿')
        if cut > 0 and self._phatic(text[:cut]):
            opening, text = text[:cut].strip(' ,.;:'), text[cut:]
        if not text or self._phatic(text):
            said = (opening or text).strip(' ,.;:')
            return {'text': (said[:1].upper() + said[1:] + '.') if said else '', 'status': 'phatic',
                    'evidence': None, 'confidence': None}
        ranked = self._rank(self.context_terms(text))
        if not self._admitted(ranked) and getattr(self, 'follow_up', True):
            earlier = [t for t in self._client_turns(history) if self._asks(t) and not self._phatic(t)]
            if earlier:
                joined = self._rank(self.context_terms(text) + self.context_terms(earlier[-1]))
                if self._admitted(joined):
                    ranked = joined
        prefix = (opening[:1].upper() + opening[1:] + '. ') if opening else ''
        cells = self.context_model.get('cells', {}).get(ranked['cell']) if ranked else None
        precision = round(cells[1] / cells[0], 4) if cells and cells[0] else None
        if not self._admitted(ranked):
            # Not asserted: the best unit and its counted precision go to the
            # caller apart from the reply, so an integrator can decide.
            candidate = ({'text': self._shown(ranked), 'precision': precision}
                         if ranked is not None and ranked['unit'] is not None else None)
            return {'text': prefix + UNKNOWN_TEXT, 'status': 'unknown', 'evidence': None,
                    'confidence': None, 'cell': ranked['cell'] if ranked else None, 'candidate': candidate}
        unit = self.context_units[ranked['unit']]
        return {'text': prefix + self._shown(ranked), 'status': 'answered',
                'evidence': {'unit': unit['text'], 'heading': unit['heading'], 'index': ranked['unit']},
                'confidence': precision, 'cell': ranked['cell']}

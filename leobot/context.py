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
Otherwise it is quoted with a warning when its counted usefulness reaches the
operating point (G-60: naive Bayes over seven features, isotonic calibration),
or the engine says it does not know.  Nothing is cut or generated: the answer
is the document's own text.
"""
from __future__ import annotations

import math
import re
import unicodedata

from .reading import KIND_SUPPORT

_TOKEN = re.compile(r'\w+|[^\w\s]')
_LIST_MARK = re.compile(r'^\s*(?:[-*•·–—]+|\d{1,3}[.)])\s+')
_MD_HEADING = re.compile(r'^#{1,6}\s*')
_RULE_ROW = re.compile(r'^[\s|:+=-]+$')
# A sentence ends after a word of four or more letters, a number or a closing
# mark, never after a run of dots or a short abbreviation («Av.», «Lic.»).
_SENTENCE_END = re.compile(r'(?:(?<=\w{4}[.!?])|(?<=\d[.!?])|(?<=[)"»][.!?]))\s+(?=[¿¡"«(]?[A-ZÁÉÍÓÚÑ0-9])')
_FIELD = re.compile(r'^[^:]{1,60}:\s+\S')
# Layout conventions, not words: a heading is a short line without closing
# punctuation; longer lines are content.
HEADING_WORDS = 8
LEMMA_ENDING = 4
LEMMA_RULE_SUPPORT = 20
LEMMA_RULE_SHARE = 0.8
PI_BINS = (0.2, 0.4, 0.6, 0.8)
MARGIN_BINS = (0.5, 1.0, 2.0, 4.0)
COVER_BINS = (0.25, 0.5, 0.75, 0.999)
LENGTH_BINS = (6, 13, 26)
CITE_FROM = 0.7
UNKNOWN_TEXT = 'No lo sé: no encontré esa información en el texto que tengo.'
CLOSEST_TEXT = 'No lo tengo seguro. Lo más cercano que dice el texto es: «{}».'
INSTRUCTION_TEXT = 'Sobre eso, las indicaciones del negocio dicen: «{}».'
FALLBACK_TEXT = ' Las indicaciones del negocio para estos casos dicen: «{}».'
ECHO_WORDS = 4
# G-103: words that share a beginning are morphological relatives (pagar, pago; hora, horario).
SOFT_PREFIX = 3
SOFT_RATIO = 0.5
CANDIDATES = 8
BM25_K1 = 1.2
BM25_B = 0.75
USEFUL_KINDS = {'line': 0, 'sentence': 1, 'item': 2, 'row': 3, 'heading': 4}
DENSE_FEATURES = ('rank', 'gain', 'gap', 'second', 'bm25', 'own', 'inherited', 'own_share', 'own_mass', 'inherited_mass',
                  'unexplained_max', 'unexplained_sum', 'indirect', 'length', 'kind', 'digits', 'headed', 'position',
                  'terms', 'mass', 'interrogative', 'asked_share', 'asked_count',
                  'history', 'carried_mass', 'same_heading', 'same_unit', 'carried_gain', 'carried_mass_alone',
                  'same_heading_alone', 'instruction')
CARRIED_WEIGHT = 0.5


def _plain(word: str) -> str:
    decomposed = unicodedata.normalize('NFKD', word.lower())
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


def _shapes(text: str) -> list[str]:
    """G-103: the character-class shape of each word that is not made of letters alone
    («$250.000» → «SH:$d.d», «8:00» → «SH:d:d», «ana@x.co» → «SH:a@a.a»), so a learned
    association can tell what kind of value a unit holds; no list of words or symbols."""
    out = set()
    for word in text.split():
        word = word.rstrip('.,;:!?)»"').lstrip('(¿¡«"')
        if word and not word.isalpha():
            shape = re.sub(r'\d+', 'd', re.sub(r'[^\W\d_]+', 'a', word))
            out.add('SH:' + shape[:8])
    return sorted(out)


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
        """The learned dictionary forms of the words of a text."""
        if self.syntax_model.get('sentences'):
            words = self.split_words(text)
            return [self._term(w) for w in words if w[:1].isalnum()]
        return [_plain(w) for w in _TOKEN.findall(text) if w[:1].isalnum()]

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

    def _unwrapped(self, lines: list[str]) -> list[str]:
        """G-63: a sentence broken across lines (text pasted from a page or a
        document) is one line again: a long line that does not close its
        sentence continues on the next when that one starts in lowercase or
        with a figure and is not a list item or a table row.

        G-64: the document tells its own width, the length of its longest
        line.  A line was cut by that width when the first word of the next
        one would not have fitted.  When the text comes cut (at least 4 such
        lines, and at least a fifth of its lines), a cut line continues on
        the next whatever its case or punctuation."""
        def mergeable(prev: str, line: str) -> bool:
            return bool(prev and line) and not self._heading_like(prev) and not _LIST_MARK.match(line) \
                and self._cells(line) is None and self._cells(prev) is None

        texty = [line for line in lines if line]
        width = max((len(line) for line in texty), default=0)

        def cut(line: str, following: str) -> bool:
            return bool(line and following) and len(line) + 1 + len(following.split()[0]) > width
        cuts = sum(cut(a, b) for a, b in zip(lines, lines[1:]))
        by_width = cuts >= 4 and cuts >= 0.2 * len(texty)
        out: list[str] = []
        raw = ''
        for line in lines:
            prev = out[-1] if out else ''
            if mergeable(prev, line) and (cut(raw, line) if by_width else
                                          prev[-1].isalnum() and (line[0].islower() or line[0].isdigit())):
                out[-1] = prev + ' ' + line
            else:
                out.append(line)
            raw = line
        return out

    def _layout_units(self, text: str, source: str) -> list[dict]:
        units, title, section, question, header = [], '', '', '', None
        section_kind, block_open = '', False

        def add(display: str, kind: str, asked: str = '') -> None:
            heading = asked or question or section
            sequence = self.context_terms(display)
            own = sorted(set(sequence))
            # G-61: a unit is read under its heading, so it also answers to the
            # heading's words (a price row under «Extras», an answer under its question).
            # G-62: a question governs its answer; a title marked by typography
            # (markdown or capitals) governs its whole section; a line ending in a
            # colon introduces only its own block, up to the next blank line; a short
            # unmarked line may be content and governs nothing.
            governs = (section_kind == 'title' or (section_kind == 'colon' and block_open)
                       or getattr(self, 'inherit_all_headings', False))
            governing = asked or question or (section if governs else '')
            inherited = sorted(set(self.context_terms(governing)) - set(own)) if governing else []
            units.append({'text': display, 'heading': heading, 'kind': kind, 'source': source,
                          'terms': own, 'inherited': inherited, 'classes': self._classes(display),
                          'sequence': sequence, 'shapes': _shapes(display)})

        lines = [raw.strip() for raw in str(text).splitlines()]
        if getattr(self, 'join_wrapped', True):
            lines = self._unwrapped(lines)
        following = [''] * len(lines)
        upcoming = ''
        for k in range(len(lines) - 1, -1, -1):
            following[k] = upcoming
            if lines[k]:
                upcoming = lines[k]
        for k, line in enumerate(lines):
            if not line:
                # A question's answer ends at the blank line after it.
                question, header = '', None
                block_open = False
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
                    section, question, block_open = body, '', True
                    section_kind = ('title' if _MD_HEADING.match(line) or not line.endswith(':') else 'colon') \
                        if strong else 'unmarked'
                # The heading is also a unit.
                units.append({'text': body, 'heading': '', 'kind': 'question' if line.endswith('?') else 'heading',
                              'source': source, 'terms': sorted(set(self.context_terms(body))), 'inherited': [],
                              'classes': {}})
                continue
            sentences = [part.strip() for part in _SENTENCE_END.split(line) if part.strip()]
            asked = ''
            for n, sentence in enumerate(sentences):
                if sentence.endswith('?') and n + 1 < len(sentences) and getattr(self, 'inline_questions', True):
                    # G-61: a question that opens its answer on the same line heads it.
                    units.append({'text': sentence, 'heading': '', 'kind': 'question', 'source': source,
                                  'terms': sorted(set(self.context_terms(sentence))), 'inherited': [],
                                  'classes': {}})
                    asked = sentence
                    continue
                add(sentence, 'sentence' if len(sentences) > 1 else 'line', asked)
        self._layout_title = title
        return units

    def _classes(self, text: str) -> dict:
        """G-59: the learned word classes (AnCora tagger) in a unit, with how
        many words carry each (G-60)."""
        if not self.syntax_model.get('sentences'):
            return {}
        words = self.split_words(text)
        counts: dict = {}
        for tag in (self.tag_words(words) or []) if words else []:
            counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items()))

    def _asked_class(self, question: str):
        """G-59: the class of answer this kind of question asks for, learned
        in G-53 by counting worked questions (SQuAD-es): its most frequent
        class and that class's share.  A weak or common class weighs little
        by itself in the mixture, so no dominance threshold is needed."""
        if not self.syntax_model.get('sentences') or not getattr(self, 'answer_class', True):
            return None
        words = [w.lower() for w in self.split_words(question) if w[:1].isalnum()]
        table = self.reading_model.get('answer_kinds', {})
        for key in reversed(self._kind_keys(words)):
            row = table.get(key)
            if row and row['n'] >= KIND_SUPPORT:
                cls, count = max(sorted(row['classes'].items()), key=lambda kv: kv[1])
                return cls, count / row['n']
        return None

    def load_context(self, text: str, instructions: str = '') -> dict:
        """Replace the loaded context with a text and its instructions."""
        self.context_units = self._layout_units(text, 'context')
        # The title covers every unit: its words are explained, never ranked.
        self.context_title = sorted(set(self.context_terms(self._layout_title)))
        self.context_instructions = self._layout_units(instructions, 'instructions') if instructions else []
        self._context_index = None
        self._instruction_space = None
        self._fallback = None
        return {'status': 'context_loaded', 'units': len(self.context_units),
                'instructions': len(self.context_instructions)}

    def _instruction_view(self):
        """G-105: the instructions as a text of their own: the same object seen with the
        instruction units, their own index and no title, so the same ranking and the
        same usefulness model read them."""
        if not getattr(self, 'follow_instructions', True) or not getattr(self, 'context_instructions', None):
            return None
        view = getattr(self, '_instruction_space', None)
        if view is None:
            view = object.__new__(type(self))
            view.__dict__.update(self.__dict__)
            view.context_units = self.context_instructions
            view.context_title = []
            view._context_index = None
            view._prefix_buckets = None
            view._unit_term_sets = None
            view._instruction_space = None
            self._instruction_space = view
        return view

    def _fallback_exit(self):
        """G-105: the instruction that says what to do when something is not known: the
        instruction sentence the counted classifier gives the highest chance, when that
        chance reaches its threshold.  It does not depend on the question."""
        model = self.context_model.get('fallback')
        if not model or not getattr(self, 'follow_instructions', True) or not getattr(self, 'context_instructions', None):
            return None
        if getattr(self, '_fallback', None) is None:
            best, at = None, -1
            for k, unit in enumerate(self.context_instructions):
                if unit['kind'] in ('heading', 'question'):
                    continue
                z = model['bias'] + sum(model['weights'].get(t, 0.0) for t in set(unit['terms']))
                chance = 1.0 / (1.0 + math.exp(-z)) if z > -30 else 0.0
                if chance >= model['threshold'] and (best is None or chance > best):
                    best, at = chance, k
            self._fallback = (at,)
        at = self._fallback[0]
        return None if at < 0 else self.context_instructions[at]

    def _index(self):
        if getattr(self, '_context_index', None) is None:
            postings: dict = {}
            for i, unit in enumerate(self.context_units):
                if unit['kind'] == 'question':
                    continue  # a question heads its answer; it is never the answer (G-57r)
                terms = unit['terms'] + (unit.get('inherited', []) if getattr(self, 'inherit_heading', True) else [])
                for term in terms:
                    postings.setdefault(term, []).append(i)
            self._context_index = postings
            self._prefix_buckets = None
            self._unit_term_sets = None
        return self._context_index

    def _related(self, term: str) -> list[tuple[str, float]]:
        """G-103: the words of the text that begin like this one (at least SOFT_PREFIX
        letters and half of the longer word), with the share of the longer word
        that they have in common."""
        if len(term) < SOFT_PREFIX:
            return []
        postings = self._index()
        if getattr(self, '_prefix_buckets', None) is None:
            buckets: dict = {}
            for word in postings:
                buckets.setdefault(word[:SOFT_PREFIX], []).append(word)
            self._prefix_buckets = buckets
        out = []
        for word in self._prefix_buckets.get(term[:SOFT_PREFIX], ()):
            if word == term:
                continue
            common = 0
            for a, b in zip(term, word):
                if a != b:
                    break
                common += 1
            share = common / max(len(term), len(word))
            if share >= SOFT_RATIO:
                out.append((word, share))
        return out

    # ----- retrieval ----------------------------------------------------
    def _gains(self, terms: list[str], question: str = ''):
        """The mixture model of G-57: for each unit, how much better than chance it
        explains the question words, and how (directly, through a counted bridge or,
        G-103, through a word that begins like the question's word)."""
        units = self.context_units
        postings, total = self._index(), len(units)
        bridge = self._bridge() if getattr(self, 'bridge', True) else {}
        soft = getattr(self, 'soft_prefix', True)
        title = set(getattr(self, 'context_title', ()))
        base, gains, how = 0.0, {}, {}
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
            if soft and q not in title:
                for word, share in self._related(q):
                    d_w = delta * share
                    pw0 = (len(postings.get(word, ())) + 0.5) / (total + 1)
                    gain = math.log(d_w / pw0 + 1 - d_w) - absent
                    for i in postings[word]:
                        if i not in best or best[i][0] < gain:
                            best[i] = (gain, 'soft', word)
            for a, d_a in bridge.get(q, ()):
                pa0 = (len(postings.get(a, ())) + 0.5) / (total + 1)
                gain = math.log(d_a / pa0 + 1 - d_a)
                for i in postings.get(a, ()):
                    if i not in best or best[i][0] < gain:
                        best[i] = (gain, 'bridge', a)
            for i, (gain, kind, _) in best.items():
                gains[i] = gains.get(i, 0.0) + gain
                how.setdefault(i, {})[q] = kind
            how.setdefault(None, {})[q] = 0.0 if q in title else delta
        asked = self._asked_class(question) if question else None
        if asked is not None:
            # The answer holds a word of the asked class (share learned in G-53),
            # or it holds one by chance, like any unit of this text.
            cls, share = asked
            share = min(share, 1 - 1e-4)
            having = [i for i, u in enumerate(units) if cls in u.get('classes', ())
                      and u['kind'] not in ('question', 'heading')]
            p0 = (len(having) + 0.5) / (total + 1)
            absent = math.log(1 - share)
            base += absent
            for i in having:
                gains[i] = gains.get(i, 0.0) + math.log(share / p0 + 1 - share) - absent
        return base, gains, how, asked

    def _rank(self, terms: list[str], question: str = '', previous: dict | None = None) -> dict | None:
        """The best unit for these question words and its calibration cell."""
        units = self.context_units
        if not units:
            return None
        base, gains, how, asked = self._gains(terms, question)
        model = self.context_model.get('usefulness')
        if model and getattr(self, 'candidate_model', True):
            return self._rank_by_model(model, terms, question, base, gains, how, asked, previous)
        if not gains:
            order = [(base, 0)]
        else:
            order = sorted(((base + g, i) for i, g in gains.items()), key=lambda x: (-x[0], x[1]))
        top_score, top = order[0]
        explained = how.get(top, {})
        runner = order[1][0] if len(order) > 1 else base
        asked_for = how.get(None, {})
        unaddressed = max((pi for q, pi in asked_for.items() if q not in explained), default=0.0)
        margin = top_score - runner
        mass = sum(asked_for.values())
        covered = sum(pi for q, pi in asked_for.items() if q in explained) / mass if mass else 0.0
        ranked = {'unit': top, 'score': top_score, 'margin': margin, 'unaddressed': unaddressed,
                  'cell': cell_key(unaddressed, margin), 'explained': explained, 'covered': covered,
                  'asked': asked}
        ranked['features'] = self._features(ranked, question)
        ranked['useful'] = self._usefulness(ranked['features'])
        return ranked

    # ----- G-103: usefulness of each candidate --------------------------------
    def _unit_sets(self):
        self._index()
        if getattr(self, '_unit_term_sets', None) is None:
            self._unit_term_sets = [frozenset(u['terms']) | frozenset(u.get('inherited', ())) for u in self.context_units]
            valid = [u for u in self.context_units if u['kind'] != 'question']
            self._mean_length = sum(max(1, len(u.get('sequence', u['terms']))) for u in valid) / max(1, len(valid))
            self._valid_units = len(valid)
        return self._unit_term_sets

    def _bm25(self, terms: list[str]) -> dict:
        """Okapi BM25 of each unit for the question words (title words left out); the
        words of the governing heading count half."""
        self._unit_sets()
        postings, units = self._index(), self.context_units
        title = set(getattr(self, 'context_title', ()))
        scores: dict = {}
        for q in dict.fromkeys(terms):
            listed = postings.get(q)
            if q in title or not listed:
                continue
            idf = math.log(1 + (self._valid_units - len(listed) + 0.5) / (len(listed) + 0.5))
            for i in listed:
                unit = units[i]
                sequence = unit.get('sequence', unit['terms'])
                tf = sequence.count(q) or (0.5 if q in unit.get('inherited', ()) else 0)
                if tf:
                    length = max(1, len(sequence))
                    scores[i] = scores.get(i, 0.0) + idf * tf * (BM25_K1 + 1) / (
                        tf + BM25_K1 * (1 - BM25_B + BM25_B * length / self._mean_length))
        return scores

    def _previous_topic(self, history) -> dict | None:
        """G-104: the last thing the person asked that names something in the text: its
        words and the unit the mixture gives it by itself.  Only what the caller sends."""
        if not history or not getattr(self, 'history_features', True) or not self.context_units:
            return None
        for entry in reversed(list(history)):
            role, said = (entry.get('role', 'user'), entry.get('text', '')) if isinstance(entry, dict) else ('user', entry)
            if role != 'user':
                continue
            _, text = self._question_part(str(said))
            if not text or self._phatic(text):
                continue
            terms = self.context_terms(text)
            if not terms:
                continue
            _, gains, _, _ = self._gains(terms, '')
            units = self.context_units
            unit = min(((-g, i) for i, g in gains.items() if units[i]['kind'] not in ('heading', 'question')),
                       default=(0.0, None))[1]
            return {'terms': terms, 'unit': unit}
        return None

    def _candidate_table(self, terms: list[str], question: str, base: float, gains: dict, how: dict, asked,
                         previous: dict | None = None):
        """The first CANDIDATES units (headings are never an answer) with the general
        features and the sparse pairs the usefulness model reads."""
        units, sets = self.context_units, self._unit_sets()
        distinct = list(dict.fromkeys(terms))
        carried, carried_gains, carried_how = [], {}, {}
        if previous is not None:
            carried = [t for t in dict.fromkeys(previous['terms']) if t not in distinct]
            if carried:
                _, carried_gains, carried_how, _ = self._gains(carried, '')
        pool = dict(gains)
        for i, g in carried_gains.items():
            pool[i] = pool.get(i, 0.0) + CARRIED_WEIGHT * g
        order = [i for _, i in sorted(((-g, i) for i, g in pool.items() if units[i]['kind'] not in ('heading', 'question')))]
        order = order[:CANDIDATES]
        if not order:
            return []
        title = set(getattr(self, 'context_title', ()))
        asked_for = how.get(None, {})
        mass = sum(asked_for.values())
        bm = self._bm25(terms)
        bm_top = max(bm.values(), default=0.0) or 1.0
        asking = {_plain(w) for w in self.syntax_model.get('interrogatives', ())}
        words = [_plain(w) for w in self.split_words(question) if w[:1].isalnum()] if question else []
        wh = 1.0 if any(w in asking for w in words) else 0.0
        share = asked[1] if asked is not None else 0.0
        top = max(gains.get(i, 0.0) for i in order)
        second = sorted((gains.get(i, 0.0) for i in order), reverse=True)[1] if len(order) > 1 else 0.0
        carried_mass = sum(carried_how.get(None, {}).values())
        carried_top = max(carried_gains.values(), default=0.0) or 1.0
        prior = units[previous['unit']]['heading'] if previous is not None and previous.get('unit') is not None else ''
        table = []
        for rank, i in enumerate(order):
            unit, held = units[i], sets[i]
            own, inherited = set(unit['terms']), set(unit.get('inherited', ()))
            explained = how.get(i, {})
            weight = lambda q: 0.0 if q in title else asked_for.get(q, 0.0)
            unexplained = [asked_for.get(q, 0.0) for q in distinct if q not in explained]
            dense = [
                float(rank), gains.get(i, 0.0), top - gains.get(i, 0.0), second, bm.get(i, 0.0) / bm_top,
                float(sum(q in own for q in distinct)), float(sum(q in inherited and q not in own for q in distinct)),
                sum(q in own for q in distinct) / (len(distinct) or 1),
                sum(weight(q) for q in distinct if q in own) / mass if mass else 0.0,
                sum(weight(q) for q in distinct if q in inherited and q not in own) / mass if mass else 0.0,
                max(unexplained, default=0.0), sum(unexplained),
                float(sum(kind != 'direct' for kind in explained.values())),
                float(len(unit['text'].split())), float(USEFUL_KINDS.get(unit['kind'], 5)),
                float(sum(ch.isdigit() for ch in unit['text'])), 1.0 if unit['heading'] else 0.0,
                i / len(units), float(len(distinct)), mass, wh, share,
                float(min(unit.get('classes', {}).get(asked[0], 0), 2)) if asked is not None else 0.0,
            ]
            if previous is None:
                dense += [0.0] * 7
            else:
                explained_before = sum(w for q, w in carried_how.get(None, {}).items() if q in carried_how.get(i, {}))
                shared = 1.0 if prior and unit['heading'] == prior else 0.0
                alone = 1.0 - min(1.0, dense[8] + dense[9])
                held_mass = explained_before / carried_mass if carried_mass else 0.0
                dense += [1.0, held_mass, shared, 1.0 if i == previous.get('unit') else 0.0,
                          carried_gains.get(i, 0.0) / carried_top, held_mass * alone, shared * alone]
            ordered = sorted(held)
            pairs = [q + '|' + w for q in distinct if q not in held for w in ordered if w != q]
            pairs += [q + '|' + shape for q in distinct for shape in unit.get('shapes', ())]
            pairs += [q + '|K' + unit['kind'] for q in distinct]
            pairs += ['K' + unit['kind'] + '|' + w for w in ordered]
            instruction = unit.get('source') == 'instructions'
            if instruction:
                pairs += [q + '|SRC' for q in distinct] + ['SRC|' + w for w in ordered]
            dense.append(1.0 if instruction else 0.0)
            table.append({'unit': i, 'gain': gains.get(i, 0.0), 'dense': dense, 'pairs': pairs})
        return table

    def _pair_weights(self, model) -> dict:
        """The learned pair weights as one dictionary.  They are stored grouped by the
        word of the question, ``{head: 'tail:w;tail:w'}``, to keep the file small."""
        stored = model['pairs']
        cache = getattr(self, '_pair_cache', None)
        if cache is None or cache[0] is not stored:
            flat = {}
            for head, row in stored.items():
                if isinstance(row, str):
                    for item in row.split(';'):
                        tail, weight = item.rsplit(':', 1)
                        flat[head + '|' + tail] = float(weight)
                else:
                    flat[head] = row
            cache = (stored, flat)
            self._pair_cache = cache
        return cache[1]

    def _rank_by_model(self, model, terms, question, base, gains, how, asked, previous=None):
        table = self._candidate_table(terms, question, base, gains, how, asked, previous)
        asked_for = how.get(None, {})
        if not table:
            ranked = {'unit': None, 'score': base, 'margin': 0.0, 'unaddressed': max(asked_for.values(), default=0.0),
                      'cell': cell_key(1.0, 0.0), 'explained': {}, 'covered': 0.0, 'asked': asked, 'candidates': 0}
            ranked['features'] = self._features(ranked, question)
            ranked['useful'] = 0.0
            return ranked
        pairs, scale = self._pair_weights(model), model['pair_scale']
        best = None
        for candidate in table:
            z = model['bias'] + sum(w * (x - m) / s for x, m, s, w in
                                    zip(candidate['dense'], model['mean'], model['scale'], model['weights']))
            z += scale * sum(pairs.get(key, 0.0) for key in candidate['pairs'])
            candidate['z'] = z
            if best is None or z > best['z']:
                best = candidate
        top = best['unit']
        explained = how.get(top, {})
        runner = sorted((g for i, g in gains.items() if i != top and self.context_units[i]['kind'] != 'heading'),
                        reverse=True)[:1]
        unaddressed = max((pi for q, pi in asked_for.items() if q not in explained), default=0.0)
        mass = sum(asked_for.values())
        covered = sum(pi for q, pi in asked_for.items() if q in explained) / mass if mass else 0.0
        ranked = {'unit': top, 'score': best['gain'] + base, 'margin': best['gain'] - (runner[0] if runner else 0.0),
                  'unaddressed': unaddressed, 'cell': cell_key(unaddressed, best['gain'] - (runner[0] if runner else 0.0)),
                  'explained': explained, 'covered': covered, 'asked': asked, 'raw': best['z'],
                  'candidates': len(table)}
        ranked['features'] = self._features(ranked, question)

        curve = model.get('calibration_instructions') if self.context_units[top].get('source') == 'instructions' else None
        curve = curve or model['calibration']

        def calibrated(z):
            rate = curve[0][1]
            for low, block_rate, _ in curve:
                if z >= low:
                    rate = block_rate
            return rate
        ranked['useful'] = calibrated(best['z'])
        ranked['alternatives'] = [(c['unit'], calibrated(c['z'])) for c in
                                  sorted(table, key=lambda c: -c['z']) if c['unit'] != top][:2]
        return ranked

    def _features(self, ranked: dict, question: str) -> dict:
        """G-60: what is known about a candidate answer, all from layout or
        learned: the calibration cell's two features, whether the question
        carries a learned interrogative or asks yes or no, how often the unit
        holds the class of answer asked for, how much of the question it
        explains, its kind of layout unit and its length."""
        unit = self.context_units[ranked['unit']] if ranked['unit'] is not None else None
        asking = {_plain(w) for w in self.syntax_model.get('interrogatives', ())}
        words = [_plain(w) for w in self.split_words(question) if w[:1].isalnum()] if question else []
        asked = ranked.get('asked')
        return {'u': str(_bin(ranked['unaddressed'], PI_BINS)), 'm': str(_bin(ranked['margin'], MARGIN_BINS)),
                'form': 'wh' if any(w in asking for w in words) else 'sn',
                'cls': 'na' if asked is None or unit is None else
                f"{asked[0]}:{min(unit.get('classes', {}).get(asked[0], 0), 2)}",
                'cov': str(_bin(ranked['covered'], COVER_BINS)),
                'kind': unit['kind'] if unit else 'none',
                'len': str(_bin(len(unit['text'].split()), LENGTH_BINS)) if unit else '0'}

    def _usefulness(self, features: dict):
        """G-60: the counted chance that this candidate is useful: naive Bayes
        over the counted features, turned into a rate by the isotonic table
        counted on cross-fitted scores.  None without a counted model."""
        model = self.context_model.get('confidence')
        if not model or not getattr(self, 'confidence_features', True):
            return None
        n0, n1 = model['prior']
        score = math.log((n1 + 1) / (n0 + 1))
        for name, counts in model['counts'].items():
            c0, c1 = counts.get(features.get(name), (0, 0))
            k = model['values'][name] + 1
            score += math.log((c1 + 1) / (n1 + k)) - math.log((c0 + 1) / (n0 + k))
        rate = model['calibration'][0][1]
        for low, block_rate, _ in model['calibration']:
            if score >= low:
                rate = block_rate
        return rate

    def _active_model(self):
        """G-103: the usefulness model of the candidates, when it is taught and on."""
        model = self.context_model.get('usefulness')
        return model if model and getattr(self, 'candidate_model', True) else None

    def _admitted(self, ranked: dict | None) -> bool:
        if ranked is None:
            return False
        model = self._active_model()
        if model is not None:
            return 'plain_from' in model and ranked['useful'] >= model['plain_from']
        if not getattr(self, 'calibrated', True):
            return True
        return ranked['cell'] in set(self.context_model.get('admitted', ()))

    def _level(self, ranked: dict | None) -> str:
        """G-58: what the counted reliability of this cell allows: a plain
        answer, the closest text with a warning, or not knowing."""
        if self._admitted(ranked):
            return 'answered'
        if ranked is None or not getattr(self, 'closest', True):
            return 'unknown'
        if ranked.get('useful') is not None:
            # G-60: quoted only where it is counted useful often enough.
            source = self._active_model() or self.context_model['confidence']
            cite_from = source.get('cite_from', CITE_FROM)
            return 'closest' if ranked['useful'] >= cite_from else 'unknown'
        return 'closest' if ranked['cell'] in set(self.context_model.get('closest', ())) else 'unknown'

    def _shown(self, ranked: dict) -> str:
        return self.context_units[ranked['unit']]['text']

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
        # G-58: only a short turn without figures is given back; anything
        # longer, or with figures, may carry a person's data and is never echoed.
        if getattr(self, 'short_echo', True) and (len(text.split()) > ECHO_WORDS or any(c.isdigit() for c in text)):
            return False
        postings = self._index()
        terms = self.context_terms(text)
        view = self._instruction_view() if self._active_model() is not None else None
        if view is not None and any(t in view._index() for t in terms):
            return False
        return not any(t in postings for t in terms)

    def _question_part(self, question: str) -> tuple[str, str]:
        """A greeting that opens a question is set apart from it."""
        text = str(question).strip()
        cut = text.find('¿')
        if cut > 0 and self._phatic(text[:cut]):
            return text[:cut].strip(' ,.;:'), text[cut:]
        return '', text

    def answer(self, question: str, history=None) -> dict:
        """Answer one turn of a person from the loaded text: plainly when the
        counted reliability allows it, with the closest text and a warning
        when that text is useful at least half of the time, or saying it is
        not known.  ``history`` holds the earlier turns of this person only
        and is part of the interface; G-58r does not use it (the follow-up
        raised misleading citations and was retired).  Nothing of a person is
        kept by the bot.  ``text`` is the only thing to say to the person;
        ``candidate`` is for the integrator and is never shown to a customer."""
        opening, text = self._question_part(question)
        if not text or self._phatic(text):
            said = (opening or text).strip(' ,.;:')
            return {'text': (said[:1].upper() + said[1:] + '.') if said else '', 'status': 'phatic',
                    'evidence': None, 'confidence': None}
        previous = self._previous_topic(history) if self._active_model() is not None else None
        terms = self.context_terms(text)
        ranked = self._rank(terms, text, previous)
        source, units = 'context', self.context_units
        view = self._instruction_view() if self._active_model() is not None else None
        if view is not None:
            # G-105: the best sentence of the instructions competes with the best unit of the text.
            other = view._rank(terms, text)
            if other is not None and other.get('unit') is not None and (
                    ranked is None or ranked.get('unit') is None or other['useful'] > ranked['useful']):
                ranked, source, units = other, 'instructions', self.context_instructions
        level = self._level(ranked)
        prefix = (opening[:1].upper() + opening[1:] + '. ') if opening else ''
        table = self.context_model.get('closest_cells' if level == 'closest' else 'cells', {})
        cells = table.get(ranked['cell']) if ranked else None
        precision = round(cells[1] / cells[0], 4) if cells and cells[0] else None
        if ranked is not None and ranked.get('useful') is not None and level != 'answered':
            precision = round(ranked['useful'], 4)
        if level == 'unknown':
            # Not asserted: the best unit and its counted precision go to the
            # caller apart from the reply, so an integrator can decide.
            candidate = ({'text': units[ranked['unit']]['text'], 'precision': precision, 'source': source}
                         if ranked is not None and ranked['unit'] is not None else None)
            exit_unit = self._fallback_exit()
            text_out = prefix + UNKNOWN_TEXT + (FALLBACK_TEXT.format(exit_unit['text'].rstrip('.')) if exit_unit else '')
            result = {'text': text_out, 'status': 'unknown', 'evidence': None,
                      'confidence': None, 'cell': ranked['cell'] if ranked else None, 'candidate': candidate}
            if exit_unit:
                result['fallback'] = exit_unit['text']
            return result
        unit = units[ranked['unit']]
        shown = unit['text']
        if source == 'instructions':
            return {'text': prefix + INSTRUCTION_TEXT.format(shown.rstrip('.')), 'status': 'instruction',
                    'evidence': {'unit': unit['text'], 'heading': unit['heading'], 'index': ranked['unit'],
                                 'source': 'instructions'},
                    'confidence': precision, 'cell': ranked['cell']}
        reply = shown if level == 'answered' else CLOSEST_TEXT.format(shown.rstrip('.'))
        return {'text': prefix + reply, 'status': level,
                'evidence': {'unit': unit['text'], 'heading': unit['heading'], 'index': ranked['unit']},
                'confidence': precision, 'cell': ranked['cell']}

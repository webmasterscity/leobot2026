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
ECHO_WORDS = 4


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
            own = sorted(set(self.context_terms(display)))
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
                          'terms': own, 'inherited': inherited, 'classes': self._classes(display)})

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
        return {'status': 'context_loaded', 'units': len(self.context_units),
                'instructions': len(self.context_instructions)}

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
        return self._context_index

    # ----- retrieval ----------------------------------------------------
    def _rank(self, terms: list[str], question: str = '') -> dict | None:
        """The best unit for these question words and its calibration cell."""
        units = self.context_units
        if not units:
            return None
        postings, total = self._index(), len(units)
        bridge = self._bridge() if getattr(self, 'bridge', True) else {}
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

    def _admitted(self, ranked: dict | None) -> bool:
        if ranked is None:
            return False
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
            cite_from = self.context_model['confidence'].get('cite_from', CITE_FROM)
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
        return not any(t in postings for t in self.context_terms(text))

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
        ranked = self._rank(self.context_terms(text), text)
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
            candidate = ({'text': self._shown(ranked), 'precision': precision}
                         if ranked is not None and ranked['unit'] is not None else None)
            return {'text': prefix + UNKNOWN_TEXT, 'status': 'unknown', 'evidence': None,
                    'confidence': None, 'cell': ranked['cell'] if ranked else None, 'candidate': candidate}
        unit = self.context_units[ranked['unit']]
        shown = self._shown(ranked)
        reply = shown if level == 'answered' else CLOSEST_TEXT.format(shown.rstrip('.'))
        return {'text': prefix + reply, 'status': level,
                'evidence': {'unit': unit['text'], 'heading': unit['heading'], 'index': ranked['unit']},
                'confidence': precision, 'cell': ranked['cell']}

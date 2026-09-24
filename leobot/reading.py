"""G-28: literal utterance memory and question answering learned by alignment.

Every declarative sentence read from a document is kept verbatim with its
source.  A question that no learned construction interprets is aligned with the
stored utterances; the answer is a span of the best aligned utterance, chosen by
feature statistics learned from worked examples of *other* texts (text,
question, answer).  Nothing here lists words of any language: the tokens that
mark the gap of a question, token weights and span preferences are counted from
experience.  Answers are reported as what the text says (``literal``), with the
utterance and its source, never as verified facts.
"""
from __future__ import annotations

import math
import re
from collections import deque
import unicodedata

_TOKEN = re.compile(r'\w+|[^\w\s]')
MAX_UTTERANCES = 200_000
MARKER_SUPPORT = 3          # G-28b: a gap marker must have been a key this often
MARKER_ABSENCE = 0.5        # ... and absent from the answering sentence this often
ANCHOR_INSIDE_RATE = 0.05   # below this learned rate, spans with anchors are dropped
MAX_SPAN = 10
STEM = 5
SMOOTHING = 4.0
BM25_K1 = 1.2
BM25_B = 0.75
LEAD_WORDS = 6             # G-45: question words whose presence in the answer sentence is counted
CATEGORY_SUPPORT = 5       # worked examples before a noun can be learned as a category
# G-42: learned word classes that carry grammar rather than content; they do
# not have to be found in the answering sentence and do not anchor it.
FUNCTION_TAGS = frozenset({'DET', 'ADP', 'AUX', 'PRON', 'CCONJ', 'SCONJ', 'PUNCT'})


def _norm(token: str) -> str:
    # Case, accents and inflectional endings are ignored by keeping only the
    # first letters of long words: «ganó», «ganador», «ganaron» align.  This is
    # a length rule, not a list of words, so it applies to any suffixing language.
    decomposed = unicodedata.normalize('NFKD', token.casefold())
    plain = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    return plain[:STEM] if STEM and len(plain) > STEM else plain


def _fold(word: str) -> str:
    decomposed = unicodedata.normalize('NFKD', word.lower())
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


def _is_word(token: str) -> bool:
    return any(ch.isalnum() for ch in token)


def _shape(token: str) -> str:
    if any(ch.isdigit() for ch in token):
        return 'D'
    return 'C' if token[:1].isupper() else 'l'


def _bucket(value: int, edges: tuple[int, ...]) -> str:
    for edge in edges:
        if value <= edge:
            return str(edge)
    return f'{edges[-1]}+'


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def _empty_model() -> dict:
    return {'examples': 0, 'skipped': 0, 'contexts': 0, 'sentence_df': {},
            'sentences': 0, 'question_df': {}, 'question_unmatched': {}, 'questions': 0,
            'features': {}, 'positives': 0, 'negatives': 0,
            'own_overlap': [], 'foreign_overlap': [], 'last_context': [],
            'key_support': {}, 'gold_spans': 0, 'gold_anchor_inside': 0}


class ReadingMemoryMixin:
    """Mixed into Bot; state lives in ``reading_utterances``/``reading_model``."""

    # ----- memory -------------------------------------------------------
    def _reading_index(self) -> dict:
        # G-41: memory only grows by appending (forgetting drops the cache), so
        # new utterances extend the index instead of rebuilding it; a replaced
        # list (another identity) is rebuilt from scratch.
        index = getattr(self, '_reading_index_cache', None)
        rows = self.reading_utterances
        if index is None or len(index) < 5 or index[4] != id(rows) or index[0] > len(rows):
            index = (0, {}, {}, [], id(rows))
        if index[0] != len(rows):
            _, postings, documents, word_sets, _ = index
            for position in range(index[0], len(rows)):
                row = rows[position]
                words = {_norm(t) for t in row['tokens'] if _is_word(t)}
                word_sets.append(words)
                documents.setdefault(row.get('document'), set()).update(words)
                for token in words:
                    postings.setdefault(token, []).append(position)
            index = (len(rows), postings, documents, word_sets, id(rows))
        self._reading_index_cache = index
        return index[1]

    def _reading_documents(self) -> dict:
        self._reading_index()
        return self._reading_index_cache[2]

    def remember_utterances(self, sentences, source: str) -> int:
        stored = 0
        for number, sentence in enumerate(sentences):
            if self._question_like(sentence):
                continue
            tokens = _TOKEN.findall(sentence)
            if not any(_is_word(t) for t in tokens):
                continue
            if len(self.reading_utterances) >= MAX_UTTERANCES:
                break
            self.reading_utterances.append({'source': f'{source}:oración:{number + 1}',
                                            'document': source, 'text': sentence,
                                            'tokens': tokens})
            stored += 1
        return stored

    def forget_utterances(self, source: str) -> int:
        before = len(self.reading_utterances)
        self.reading_utterances = [row for row in self.reading_utterances
                                   if row.get('document') != source]
        self._reading_index_cache = None
        return before - len(self.reading_utterances)

    # ----- learned statistics --------------------------------------------
    def _reading_idf(self, token: str) -> float:
        # A word's weight reflects everything read: the education texts and
        # the utterances now in memory, where a repeated name stops discriminating.
        model = self.reading_model
        cache = getattr(self, '_reading_index_cache', None)
        memory = len(cache[1].get(token, ())) if cache and cache[0] == len(self.reading_utterances) else 0
        sentences = model['sentences'] + (cache[0] if cache else 0)
        return math.log((sentences + 1) / (model['sentence_df'].get(token, 0) + memory + 1))

    def _reading_key(self, unmatched) -> str:
        """The unmatched token that, in learned questions, is most often absent
        from the answering sentence: the learned marker of the question's gap."""
        model = self.reading_model
        df, missing = model['question_df'], model.get('question_unmatched', {})
        def strength(token):
            return ((missing.get(token, 0) + 1) / (df.get(token, 0) + 2), df.get(token, 0), token)
        known = [t for t in unmatched if df.get(t, 0) > 0]
        return max(known, key=strength) if known else '*'

    def _reading_overlap(self, question: list[str], tokens) -> float:
        present = tokens if isinstance(tokens, set) else {_norm(t) for t in tokens}
        total = sum(self._reading_idf(t) for t in question)
        if total <= 0:
            return 0.0
        return sum(self._reading_idf(t) for t in question if t in present) / total

    def _marker_ok(self, token: str) -> bool:
        """A learned gap marker: seen in >= MARKER_SUPPORT questions and absent
        from the answering sentence in >= MARKER_ABSENCE of them."""
        model = self.reading_model
        seen = model['question_df'].get(token, 0)
        if token == '*' or seen < MARKER_SUPPORT:
            return False
        return model.get('question_unmatched', {}).get(token, 0) / seen >= MARKER_ABSENCE

    def _gap_marker(self, question: list[str]) -> str:
        """The question's strongest learned gap marker, or '*' if it has none."""
        model = self.reading_model
        df, missing = model['question_df'], model.get('question_unmatched', {})
        markers = [t for t in set(question) if self._marker_ok(t)]
        if not markers:
            return '*'
        return max(markers, key=lambda t: (missing.get(t, 0) / df[t], df[t], t))

    @staticmethod
    def _verbatim(question: list[str], sentence: list[str]) -> bool:
        # A question that only quotes the sentence leaves no gap to fill.
        n = len(question)
        return any(sentence[i:i + n] == question for i in range(len(sentence) - n + 1))

    def consolidate_reading(self) -> dict:
        """Consolidation hook.  G-28b's IBM-1 word correspondences were retired:
        with the preregistered thresholds they learned nothing (G-28b result).
        G-42: the questions read are evidence of which words ask."""
        if self.syntax_model.get('sentences'):
            self._compile_question_words()
            self._compile_category_nouns()
        return {'status': 'reading_consolidated', 'words': 0, 'pairs': 0}

    def _gap_neighbours(self, question: list[str], key: str, present: set) -> tuple:
        """Question words right before and after the gap marker that the
        sentence also contains; their positions locate the gap in the sentence."""
        if key not in question:
            return None, None
        at = question.index(key)
        before = next((t for t in reversed(question[:at]) if t in present), None)
        after = next((t for t in question[at + 1:] if t in present), None)
        return before, after

    def _span_features(self, tokens, start, end, anchors, qtokens, gap=(None, None),
                       normalized=None) -> list[tuple]:
        normalized = normalized or [_norm(t) for t in tokens]
        span = tokens[start:end]
        before = normalized[start - 1] if start > 0 else '<s>'
        after = normalized[end] if end < len(tokens) else '</s>'
        outside = [p for p in anchors if p < start or p >= end]
        if outside:
            nearest = min(outside, key=lambda p: (start - p if p < start else p - end + 1, p))
            side, distance = ('R', start - nearest) if nearest < start else ('L', nearest - end + 1)
        else:
            side, distance = 'N', 0
        boundary_left = start == 0 or not _is_word(tokens[start - 1]) or (start - 1) in anchors
        boundary_right = end == len(tokens) or not _is_word(tokens[end]) or end in anchors
        inside = sum(1 for i in range(start, end) if i in anchors)
        features = [('shape', _shape(span[0]), _shape(span[-1]), _bucket(len(span), (1, 2, 3, 5))),
                    ('position', side, _bucket(distance, (0, 1, 2, 3, 5, 9))),
                    ('before', before), ('after', after),
                    ('first', normalized[start]), ('last', normalized[end - 1]),
                    ('run', boundary_left, boundary_right),
                    ('question_inside', _bucket(inside, (0, 1)))]
        for name, word in (('gap_before', gap[0]), ('gap_after', gap[1])):
            if word is None:
                features.append((name, 'none')); continue
            places = [i for i, t in enumerate(normalized) if t == word and not start <= i < end]
            if not places:
                features.append((name, 'inside')); continue
            if name == 'gap_before':
                offsets = [start - i for i in places]
            else:
                offsets = [i - end + 1 for i in places]
            offset = min(offsets, key=lambda d: (abs(d), d))
            features.append((name, 'neg' if offset <= 0 else _bucket(offset, (1, 2, 3, 5, 9))))
        return features

    def _candidate_spans(self, tokens):
        for start in range(len(tokens)):
            if not _is_word(tokens[start]):
                continue
            for end in range(start + 1, min(len(tokens), start + MAX_SPAN) + 1):
                if not _is_word(tokens[end - 1]):
                    break
                yield start, end

    def _anchors(self, tokens, qtokens) -> list[int]:
        weights = [self._reading_idf(_norm(t)) for t in tokens if _is_word(t)]
        floor = sum(weights) / len(weights) if weights else 0.0
        return [i for i, t in enumerate(tokens)
                if _is_word(t) and _norm(t) in qtokens and self._reading_idf(_norm(t)) >= floor]

    def observe_reading_example(self, context: str, question: str, answer: str) -> dict:
        """Learn from one worked demonstration; the text itself is not memorized."""
        model = self.reading_model
        sentences = self._document_sentences(context)
        tokenized = [_TOKEN.findall(s) for s in sentences]
        for tokens in tokenized:
            model['sentences'] += 1
            for token in {_norm(t) for t in tokens if _is_word(t)}:
                model['sentence_df'][token] = model['sentence_df'].get(token, 0) + 1
        model['contexts'] += 1
        self._observe_opener(_TOKEN.findall(question), True)
        qtokens = [_norm(t) for t in _TOKEN.findall(question) if _is_word(t)]
        target = [_norm(t) for t in _TOKEN.findall(answer) if _is_word(t)]
        # Calibration: how much of a question a foreign text covers by chance.
        own = max((self._reading_overlap(qtokens, t) for t in tokenized), default=0.0)
        foreign = max((self._reading_overlap(qtokens, t) for t in model['last_context']), default=None)
        model['last_context'] = tokenized
        found = None
        for tokens in tokenized:
            words = [(i, _norm(t)) for i, t in enumerate(tokens) if _is_word(t)]
            for k in range(len(words) - len(target) + 1):
                if target and [w for _, w in words[k:k + len(target)]] == target:
                    found = (tokens, words[k][0], words[k + len(target) - 1][0] + 1)
                    break
            if found:
                break
        key = self._gap_marker(qtokens)
        for token in set(qtokens):
            model['question_df'][token] = model['question_df'].get(token, 0) + 1
        model['questions'] += 1
        if found is None or not qtokens:
            model['skipped'] += 1
            return {'status': 'reading_example_skipped', 'reason': 'answer_not_in_one_sentence'}
        for name, value in (('own_overlap', own), ('foreign_overlap', foreign)):
            if value is not None:
                model[name].append(round(value, 4))
                del model[name][:-5000]
        tokens, gold_start, gold_end = found
        present = {_norm(t) for t in tokens}
        # G-45: which of the question's first words the answering sentence repeats.
        lead = [t.lower() for t in _TOKEN.findall(question) if _is_word(t)][:LEAD_WORDS]
        table = model.setdefault('lead_presence', {})
        presence = ' '.join(lead) + '\x1e' + ''.join('1' if _norm(w) in present else '0' for w in lead)
        table[presence] = table.get(presence, 0) + 1
        qset = set(qtokens)
        missing = model.setdefault('question_unmatched', {})
        for token in qset - present:
            missing[token] = missing.get(token, 0) + 1
        anchors = set(self._anchors(tokens, qset))
        gap = self._gap_neighbours(qtokens, key, present)
        normalized = [_norm(t) for t in tokens]
        support = model.setdefault('key_support', {})
        support[key] = support.get(key, 0) + 1
        model['gold_spans'] = model.get('gold_spans', 0) + 1
        model['gold_anchor_inside'] = model.get('gold_anchor_inside', 0) + int(
            any(i in anchors for i in range(gold_start, gold_end)))
        features = model['features']
        for start, end in self._candidate_spans(tokens):
            positive = (start, end) == (gold_start, gold_end)
            for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized):
                for scope in (key, '*'):
                    name = '\x1f'.join(map(str, (scope,) + feature))
                    counts = features.setdefault(name, [0, 0])
                    counts[0 if positive else 1] += 1
            model['positives' if positive else 'negatives'] += 1
        model['examples'] += 1
        self._reading_threshold_cache = None
        return {'status': 'reading_example_learned', 'key': key}

    def _reading_threshold(self) -> float:
        cached = getattr(self, '_reading_threshold_cache', None)
        if cached is None:
            foreign = sorted(self.reading_model['foreign_overlap'])
            # Answer only above what 95 % of foreign texts reach by chance.
            cached = foreign[min(len(foreign) - 1, math.ceil(0.95 * len(foreign)) - 1)] if foreign else 1.0
            self._reading_threshold_cache = cached
        return cached

    def _feature_score(self, scope: str, feature: tuple, prior: float) -> float:
        features = self.reading_model['features']
        general = features.get('\x1f'.join(map(str, ('*',) + feature)), (0, 0))
        rate = (general[0] + SMOOTHING * prior) / (general[0] + general[1] + SMOOTHING)
        if scope != '*':
            local = features.get('\x1f'.join(map(str, (scope,) + feature)), (0, 0))
            rate = (local[0] + SMOOTHING * rate) / (local[0] + local[1] + SMOOTHING)
        return _logit(rate) - _logit(prior)

    # ----- answering -----------------------------------------------------
    def verify_from_utterances(self, question: str) -> dict:
        """G-41: a yes/no question checked against what was said or read.

        An utterance supports it when it contains every stem of the question
        other than the learned negators; its answer is «sí» with the question's
        polarity (parity of learned negators) and «no» with the opposite one.
        Both polarities supported: contradiction; none: «no lo sé».
        G-43: with learned syntax the support must also hold in structure (who
        does what) and not be subordinate (what someone said or supposed)."""
        negators = set(self.syntax_model.get('negators', ()))
        words = [t.lower() for t in _TOKEN.findall(question) if _is_word(t)]
        polarity = sum(w in negators for w in words) % 2
        content = {_norm(w) for w in words if w not in negators}
        supports: dict[int, list[str]] = {0: [], 1: []}
        reported: list[str] = []
        structure = None
        if getattr(self, 'structural_verification', True) and self.syntax_model.get('sentences'):
            structure = self._question_links(question, negators)
        if content and self.reading_utterances:
            index = self._reading_index()
            lists = sorted((index.get(t, ()) for t in content), key=len)
            candidates = set(lists[0]).intersection(*lists[1:]) if lists else set()
            for position in sorted(candidates):
                row = self.reading_utterances[position]
                if structure is not None:
                    held = self._links_hold(structure, row['text'])
                    if held is None:
                        continue
                    if held == 'subordinate':
                        reported.append(row['source'])
                        continue
                said = [t.lower() for t in row['tokens'] if _is_word(t)]
                supports[sum(w in negators for w in said) % 2].append(row['source'])
        same, opposite = supports[polarity], supports[1 - polarity]
        if same and opposite:
            return {'text': 'No lo sé: lo que me dijeron se contradice.', 'status': 'literal_contradiction',
                    'evidence': same + opposite}
        if same:
            return {'text': 'Sí, según lo que me dijeron.', 'status': 'literal_yes', 'evidence': same}
        if opposite:
            return {'text': 'No, según lo que me dijeron.', 'status': 'literal_no', 'evidence': opposite}
        if reported:
            return {'text': 'No lo sé con seguridad: lo que me dijeron lo presenta como algo dicho o supuesto, '
                            'no como un hecho.', 'status': 'literal_reported', 'evidence': reported}
        return {'text': 'No lo sé: no tengo esa información.', 'status': 'literal_unknown', 'evidence': []}

    @staticmethod
    def _enhanced(heads, labels):
        """G-43: each coordinated element hangs from the head of the first
        element of its coordination, with its function (the enhanced Universal
        Dependencies convention); returns the new heads and functions."""
        new_heads, new_labels = list(heads), list(labels)
        for d in range(len(heads)):
            first, seen = d, set()
            while labels[first] == 'conj' and heads[first] and first not in seen:
                seen.add(first)
                first = heads[first] - 1
            if first != d:
                new_heads[d], new_labels[d] = heads[first], labels[first]
        return new_heads, new_labels

    def _graph(self, heads, labels):
        """Undirected links of the enhanced tree, plus the subject a coordinated
        predicate shares with the first one (G-43)."""
        enhanced, _ = self._enhanced(heads, labels)
        links = [set() for _ in heads]
        for d, h in enumerate(enhanced):
            if h:
                links[d].add(h - 1); links[h - 1].add(d)
        for d, h in enumerate(heads):
            if labels[d] == 'conj' and h and not any(heads[k] == d + 1 and str(labels[k]).startswith('nsubj')
                                                     for k in range(len(heads))):
                for k in range(len(heads)):
                    if heads[k] == h and str(labels[k]).startswith('nsubj'):
                        links[d].add(k); links[k].add(d)
        return enhanced, links

    def _question_links(self, question: str, negators: set):
        """Links between the content words of a yes/no question: each one with
        its nearest content ancestor and the number of steps between them."""
        tree = self._utterance_tree(question)
        if tree is None:
            return None
        words, tags, heads, labels = tree
        enhanced, _ = self._enhanced(heads, labels)
        content = {i for i, (w, t) in enumerate(zip(words, tags))
                   if t not in FUNCTION_TAGS and _is_word(w) and w.lower() not in negators}
        links = []
        for i in sorted(content):
            node = enhanced[i] - 1
            while node >= 0 and node not in content:
                node = enhanced[node] - 1
            if node >= 0:
                # One content step: function words in between are transparent.
                links.append((self._word_key(words[i]), self._word_key(words[node]), 1))
        return {'stems': {self._word_key(words[i]) for i in content}, 'links': links}

    def _links_hold(self, structure, text: str):
        """None if the sentence does not state the question's links; 'subordinate'
        if it does but inside a subordinate clause; 'asserted' otherwise."""
        tree = self._utterance_tree(text)
        if tree is None:
            return None
        words, tags, heads, labels = tree
        stems = [self._word_key(w) for w in words]
        places: dict = {}
        for j, w in enumerate(words):
            if _is_word(w) and stems[j] in structure['stems']:
                places.setdefault(stems[j], []).append(j)
        if set(places) != structure['stems']:
            return None
        aligned = {j for js in places.values() for j in js}
        enhanced, graph = self._graph(heads, labels)
        weight = [0 if t in FUNCTION_TAGS else 1 for t in tags]
        for a, b, steps in structure['links']:
            reached = False
            for start in places[a]:
                # Only content words count as steps (G-43); other question
                # words may not stand in between.
                far, queue = {start: 0}, deque([start])
                while queue and not reached:
                    node = queue.popleft()
                    for other in graph[node]:
                        cost = far[node] + weight[other]
                        if cost > steps + 1 or far.get(other, cost + 1) <= cost:
                            continue
                        far[other] = cost
                        if other in places[b]:
                            reached = True
                            break
                        if other not in aligned:
                            (queue.appendleft if weight[other] == 0 else queue.append)(other)
                if reached:
                    break
            if not reached:
                return None
        depth = lambda j: len(self._ancestors(enhanced, j))
        top = min(sorted(aligned), key=depth)
        for node in [top] + self._ancestors(enhanced, top):
            if any(heads[k] == node + 1 and tags[k] == 'SCONJ' for k in range(len(heads))):
                return 'subordinate'
        return 'asserted'

    @staticmethod
    def _ancestors(heads, node: int) -> list[int]:
        out, seen = [], {node}
        while heads[node] and heads[node] - 1 not in seen:
            node = heads[node] - 1
            out.append(node); seen.add(node)
        return out

    def _utterance_tree(self, text: str):
        """Syntactic words, tags, heads and functions of a remembered sentence,
        analysed the first time a question needs it and kept (G-42)."""
        cache = self.__dict__.setdefault('_utterance_trees', {})
        tree = cache.get(text)
        if tree is None:
            words = self.split_words(text)
            parse = self.parse_words(words)
            if not parse or parse.get('status') != 'parsed_syntax':
                tree = False
            else:
                tree = (words, parse['tags'], parse['heads'], parse.get('labels') or [None] * len(words))
            cache[text] = tree
        return tree or None

    @staticmethod
    def _tree_distances(heads, start: int, tags=None) -> list[int]:
        """Steps between ``start`` and every word of a tree (heads 1-based, 0
        root).  G-43: with tags, only content words count as steps; function
        words are transparent, so an article or a copula wrongly chosen as a
        head does not lengthen the way."""
        n = len(heads)
        links = [[] for _ in range(n)]
        for d, h in enumerate(heads):
            if h:
                links[d].append(h - 1); links[h - 1].append(d)
        step = [0 if tags is not None and tags[i] in FUNCTION_TAGS else 1 for i in range(n)]
        far = [-1] * n
        far[start] = 0
        frontier = [start]
        while frontier:
            nxt = []
            for node in frontier:
                for other in links[node]:
                    if far[other] < 0:
                        far[other] = far[node] + step[other]; nxt.append(other)
            frontier = nxt
        return [d if d >= 0 else n for d in far]

    def _reader_span_score(self, question: str, row: dict, text: str):
        """The G-28 reader's learned score for one given span of a sentence,
        or None when the span cannot be located or nothing was learned."""
        model = self.reading_model
        if not model.get('examples'):
            return None
        tokens = row['tokens']
        normalized = [_norm(t) for t in tokens]
        target = [_norm(t) for t in _TOKEN.findall(text) if _is_word(t)]
        words = [(i, w) for i, (t, w) in enumerate(zip(tokens, normalized)) if _is_word(t)]
        found = next(((words[k][0], words[k + len(target) - 1][0] + 1) for k in range(len(words) - len(target) + 1)
                      if target and [w for _, w in words[k:k + len(target)]] == target), None)
        if found is None:
            return None
        qtokens = [_norm(t) for t in _TOKEN.findall(question) if _is_word(t)]
        qset = set(qtokens)
        key = self._gap_marker(qtokens)
        anchors = set(self._anchors(tokens, qset))
        gap = self._gap_neighbours(qtokens, key, set(normalized))
        prior = model['positives'] / max(1, model['positives'] + model['negatives'])
        return round(sum(self._feature_score(key, f, prior)
                         for f in self._span_features(tokens, found[0], found[1], anchors, qset, gap, normalized)), 9)

    def _majority_tag(self, word: str) -> str | None:
        lexicon = self.syntax_model['lexicon']
        counts = {t: lexicon.get(word + '\x1f' + t, 0) + lexicon.get(word.capitalize() + '\x1f' + t, 0)
                  for t in self._tag_list()}
        return max(sorted(counts), key=lambda t: counts[t]) if sum(counts.values()) else None

    def _compile_category_nouns(self) -> None:
        """G-45: a noun after an interrogative names a category («color»,
        «tipo») when the answering sentence leaves it out in at least half of
        at least CATEGORY_SUPPORT worked examples."""
        counts: dict = {}
        for key, n in sorted(self.reading_model.get('lead_presence', {}).items()):
            lead, bits = key.split('\x1e')
            words = lead.split()
            q = self.asking_word(words)
            if q is None or q + 1 >= len(words) or self._majority_tag(words[q + 1]) != 'NOUN':
                continue
            row = counts.setdefault(self.lemma_key(words[q + 1]), [0, 0])
            row[0] += n
            row[1] += n * (bits[q + 1] == '0')
        self.reading_model['category_nouns'] = sorted(k for k, (n, absent) in counts.items()
                                                      if n >= CATEGORY_SUPPORT and absent >= 0.5 * n)

    def _word_key(self, word: str) -> str:
        """How two words are matched when aligning: by learned dictionary form
        (G-44b), or by the 5-letter stem when that is switched off."""
        return self.lemma_key(word) if getattr(self, 'lemma_alignment', True) else _norm(word)

    def asking_word(self, words, tags=None) -> int | None:
        """Position of the word that asks: a learned interrogative, or (G-44)
        the first word after the prepositions that matches one without
        accents, the position from which interrogatives were learned."""
        interrogatives = set(self.syntax_model.get('interrogatives', ()))
        if not interrogatives:
            return None
        low = [w.lower() for w in words]
        for i, w in enumerate(low):
            if w in interrogatives:
                return i
        if not getattr(self, 'folded_openers', True):
            return None
        folded = {_fold(w): w for w in interrogatives}
        for i, w in enumerate(low):
            if not _is_word(w) or (tags is not None and tags[i] == 'ADP') or (tags is None and self._preposition(w)):
                continue
            return i if _fold(w) in folded else None
        return None

    def _preposition(self, word: str) -> bool:
        """Whether a word's most frequent learned tag is a preposition."""
        lexicon = self.syntax_model['lexicon']
        counts = {t: lexicon.get(word + '\x1f' + t, 0) + lexicon.get(word.capitalize() + '\x1f' + t, 0)
                  for t in self._tag_list()}
        return sum(counts.values()) > 0 and max(sorted(counts), key=lambda t: counts[t]) == 'ADP'

    def answer_by_structure(self, question: str) -> dict | None:
        """G-42: an open question is a sentence with a gap.  A remembered
        sentence that contains every content word of the question answers it
        with the part that sits where the question's interrogative sits: a
        largest subtree without question words, in the sentence that aligns
        most question words, placed at the same tree distances from the shared
        words.  G-43: distances are taken from the head of the interrogative
        phrase in enhanced trees (coordinated elements share their head) and
        count content words only; a coordinated element answers only with its
        coordination; the G-28 reader's statistics separate the ties left.
        G-44b: words align by learned dictionary form.  Ties that remain are reported as ambiguity instead of
        chosen silently.  None when no sentence contains every content word
        (the G-28 reader then decides)."""
        if not self.syntax_model.get('interrogatives') or not self.reading_utterances:
            return None
        qtree = self._utterance_tree(question)
        if qtree is None:
            return None
        words, tags, heads, labels = qtree
        low = [w.lower() for w in words]
        q = self.asking_word(words, tags)
        if q is None:
            return None
        # «qué color», «cuántas vacas»: the noun right after the interrogative.
        noun = q + 1 if q + 1 < len(words) and tags[q + 1] == 'NOUN' else None
        phrase = {q} | ({noun} if noun is not None else set())
        first = min(phrase)
        case = low[first - 1] if first > 0 and tags[first - 1] == 'ADP' else None
        interrogatives = set(self.syntax_model.get('interrogatives', ()))
        where: dict = {}
        for i, (w, t) in enumerate(zip(words, tags)):
            if i not in phrase and t not in FUNCTION_TAGS and _is_word(w) and low[i] not in interrogatives:
                where.setdefault(self._word_key(w), i)
        noun_key = self._word_key(words[noun]) if noun is not None else None
        categories = set(self.reading_model.get('category_nouns', ()))
        required = set(where)
        if not required:
            return None
        retrieval = {_norm(words[i]) for i in where.values()}
        index = self._reading_index()
        lists = sorted((index.get(t, ()) for t in retrieval), key=len)
        positions = set(lists[0]).intersection(*lists[1:])
        qheads, _ = self._enhanced(heads, labels)
        qdist = self._tree_distances(qheads, noun if noun is not None else q, tags)
        ranked = []
        for position in sorted(positions):
            row = self.reading_utterances[position]
            tree = self._utterance_tree(row['text'])
            if tree is None:
                continue
            swords, stags, sheads, slabels = tree
            keys = [self._word_key(w) for w in swords]
            aligned = {j for j, w in enumerate(swords)
                       if _is_word(w) and (keys[j] in where or keys[j] == noun_key)}
            if not required <= {keys[j] for j in aligned}:
                continue
            n = len(swords)
            children = [[] for _ in range(n)]
            for d, h in enumerate(sheads):
                if h:
                    children[h - 1].append(d)
            covered = [False] * n

            def mark(node):
                inside = node in aligned
                for child in children[node]:
                    inside = mark(child) or inside
                covered[node] = inside
                return inside
            for root in (d for d, h in enumerate(sheads) if not h):
                mark(root)
            enhanced, _ = self._enhanced(sheads, slabels)
            host = next((j for j in aligned if keys[j] == noun_key), None)
            coverage = len({keys[j] for j in aligned})
            for node in range(n):
                if covered[node] or slabels[node] == 'conj':
                    continue
                parent = sheads[node] - 1
                if parent >= 0 and not covered[parent]:
                    continue
                if host is not None and host not in self._ancestors(enhanced, node):
                    continue
                if (host is None and noun is not None and stags[node] == 'NOUN' and keys[node] != noun_key
                        and getattr(self, 'noun_clash', True) and noun_key not in categories):
                    continue        # G-45: another noun speaks of another thing
                span, stack = [], [node]
                while stack:
                    k = stack.pop(); span.append(k); stack.extend(children[k])
                if all(stags[k] in FUNCTION_TAGS or not _is_word(swords[k]) for k in span):
                    continue
                sdist = self._tree_distances(enhanced, node, stags)
                mirror = sum(abs(qdist[where[keys[j]]] - sdist[j]) for j in aligned if keys[j] in where)
                a, b = min(span), max(span)
                while a <= b and not _is_word(swords[a]):
                    a += 1
                while b >= a and not _is_word(swords[b]):
                    b -= 1
                own_case = swords[a].lower() if stags[a] == 'ADP' else None
                ranked.append(((-coverage, mirror, own_case != case, slabels[node] != labels[q]),
                               ' '.join(swords[a:b + 1]), row))
        if not ranked:
            return None
        best = min(key for key, _, _ in ranked)
        winners = {}
        for key, text, row in ranked:
            if key == best:
                winners.setdefault(' '.join(_norm(t) for t in text.split()), (text, row))
        if len(winners) > 1:
            # G-43: structure narrows the options; the reader's learned statistics decide among them.
            scores = {name: self._reader_span_score(question, row, text) for name, (text, row) in winners.items()}
            top = max((v for v in scores.values() if v is not None), default=None)
            if top is not None and sum(v == top for v in scores.values()) == 1:
                winners = {name: winners[name] for name, v in scores.items() if v == top}
        if len(winners) > 1:
            return {'text': 'No lo sé con seguridad: lo que me dijeron admite más de una respuesta.',
                    'status': 'literal_ambiguous', 'candidates': len(winners)}
        text, row = next(iter(winners.values()))
        return {'text': text, 'status': 'literal',
                'explanation': f'Según lo que me dijeron ({row["source"]}): «{row["text"]}».',
                'evidence': {'source': row['source'], 'utterance': row['text'], 'structural': True}}

    def answer_from_utterances(self, question: str, use_model: bool = True,
                               use_correspondences: bool = True, documents_only: bool = False) -> dict | None:
        """Answer from literal memory, or return None to keep the old behaviour.
        G-45: with ``documents_only`` the reader looks only at documents read,
        not at what was said in conversation: it was educated on questions that
        always have an answer in their text, which holds when asking about a
        document and not about a conversation."""
        model = self.reading_model
        if not self.reading_utterances or model['examples'] == 0:
            return None
        # ``use_correspondences`` is kept only for the frozen G-28b evaluator;
        # the correspondences it switched were retired.
        qtokens = [_norm(t) for t in _TOKEN.findall(question) if _is_word(t)]
        if not qtokens:
            return None
        index = self._reading_index()
        candidates = sorted({p for t in set(qtokens) for p in index.get(t, ())})
        if documents_only:
            candidates = [p for p in candidates
                          if not str(self.reading_utterances[p].get('document', '')).startswith('conversación')]
        word_sets = self._reading_index_cache[3]
        literal = {p: self._reading_overlap(qtokens, word_sets[p]) for p in candidates}
        scored = [(literal[p], p) for p in candidates]
        if not scored:
            return self._reading_abstain(0.0)
        # Locate the passage first, as a reader does: the document that best
        # covers the question, then its best-covering sentence.  (Letting the best span break near ties was tried on the
        # visible development split and lowered joint-memory F1; not kept.)
        # Passage score: BM25 with its usual constants (Robertson and Walker,
        # 1994), so a long passage does not win by covering words by chance.
        documents = self._reading_documents()
        average = sum(len(words) for words in documents.values()) / max(1, len(documents))
        unique = set(qtokens)
        cover: dict = {}
        by_document: dict = {}
        for overlap, position in scored:
            name = self.reading_utterances[position].get('document')
            if name not in cover:
                words = documents.get(name, set())
                norm = BM25_K1 * (1 - BM25_B + BM25_B * len(words) / max(1.0, average))
                cover[name] = sum(self._reading_idf(t) * (BM25_K1 + 1) / (1 + norm)
                                  for t in unique if t in words)
            by_document.setdefault(name, []).append((overlap, position))
        top = max(cover.values())
        best = []
        for name in sorted((n for n in cover if cover[n] == top), key=str):
            local = max(o for o, _ in by_document[name])
            best.extend(p for o, p in by_document[name] if o == local)
        overlaps = literal
        threshold = self._reading_threshold()
        best_overlap = max(overlaps[p] for p in best)
        best = sorted(p for p in best if overlaps[p] >= threshold)
        if not best:
            return self._reading_abstain(best_overlap)
        drop_anchored = (model.get('gold_spans', 0) > 0 and
                         model.get('gold_anchor_inside', 0) / model['gold_spans'] < ANCHOR_INSIDE_RATE)
        no_gap = False
        qset = set(qtokens)
        prior = model['positives'] / max(1, model['positives'] + model['negatives'])
        choices = []
        for position in best:
            tokens = self.reading_utterances[position]['tokens']
            present = {_norm(t) for t in tokens}
            key = self._gap_marker(qtokens)
            if key == '*' or self._verbatim(qtokens, [_norm(t) for t in tokens if _is_word(t)]):
                # No learned gap marker (e.g. yes/no) or a mere quotation: a span cannot answer.
                no_gap = True
                continue
            anchors = set(self._anchors(tokens, qset))
            gap = self._gap_neighbours(qtokens, key, present)
            normalized = [_norm(t) for t in tokens]
            memo: dict = {}
            for start, end in self._candidate_spans(tokens):
                if drop_anchored and any(i in anchors for i in range(start, end)):
                    continue
                if use_model:
                    score = 0.0
                    for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized):
                        value = memo.get(feature)
                        if value is None:
                            value = memo[feature] = self._feature_score(key, feature, prior)
                        score += value
                else:
                    score = self._nearest_run_score(tokens, start, end, anchors, qset)
                    if score is None:
                        continue
                choices.append((score, position, start, end))
        if not choices:
            result = self._reading_abstain(best_overlap)
            if no_gap:
                result['reason'] = 'no_gap_marker'
                result['text'] = ('Esa pregunta no tiene un hueco que un fragmento del texto pueda llenar '
                                  '(por ejemplo, se responde con sí o no); no inventaré una respuesta.')
            return result
        choices.sort(key=lambda row: (-row[0], row[1], row[2], row[3]))
        score, position, start, end = choices[0]
        row = self.reading_utterances[position]
        span = ' '.join(row['tokens'][start:end])
        best_overlap = overlaps[position]
        return {'text': span, 'status': 'literal',
                'explanation': f'Según el texto leído ({row["source"]}): «{row["text"]}».',
                'evidence': {'source': row['source'], 'utterance': row['text'],
                             'span': [start, end], 'overlap': round(best_overlap, 4),
                             'score': round(score, 4)}}

    @staticmethod
    def _nearest_run_score(tokens, start, end, anchors, qset):
        """Ablation: the unaligned run of 1-3 words touching an aligned word."""
        if end - start > 3 or any(_norm(t) in qset for t in tokens[start:end]):
            return None
        if (start - 1) in anchors:
            return 2.0 + (end - start) / 10
        if end in anchors:
            return 1.0 + (end - start) / 10
        return None

    def _reading_abstain(self, overlap: float) -> dict:
        return {'text': 'No encuentro en lo que leí un enunciado que responda esa pregunta; no inventaré una respuesta.',
                'status': 'unknown', 'reason': 'reading_overlap_below_threshold',
                'overlap': round(overlap, 4)}

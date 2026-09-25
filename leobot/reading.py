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

import itertools
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
MAX_PLACEMENTS = 64        # G-47: ways of placing the question's words that are tried
TYPE_SUPPORT = 30          # G-47: worked examples before a never-seen answer class is ruled out
ANSWER_WORDS = 4           # G-47: answer words kept per worked example
KIND_SUPPORT = 30          # G-53: worked answers before a kind of question is checked ...
KIND_SHARE = 0.1           # ... an answer's class needs at least this share of them ...
OPEN_TOKENS = 10           # ... and a word class is open for that kind with this many cases ...
OPEN_RATE = 0.5            # ... if this share of them are words seen once (Good-Turing)
KIND_COMPLEMENTED = 0.5    # G-55: a kind's noun this often completed («qué tipo de…») names no dimension itself
KIND_DOMINANT = 2 / 3      # ... the class is checked only where one class takes this share of the answers
MEMBER_LABELS = frozenset({'amod', 'nmod', 'appos', 'flat', 'nummod', 'compound'})
FORM_SUPPORT = 3           # G-54: a counted reading of a form with this support outweighs rarer ones
CORE_LABELS = frozenset({'nsubj', 'obj', 'iobj', 'ccomp', 'xcomp', 'csubj'})    # G-56: who does what to whom
CLAUSE_EDGES = frozenset({'conj', 'advcl', 'acl', 'ccomp', 'parataxis', 'csubj'})  # G-56: edges between clauses
OPTIONAL_SUPPORT = 30      # G-56: worked questions with a word before it can be learned as optional ...
OPTIONAL_RATE = 0.8        # ... if the answering sentence lacks it this often
# G-42: learned word classes that carry grammar rather than content; they do
# not have to be found in the answering sentence and do not anchor it.
FUNCTION_TAGS = frozenset({'DET', 'ADP', 'AUX', 'PRON', 'CCONJ', 'SCONJ', 'PUNCT'})
LEMMA = '\x1d'             # G-47b: prefix of dictionary forms in the search index


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
                said = [t for t in list(row['tokens']) + list(row.get('referents', ())) if _is_word(t)]
                # G-47b: also every learned dictionary form, so that search uses alignment's keys.
                words = {_norm(t) for t in said} | {LEMMA + k for t in said for k in self.lemma_keys(t)}
                word_sets.append(words)
                documents.setdefault(row.get('document'), set()).update(words)
                for token in words:
                    postings.setdefault(token, []).append(position)
            index = (len(rows), postings, documents, word_sets, id(rows))
        self._reading_index_cache = index
        return index[1]

    def _index_extend(self, position: int, words) -> None:
        """G-47: words a row gained after being indexed (its resolved references)."""
        index = getattr(self, '_reading_index_cache', None)
        if index is None or len(index) < 5 or index[4] != id(self.reading_utterances) or position >= index[0]:
            return
        _, postings, documents, word_sets, _ = index
        new = ({_norm(t) for t in words if _is_word(t)} |
               {LEMMA + k for t in words if _is_word(t) for k in self.lemma_keys(t)}) - word_sets[position]
        for token in sorted(new):
            postings.setdefault(token, []).append(position)
        word_sets[position] |= new
        documents.setdefault(self.reading_utterances[position].get('document'), set()).update(new)

    def _tree_of(self, source):
        """The tree of a remembered row (with resolved references, G-47) or of a text."""
        return self._row_tree(source) if isinstance(source, dict) else self._utterance_tree(source)

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
            self._compile_answer_classes()
            if hasattr(self, '_compile_identity_frames'):
                self._compile_identity_frames()
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
        # G-47: the kind of question and the words of its answer (no text is kept).
        answer_words = [t for t in _TOKEN.findall(answer) if _is_word(t)][:ANSWER_WORDS]
        if answer_words:
            lead = ' '.join(t.lower() for t in _TOKEN.findall(question) if _is_word(t))
            lead = ' '.join(lead.split()[:LEAD_WORDS]) + '\x1e' + ' '.join(answer_words)
            leads = model.setdefault('answer_leads', {})
            leads[lead] = leads.get(lead, 0) + 1
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
        if self.syntax_model.get('sentences') and hasattr(self, '_observe_identity_frame'):
            # G-51: whether this kind of question asks for the same entity said otherwise.
            self._observe_identity_frame(question, sentences[tokenized.index(tokens)], answer)
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
        negators = self.negator_words()
        words = [t.lower() for t in _TOKEN.findall(question) if _is_word(t)]
        polarity = self.negated(sum(w in negators for w in words))
        # G-56: learned optional modifiers nobody said are not asked for.
        qtree = self._utterance_tree(question) if self.syntax_model.get('sentences') else None
        skipped = {qtree[0][i].lower() for i in self._skippable(qtree[0], qtree[1], qtree[3], negators)} \
            if qtree is not None else set()
        content = {self._search_key(w) for w in words if w not in negators and w not in skipped}
        supports: dict[int, list[str]] = {0: [], 1: []}
        reported: list[str] = []
        structure = None
        if getattr(self, 'structural_verification', True) and self.syntax_model.get('sentences'):
            structure = self._question_links(question, negators, skipped)
        if structure is not None:
            self._resolve_references()
        if content and self.reading_utterances:
            index = self._reading_index()
            # G-51: a row where another mention of the same entity is said also counts.
            lists = sorted((set(index.get(t, ())) | set(self._alias_postings(t)) for t in content), key=len)
            candidates = set(lists[0]).intersection(*lists[1:]) if lists else set()
            for position in sorted(candidates):
                row = self.reading_utterances[position]
                if structure is not None:
                    held = self._links_hold(structure, row)
                    if held is None:
                        continue
                    if held == 'subordinate':
                        reported.append(row['source'])
                        continue
                said = [t.lower() for t in row['tokens'] if _is_word(t)]
                supports[self.negated(sum(w in negators for w in said))].append(row['source'])
        same, opposite = supports[polarity], supports[1 - polarity]
        # G-54: the rows behind an answer, for its voice.
        rows_of = lambda sources: [r for r in self.reading_utterances if r['source'] in set(sources)]
        if same and opposite:
            return {'text': self._voiced('contradiction', rows_of(same + opposite))
                    or 'No lo sé: lo que me dijeron se contradice.', 'status': 'literal_contradiction',
                    'evidence': same + opposite}
        if same:
            return {'text': self._voiced('yes', rows_of(same)) or 'Sí, según lo que me dijeron.',
                    'status': 'literal_yes', 'evidence': same}
        if opposite:
            return {'text': self._voiced('no', rows_of(opposite)) or 'No, según lo que me dijeron.',
                    'status': 'literal_no', 'evidence': opposite}
        if reported:
            return {'text': 'No lo sé con seguridad: lo que me dijeron lo presenta como algo dicho o supuesto, '
                            'no como un hecho.', 'status': 'literal_reported', 'evidence': reported}
        if structure is not None and polarity == 0 and getattr(self, 'contrast_answers', True) and self.reading_utterances:
            # G-46: another value of the same attribute was said.
            index = self._reading_index()
            for value in sorted(structure['stems']):
                others = [LEMMA + k if self._lemma_sets() else structure['norms'][k]
                          for k in structure['stems'] if k != value]
                lists = sorted((index.get(t, ()) for t in others), key=len)
                if not lists:
                    continue
                for position in sorted(set(lists[0]).intersection(*lists[1:])):
                    row = self.reading_utterances[position]
                    said = self._contrast(structure, row, negators)
                    if said is None and getattr(self, 'kind_contrast', True):
                        said = self._contrast(structure, row, negators, by_kind=True)
                    if said is not None:
                        return {'text': self._voiced('contrast', [row]) or f'No: según lo que me dijeron, «{row["text"]}»',
                                'status': 'literal_contrast',
                                'evidence': [row['source']], 'said_value': said}
        return {'text': self._voiced('unknown') or 'No lo sé: no tengo esa información.', 'status': 'literal_unknown',
                'evidence': []}

    # ----- the voice of the answer (G-54) -----------------------------------
    def _swapped_form(self, word: str, tag: str, hint: str | None = None):
        """G-54: the word said by the other person: a first person singular
        form becomes second and back, with the same lemma and the other
        features.  The analyses of a form are those counted in the treebanks;
        a verb form never counted is analysed with the learned ending rules,
        keeping only lemmas the treebanks know.  A form of more than one person
        («cantaba») takes the person of its clause (``hint``: its subject or
        clitic), or is not restated.  The new form is the counted one; if it was
        never counted, it is made with the rule of the same lemma ending that
        makes the old form (the verb is regular there: «hice» is not).  A
        pronoun or possessive takes the most frequent form with those features.
        None: the word does not change; False: it should and no form is known."""
        model = self.syntax_model
        low = word.lower()
        verbal = tag in ('VERB', 'AUX')
        classes = (tag,) + tuple(t for t in ('VERB', 'AUX') if verbal and t != tag)
        known = model.get('form_analysis', {})
        rules = model.get('form_rules', {})
        table = model.get('form_table', {})
        readings: dict = {}
        for t in classes:
            for key, count in known.get(low + '\x1f' + t, {}).items():
                readings[(t,) + tuple(key.split('\x1f'))] = count
        if not readings and verbal:
            lemmas = self.__dict__.get('_known_lemmas')
            if lemmas is None or lemmas[0] != len(table):
                lemmas = self.__dict__['_known_lemmas'] = (len(table), {k.split('\x1f')[1] for k in table})
            for slot, bucket in rules.items():
                rtag, features_, end = slot.split('\x1f')
                if rtag not in classes:
                    continue
                for rule, support in bucket.items():
                    strip, add = rule.split('\x1f')
                    if low.endswith(add) and len(low) > len(add):
                        lemma = low[:len(low) - len(add)] + strip
                        if lemma.endswith(end) and lemma in lemmas[1]:
                            key = (rtag, lemma, features_)
                            readings[key] = max(readings.get(key, 0), support)
        if not readings:
            return None
        # A reading seen fewer times than the support rule, next to one that
        # reaches it, is annotation noise (G-35's support).
        if max(readings.values()) >= FORM_SUPPORT:
            readings = {r: n for r, n in readings.items() if n >= FORM_SUPPORT}
        person_of = lambda r: next((f for f in r[2].split('|') if f.startswith('Person=')), None)
        swap = lambda features, old, new: '|'.join(sorted(new if f == old else f for f in features.split('|')))
        if hint in ('Person=1', 'Person=2') and hint not in {person_of(r) for r in readings}:
            # The same form in the hinted person, by the lemma's learned paradigm («vivía» with «yo»).
            for (t, lemma, features_), n in list(readings.items()):
                other = swap(features_, person_of((t, lemma, features_)), hint)
                counted = table.get(t + '\x1f' + lemma + '\x1f' + other)
                bucket = rules.get(t + '\x1f' + other + '\x1f' + lemma[-2:], {})
                made = {lemma[:len(lemma) - len(r.split('\x1f')[0])] + r.split('\x1f')[1]
                        for r in bucket if lemma.endswith(r.split('\x1f')[0])}
                if counted == low or (counted is None and low in made):
                    readings[(t, lemma, other)] = n
        persons = {person_of(r) for r in readings}
        if hint in persons:
            persons = {hint}
        if len(persons) != 1:
            return False if persons & {'Person=1', 'Person=2'} else None
        person = next(iter(persons))
        if person not in ('Person=1', 'Person=2'):
            return None
        tag, lemma, features_ = max(sorted(r for r in readings if person_of(r) == person), key=lambda r: readings[r])
        values = features_.split('|')
        # Plural persons depend on the variety of Spanish: not restated.  The
        # number of a possessive is the possessed thing's.
        if 'Number[psor]=Plur' in values or ('Number=Plur' in values and 'Number[psor]=Sing' not in values):
            return False
        target = swap(features_, person, 'Person=2' if person == 'Person=1' else 'Person=1')
        form = next((table[t + '\x1f' + lemma + '\x1f' + target] for t in classes
                     if t + '\x1f' + lemma + '\x1f' + target in table), None)
        if form is None and verbal:
            source = rules.get(tag + '\x1f' + features_ + '\x1f' + lemma[-2:], {})
            used = [r.split('\x1f')[0] for r in source if lemma.endswith(r.split('\x1f')[0])
                    and lemma[:len(lemma) - len(r.split('\x1f')[0])] + r.split('\x1f')[1] == low]
            bucket = rules.get(tag + '\x1f' + target + '\x1f' + lemma[-2:], {})
            made = {lemma[:len(lemma) - len(r.split('\x1f')[0])] + r.split('\x1f')[1]: n
                    for r, n in bucket.items() if r.split('\x1f')[0] in used}
            if made:
                form = max(sorted(made), key=lambda f: made[f])
        if form is None and not verbal:
            form = model.get('form_by_features', {}).get(tag + '\x1f' + target)
        if form is None:
            return False
        return form.capitalize() if word[:1].isupper() else form

    def _restated(self, row) -> str | None:
        """G-54: a sentence said in conversation, as the listener says it back:
        the persons swapped with learned forms.  None if a word cannot be."""
        if not isinstance(row, dict) or not self._conversational(row):
            return None
        tree = self._utterance_tree(row['text'])
        if tree is None:
            return None
        words, tags, heads, labels = list(tree[0]), tree[1], tree[2], tree[3]
        # The person of a clause: its subject's, or its pronoun clitic's (they agree).
        hints = {}
        for k in range(len(words)):
            h = heads[k] - 1
            if h < 0:
                continue
            if str(labels[k]).startswith('nsubj') and tags[k] in ('NOUN', 'PROPN'):
                hints.setdefault(h, 'Person=3')
            elif tags[k] == 'PRON':
                person = next((f for f in self.morphology(words[k], 'PRON') if f.startswith('Person=')), None)
                if person and (str(labels[k]).startswith('nsubj') or 'Reflex=Yes' in self.morphology(words[k], 'PRON')):
                    hints[h] = person
        # G-56: a coordinated predicate without a subject of its own shares the
        # first one's (and its person): «me llamo X y vivo en…».
        for k in range(len(words)):
            if labels[k] == 'conj' and heads[k] and k not in hints and heads[k] - 1 in hints and not any(
                    heads[c] == k + 1 and str(labels[c]).startswith('nsubj') for c in range(len(words))):
                hints[k] = hints[heads[k] - 1]
        for k, (w, t) in enumerate(zip(words, tags)):
            hint = hints.get(k)
            if hint is None and labels[k] in ('cop', 'aux') and heads[k]:
                hint = hints.get(heads[k] - 1)
            new = self._swapped_form(w, t, hint)
            if new is None and labels[k] == 'conj' and heads[k] and tags[heads[k] - 1] in ('VERB', 'AUX') \
                    and t not in ('VERB', 'AUX'):
                new = self._swapped_form(w, 'VERB', hint)       # coordinated with a verb: a verb
            if new is False:
                return None
            if new:
                words[k] = new
        # G-56: what opens the sentence to link it with the one before (a
        # conjunction hung from it, or a learned connective set off by
        # punctuation) is not part of what was told.
        start = 0
        connectives = set(self.syntax_model.get('connectives', ()))
        if words and labels[0] == 'cc':
            start = 1
        for size in range(3, 0, -1):
            if start + size < len(words) and tags[start + size] == 'PUNCT' \
                    and ' '.join(w.lower() for w in words[start:start + size]) in connectives:
                start += size + 1
                break
        words, tags = words[start:], tags[start:]
        while words and not _is_word(words[-1]):
            words.pop()
        if not words:
            return None
        if tags[0] != 'PROPN':
            words[0] = words[0][:1].lower() + words[0][1:]
        return self._written(self._surface(words))

    @staticmethod
    def _written(text: str) -> str:
        """Spacing of written punctuation: none before closing marks, none after opening ones."""
        text = re.sub(r' ([,.;:!?)»])', r'\1', text)
        return re.sub(r'([(«¿¡]) ', r'\1', text)

    def _voiced(self, answer: str, rows=()) -> str | None:
        """G-54: the text of a yes/no answer or an abstention in Leobot's own
        voice (``answer_voice``): what was told, said back.  Only «sí», «no»,
        «no lo sé», «me contaste que» and «no me lo has contado» are Leobot's
        own words (programmed, not knowledge).  An open answer stays the
        constituent itself, as a person answers.  None: the old text."""
        if not getattr(self, 'answer_voice', True):
            return None
        told = [t for t in (self._restated(r) for r in rows) if t]
        if answer == 'yes':
            return f'Sí, me contaste que {told[-1]}.' if told else 'Sí, me lo contaste.'
        if answer == 'no':
            return f'No, me contaste que {told[-1]}.' if told else 'No, me contaste lo contrario.'
        if answer == 'contrast':
            return f'No: me contaste que {told[-1]}.' if told else None
        if answer == 'contradiction':
            return f'No lo sé: me contaste que {told[0]}, pero también que {told[-1]}.' \
                if len(set(told)) > 1 else None
        if answer == 'unknown':
            return 'No lo sé: eso no me lo has contado.'
        return None

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

    def _graph(self, heads, labels, conj=False):
        """Undirected links of the enhanced tree, plus the subject a coordinated
        predicate shares with the first one (G-43).  G-47: with ``conj``, each
        coordinated element also keeps its link to the element it was
        coordinated with, as enhanced dependencies do."""
        enhanced, _ = self._enhanced(heads, labels)
        links = [set() for _ in heads]
        for d, h in enumerate(enhanced):
            if h:
                links[d].add(h - 1); links[h - 1].add(d)
        if conj:
            for d, h in enumerate(heads):
                if h and labels[d] == 'conj':
                    links[d].add(h - 1); links[h - 1].add(d)
        for d, h in enumerate(heads):
            if labels[d] == 'conj' and h and not any(heads[k] == d + 1 and str(labels[k]).startswith('nsubj')
                                                     for k in range(len(heads))):
                for k in range(len(heads)):
                    if heads[k] == h and str(labels[k]).startswith('nsubj'):
                        links[d].add(k); links[k].add(d)
        return enhanced, links

    def _question_links(self, question: str, negators: set, skipped=frozenset()):
        """Links between the content words of a yes/no question: each one with
        its nearest content ancestor and the number of steps between them."""
        tree = self._utterance_tree(question)
        if tree is None:
            return None
        words, tags, heads, labels = tree
        enhanced, _ = self._enhanced(heads, labels)
        content = {i for i, (w, t) in enumerate(zip(words, tags))
                   if t not in FUNCTION_TAGS and _is_word(w) and w.lower() not in negators and w.lower() not in skipped}
        enhanced_labels = self._enhanced(heads, labels)[1]
        links, roles, loose = [], [], set()
        for i in sorted(content):
            node = enhanced[i] - 1
            while node >= 0 and node not in content:
                node = enhanced[node] - 1
            if node >= 0:
                # One content step: function words in between are transparent.
                links.append((self._word_key(words[i]), self._word_key(words[node]), 1))
                roles.append((self._word_key(words[i]), self._word_key(words[node]), enhanced_labels[i]))
                if str(enhanced_labels[i]).split(':')[0] not in CORE_LABELS:
                    loose.add((self._word_key(words[i]), self._word_key(words[node])))
        cases = {i: sorted(words[k].lower() for k in range(len(words)) if heads[k] == i + 1 and tags[k] == 'ADP')
                 for i in content}
        copular = {i: any(heads[k] == i + 1 and labels[k] == 'cop' for k in range(len(words))) for i in content}
        # G-56: the parser's core functions are trusted only in the declarative
        # order it learned from (a subject before its verb); with the verb first
        # it often takes the subject for the object.
        declarative = all(heads[i] - 1 < 0 or i < heads[i] - 1 for i in range(len(words))
                          if str(labels[i]).startswith('nsubj'))
        return {'stems': {self._word_key(words[i]) for i in content}, 'links': links,
                'declarative': declarative,
                'tags': {self._word_key(words[i]): tags[i] for i in content},
                'norms': {self._word_key(words[i]): _norm(words[i]) for i in content},
                'cases': {self._word_key(words[i]): cases[i] for i in content},
                'copular': {self._word_key(words[i]): copular[i] for i in content},
                'elabels': {self._word_key(words[i]): enhanced_labels[i] for i in content},
                'roles': roles, 'loose': loose}

    def _same_kind(self, a: str, tag_a: str, b: str, tag_b: str) -> bool:
        """G-55: whether two words, each with its word class, are members of one
        closed learned kind of answer with a noun (G-53: «martes» and «lunes»
        both answer «qué día»).  A member is a word in a class, as counted.  A
        kind whose noun usually takes a complement («qué tipo de…») gathers
        the answers of many dimensions and is left out."""
        index = self.__dict__.get('_kind_members')
        table = self.reading_model.get('answer_kinds', {})
        if index is None or index[0] != len(table):
            members: dict = {}
            for key, row in table.items():
                counts = row.get('members', {})
                tokens, hapax = sum(counts.values()), sum(n == 1 for n in counts.values())
                if ' ' not in key or row['n'] < KIND_SUPPORT or (tokens >= OPEN_TOKENS and hapax >= OPEN_RATE * tokens):
                    continue
                if row.get('complemented', 0) >= KIND_COMPLEMENTED * row['n']:
                    continue        # «qué tipo de…», «qué parte de…»: the complement is the dimension
                for member, n in counts.items():
                    if n >= 2:          # a word seen once answering a kind is Good-Turing's unseen mass, not a member
                        members.setdefault(member, set()).add(key)
            index = self.__dict__['_kind_members'] = (len(table), members)
        return bool(index[1].get(f'{self.lemma_key(a)}\x1f{tag_a}', set())
                    & index[1].get(f'{self.lemma_key(b)}\x1f{tag_b}', set()))

    def _contrast(self, structure, source, negators: set, by_kind: bool = False):
        """G-46: the value the question asks about, if the sentence states the
        same links with another value of the same class in its place, and that
        place is an attribute (a quality, a quantity, a place or time, what a
        copula predicates), which takes one value per thing; what is had,
        exists or is sold is not.  Returns the replaced value or None.
        G-55 (``by_kind``): the dimension is decided by the learned kinds of
        answer instead of the class and the place: the two values are members of
        one closed learned kind, or both numbers written alike, or both names
        with the same preposition; whatever is had, exists or is sold."""
        tree = self._tree_of(source)
        if tree is None or any(w.lower() in negators for w in tree[0]):
            return None
        words, tags, heads, labels = tree
        keys = [self._word_key(w) for w in words]
        for value in sorted(structure['stems']):
            if value in keys:
                continue
            gone = {value}
            links = [l for l in structure['links'] if not (set(l[:2]) & gone)]
            neighbours = {b for a, b, _ in structure['links'] if a == value and b not in gone} | \
                         {a for a, b, _ in structure['links'] if b == value and a not in gone}
            reduced = {'stems': structure['stems'] - gone, 'links': links,
                       'cases': {k: v for k, v in structure['cases'].items() if k not in gone}}
            if not neighbours or not reduced['stems'] or self._links_hold(reduced, source) != 'asserted':
                continue
            eheads, elabels = self._enhanced(heads, labels)
            aligned = {j for j, k in enumerate(keys) if k in reduced['stems']}
            if not by_kind:
                # The asked value must itself sit in an attribute place.
                if not (structure['tags'][value] in ('ADJ', 'NUM') or structure['cases'][value]
                        or structure['copular'][value]):
                    continue
                # G-47b: the kind of something had, existing or sold («cajas de
                # clavos») is not a single-valued attribute: other kinds may exist.
                if getattr(self, 'g47b_structure', True) and structure['cases'][value] and any(
                        str(structure.get('elabels', {}).get(b, '')).split(':')[0] == 'obj'
                        for a, b, _ in structure['roles'] if a == value):
                    continue
            asked = structure['norms'][value]
            # G-55: a direct object (what is had, sold, taught…) may have other values too.
            if by_kind and str(structure.get('elabels', {}).get(value, '')).split(':')[0] == 'obj':
                continue
            for j, (w, t) in enumerate(zip(words, tags)):
                if j in aligned or not _is_word(w):
                    continue
                children = [k for k in range(len(words)) if heads[k] == j + 1]
                case = sorted(words[k].lower() for k in children if tags[k] == 'ADP')
                if by_kind:
                    qtag = structure['tags'][value]
                    kin = (self._same_kind(value, qtag, w, t)
                           or (qtag == t == 'NUM' and w.isdigit() == asked.isdigit())
                           or (qtag == t == 'PROPN' and case and case == structure['cases'][value]))
                    if not kin or self.lemma_key(w) == value:
                        continue
                else:
                    if t != structure['tags'][value]:
                        continue
                    attribute = (t in ('ADJ', 'NUM') or case or any(labels[k] == 'cop' for k in children))
                    # The same place: the same preposition (or none) on both sides.
                    if not attribute or case != structure['cases'][value]:
                        continue
                # G-46b: the same role with respect to the value's neighbour.
                if self._same_role(structure, value, j, words, tags, keys, eheads, elabels, labels, heads):
                    return w
        return None

    def _same_role(self, structure, value, j, words, tags, keys, eheads, elabels, labels, heads) -> bool:
        """Whether sentence word ``j`` relates to the word aligned with the
        value's neighbour as the value does in the question: the same
        direction and function in the enhanced tree (function words are
        transparent); an adjective predicated of the neighbour with a copula
        and one modifying it are the same attribute."""
        def content_head(k):
            node = eheads[k] - 1
            while node >= 0 and tags[node] in FUNCTION_TAGS:
                node = eheads[node] - 1
            return node

        def copular(k):
            return any(heads[m] == k + 1 and labels[m] == 'cop' for m in range(len(words)))
        adjective = structure['tags'][value] == 'ADJ'
        for child, parent, label in structure['roles']:
            if child == value:          # the value depends on its neighbour
                for p in (k for k, key in enumerate(keys) if key == parent):
                    if content_head(j) == p and elabels[j] == label:
                        return True
                    if adjective and label == 'amod' and content_head(p) == j and \
                            str(elabels[p]).startswith('nsubj') and copular(j):
                        return True
            elif parent == value:       # the neighbour depends on the value
                for p in (k for k, key in enumerate(keys) if key == child):
                    if content_head(p) == j and elabels[p] == label:
                        return True
                    if adjective and str(label).startswith('nsubj') and structure['copular'][value] and \
                            content_head(j) == p and elabels[j] == 'amod':
                        return True
        return False

    def _links_hold(self, structure, source):
        """None if the sentence does not state the question's links; 'subordinate'
        if it does but inside a subordinate clause; 'asserted' otherwise."""
        tree = self._tree_of(source)
        if tree is None:
            return None
        words, tags, heads, labels = tree
        stems = [self._word_key(w) for w in words]
        if getattr(self, 'same_fact', True):
            # G-47: one occurrence per question word, links through no other entity, same prepositions.
            placements = self._placements(structure, tree, self._row_key_sets(source, tree))
            if not placements:
                return None
            enhanced, _ = self._graph(heads, labels)
            held = [self._subordinate(enhanced, tags, heads, set(p.values())) for p in placements]
            return 'asserted' if not all(held) else 'subordinate'
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
        return 'subordinate' if self._subordinate(enhanced, tags, heads, aligned) else 'asserted'

    def _subordinate(self, enhanced, tags, heads, aligned) -> bool:
        """G-43: whether the highest aligned word or one of its ancestors
        introduces a subordinate clause (a learned subordinating word under it)."""
        depth = lambda j: len(self._ancestors(enhanced, j))
        top = min(sorted(aligned), key=depth)
        return any(any(heads[k] == node + 1 and tags[k] == 'SCONJ' for k in range(len(heads)))
                   for node in [top] + self._ancestors(enhanced, top))

    def _placements(self, structure, tree, stems):
        """G-47: the ways to place each question word on one occurrence of it
        so that every link of the question holds through aligned and function
        words only (no other entity in between) and each word carries the same
        prepositions as in the question."""
        words, tags, heads, labels = tree
        places: dict = {}
        for j, w in enumerate(words):
            if _is_word(w):
                for key in sorted(stems[j] & set(structure['stems'])):
                    places.setdefault(key, []).append(j)
        if set(places) != set(structure['stems']):
            return []
        keys = sorted(places)
        _, graph = self._graph(heads, labels, conj=True)
        partners = self._partners(words, heads, labels)
        loose = structure.get('loose', set()) if getattr(self, 'core_links', True) else set()
        roles_all = structure.get('elabels', {})
        roles = roles_all if structure.get('declarative', True) else {}
        elabels = self._enhanced(heads, labels)[1]
        occurrences = {j for js in places.values() for j in js}
        out = []
        for combo in itertools.islice(itertools.product(*(places[k] for k in keys)), MAX_PLACEMENTS):
            chosen = dict(zip(keys, combo))
            aligned = set(combo)
            # Another entity: an unplaced noun, name or personal pronoun, or
            # another occurrence of a question word (another fact).
            blocked = {j for j in range(len(words)) if j not in aligned and (
                j in occurrences or tags[j] in ('NOUN', 'PROPN')
                or (tags[j] == 'PRON' and 'PronType=Prs' in self.morphology(words[j], 'PRON')))}
            if all(self._within_clause(words, heads, labels, tags, blocked, partners, chosen[a], chosen[b],
                                       str(roles_all.get(a, '')).split(':')[0]) if (a, b) in loose
                   else self._joined(graph, tags, blocked, partners, chosen[a], chosen[b], steps)
                   for a, b, steps in structure['links']) and not self._roles_swapped(roles, elabels, chosen):
                out.append(chosen)
        return out

    def _roles_swapped(self, roles, elabels, chosen) -> bool:
        """G-56: whether two question words that are core arguments of the
        question with different functions (subject, object, indirect object)
        trade them in the sentence: one takes the other's function («¿María ama
        a Juan?» against «Juan ama a María»).  One word labelled otherwise by
        the parser is not a swap."""
        if not getattr(self, 'core_links', True):
            return False
        core = {k: str(roles.get(k, '')).split(':')[0] for k in chosen}
        core = {k: r for k, r in core.items() if r in ('nsubj', 'obj', 'iobj')}
        return any(ra != rb and str(elabels[chosen[a]]).split(':')[0] == rb
                   and str(elabels[chosen[b]]).split(':')[0] == ra
                   for a, ra in core.items() for b, rb in core.items() if a != b)

    def _within_clause(self, words, heads, labels, tags, blocked, partners, start, goal, own: str = '') -> bool:
        """G-56: a link that is not a core argument (a modifier, a place or a
        time, an apposition) holds if the two words are in one clause: a path
        through the enhanced tree (coordinated elements hang from the head of
        the first one, so coordinated nouns share it and a coordinated predicate
        is a clause of its own) that crosses no edge between clauses and no
        other entity (G-47's blocked words, which may be crossed as the same
        entity).  A punctuation mark no modifier link was seen to reach across
        («;», learned) parts them even where the parser missed the division."""
        barriers = set(self.syntax_model.get('modifier_barriers', ()))
        if any(words[k] in barriers for k in range(min(start, goal) + 1, max(start, goal))):
            return False
        enhanced, elabels = self._enhanced(heads, labels)
        links = [set() for _ in heads]
        for d, h in enumerate(enhanced):
            base = str(elabels[d]).split(':')[0]
            # An edge between clauses is crossed only as the question's own link («hace cinco años»).
            if h and (base not in CLAUSE_EDGES or base == own) and labels[d] != 'conj' or \
                    (h and labels[d] == 'conj' and not self._clause_head(tags, heads, labels, d)):
                links[d].add(h - 1); links[h - 1].add(d)
        seen, stack = {start}, [start]
        while stack:
            node = stack.pop()
            for other in sorted(links[node]):
                if other == goal:
                    return True
                if other in seen or (other in blocked and other not in partners.get(node, ())
                                     and node not in partners.get(other, ())):
                    continue
                seen.add(other); stack.append(other)
        return False

    @staticmethod
    def _clause_head(tags, heads, labels, node) -> bool:
        """G-56: whether a word heads a clause of its own: a verb, or a word
        with its own copula or subject («… y es nueva»)."""
        return tags[node] in ('VERB', 'AUX') or any(
            heads[c] == node + 1 and (labels[c] == 'cop' or str(labels[c]).startswith('nsubj'))
            for c in range(len(heads)))

    @staticmethod
    def _partners(words, heads, labels) -> dict:
        """G-47: nouns that are the same entity as a neighbour: a noun
        predicated with a copula is its subject; a noun in apposition (or a
        name part) is the noun it goes with."""
        partners: dict = {}
        for m, h in enumerate(heads):
            if not h:
                continue
            if labels[m] in ('appos', 'flat'):
                partners.setdefault(h - 1, set()).add(m)
                partners.setdefault(m, set()).add(h - 1)
            elif str(labels[m]).startswith('nsubj'):
                # The predicate of a copula; the parser may hang the subject from the copula itself.
                if any(heads[k] == h and labels[k] == 'cop' for k in range(len(heads))):
                    partners.setdefault(h - 1, set()).add(m)
                elif labels[h - 1] == 'cop' and heads[h - 1]:
                    partners.setdefault(heads[h - 1] - 1, set()).add(m)
        return partners

    @staticmethod
    def _joined(graph, tags, blocked, partners, start, goal, steps) -> bool:
        """Whether a path joins two placed words without another entity and
        with at most ``steps`` + 1 content steps (function words are free).  A
        blocked noun that is the same entity as the word the path comes from
        or goes to (``partners``) may be crossed."""
        far, queue = {(start, None): 0}, deque([(start, None)])
        while queue:
            node, before = queue.popleft()
            for other in sorted(graph[node]):
                if node in blocked and before not in partners.get(node, ()) and other not in partners.get(node, ()):
                    continue
                cost = far[(node, before)] + (0 if tags[other] in FUNCTION_TAGS else 1)
                if cost > steps + 1 or far.get((other, node), cost + 1) <= cost:
                    continue
                if other == goal:
                    return True
                if other in blocked and other not in partners:
                    continue
                far[(other, node)] = cost
                (queue.appendleft if cost == far[(node, before)] else queue.append)((other, node))
        return False

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

    def _lemma_sets(self) -> bool:
        return getattr(self, 'lemma_sets', True) and getattr(self, 'lemma_alignment', True)

    def _key_sets(self, words) -> list:
        """G-47b: the keys each word of a remembered sentence aligns by: every
        learned dictionary form (or only the majority one, as in G-47)."""
        if self._lemma_sets():
            return [self.lemma_keys(w) for w in words]
        return [{self._word_key(w)} for w in words]

    def _search_key(self, word: str) -> str:
        """G-47b: how a question word is looked up in memory: by its
        dictionary form, like alignment (G-47: by its 5-letter stem)."""
        return LEMMA + self._word_key(word) if self._lemma_sets() else _norm(word)

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
        (the G-28 reader then decides).
        G-47 (``same_fact``): each question word is placed on one occurrence,
        so that the question's links hold through no other entity and with the
        same prepositions (the placements of the yes/no check); distances are
        taken in the graph with shared subjects; a negated or subordinate
        statement does not answer; unaligned siblings with one function joined
        only by a conjunction or a comma answer together.  With
        ``answer_type``, a candidate whose class was never seen among at least
        TYPE_SUPPORT worked answers to the same kind of question is ruled out."""
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
        # G-56: the interrogative phrase's common-noun complements («qué día de la
        # semana») belong to the gap; a name there («hermanos de Ana») identifies.
        gap = set(phrase)
        if noun is not None and getattr(self, 'gap_phrase', True):
            # The phrase is fronted as one unit: only a complement that follows
            # the noun without a gap and ends before the question's verb counts.
            verb = next((k for k in range(noun + 1, len(words)) if tags[k] in ('VERB', 'AUX')), len(words))
            for m in (k for k in range(len(words)) if heads[k] == noun + 1 and labels[k] == 'nmod' and tags[k] == 'NOUN'):
                span, stack = [], [m]
                while stack:
                    k = stack.pop(); span.append(k)
                    stack.extend(c for c in range(len(words)) if heads[c] == k + 1)
                # ... and whose words the answering sentence usually does not say (learned).
                optional = self._optional_words()
                if max(span) < verb and sorted(span) == list(range(noun + 1, max(span) + 1)) \
                        and all(tags[k] in FUNCTION_TAGS or self.lemma_key(words[k]) in optional for k in span):
                    gap.update(span)
        skip = self._skippable(words, tags, labels, self.negator_words())
        where: dict = {}
        for i, (w, t) in enumerate(zip(words, tags)):
            if i not in gap and i not in skip and t not in FUNCTION_TAGS and _is_word(w) and low[i] not in interrogatives:
                where.setdefault(self._word_key(w), i)
        noun_key = self._word_key(words[noun]) if noun is not None else None
        categories = set(self.reading_model.get('category_nouns', ()))
        # G-52: the question is copular and its interrogative phrase is not the
        # copula's subject: the gap is the predicate.  The parser may hang the
        # copula from another word or take it as the root.
        gap_head = noun if noun is not None else q
        copular = any(labels[k] == 'cop' or (tags[k] == 'AUX' and not heads[k]) for k in range(len(words)))
        predicate_gap = getattr(self, 'predicate_gap', True) and copular and (
            case is not None or not str(labels[gap_head]).startswith('nsubj'))
        required = set(where)
        if not required:
            return None
        same = getattr(self, 'same_fact', True)
        if same:
            self._resolve_references()
            identity = self._identity_answer(qtree)
            if identity is not None:
                return identity
        retrieval = {self._search_key(words[i]) for i in where.values()}
        index = self._reading_index()
        lists = sorted((set(index.get(t, ())) | set(self._alias_postings(t)) for t in retrieval), key=len)
        positions = set(lists[0]).intersection(*lists[1:])
        if same:
            _, qgraph = self._graph(heads, labels)
            qdist = self._graph_distances(qgraph, noun if noun is not None else q, tags)
            negators = self.negator_words()
            polarity = self.negated(sum(w in negators for w in low))
            shapes = {True: self._open_structure(qtree, q, where, noun, True),
                      False: self._open_structure(qtree, q, where, noun, False)}
        else:
            qheads, _ = self._enhanced(heads, labels)
            qdist = self._tree_distances(qheads, noun if noun is not None else q, tags)
        ranked = []
        for position in sorted(positions):
            row = self.reading_utterances[position]
            tree = self._tree_of(row)
            if tree is None:
                continue
            keys = [self._word_key(w) for w in tree[0]]
            if same:
                sets = self._row_key_sets(row, tree)
                present = set().union(*sets) if sets else set()
                if not required <= present:
                    continue
                ranked += self._placed_candidates(row, tree, sets, shapes[noun_key in present], where, noun, noun_key,
                                                  categories, qdist, labels[q], case, negators, polarity,
                                                  predicate_gap)
            elif required <= set(keys):
                ranked += self._legacy_candidates(row, tree, keys, where, noun, noun_key, required, categories,
                                                  qdist, labels[q], case)
        classes = self._answer_classes_for(low, q, noun) if getattr(self, 'answer_type', True) else None
        if classes is not None:
            ranked = [entry for entry in ranked if classes.get(self._answer_class(entry[1].split())) != 0]
        # G-53: an answer of another kind than the one asked for is not given.
        ranked = [entry for entry in ranked if self._kind_fits(low, q, noun, entry[1], self._head_of(entry)) is not False]
        if not ranked:
            return None
        best = min(key for key, _, _, _ in ranked)
        winners = {}
        for key, text, row, node in ranked:
            if key == best:
                # G-51: a common noun asked with a name-seeking interrogative is answered with its entity's name.
                text = self._name_of(row, node, low[q], text) or text
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

    def _open_structure(self, qtree, q, where, noun, with_noun):
        """G-47: the links an open question states among its content words
        (and the noun of its interrogative phrase when the sentence has it),
        with the prepositions each one carries."""
        words, tags, heads, labels = qtree
        enhanced, elabels = self._enhanced(heads, labels)
        content = set(where.values()) | ({noun} if with_noun and noun is not None else set())
        links, loose = [], set()
        for i in sorted(content):
            node = enhanced[i] - 1
            while node >= 0 and node not in content:
                node = enhanced[node] - 1
            if node >= 0:
                links.append((self._word_key(words[i]), self._word_key(words[node]), 1))
        # The preposition before the interrogative phrase, and the noun of
        # that phrase, belong to the gap, whatever the parser hung them from.
        first = min([q] + ([noun] if noun is not None else []))
        gap = {first - 1} if first > 0 and tags[first - 1] == 'ADP' else set()
        subjects = {(self._word_key(words[enhanced[i] - 1]), 'nsubj') for i in where.values()
                    if enhanced[i] and str(elabels[i]).startswith('nsubj')}
        declarative = all(heads[i] - 1 < 0 or i < heads[i] - 1 for i in range(len(words))
                          if str(labels[i]).startswith('nsubj'))
        return {'stems': {self._word_key(words[i]) for i in content}, 'links': links, 'subjects': subjects,
                'loose': loose, 'declarative': declarative,
                'elabels': {self._word_key(words[i]): elabels[i] for i in content if i != noun},
                'cases': {self._word_key(words[i]): sorted(words[k].lower() for k in range(len(words))
                                                           if heads[k] == i + 1 and tags[k] == 'ADP' and k not in gap)
                          for i in content if i != noun}}

    def _placed_candidates(self, row, tree, keys, structure, where, noun, noun_key, categories, qdist,
                           qlabel, case, negators, polarity, predicate_gap=False):
        swords, stags, sheads, slabels = tree
        n = len(swords)
        children = [[] for _ in range(n)]
        for d, h in enumerate(sheads):
            if h:
                children[h - 1].append(d)
        enhanced, graph = self._graph(sheads, slabels, conj=True)
        literal = self._key_sets(swords)
        out = []
        for placement in self._placements(structure, tree, keys):
            aligned = set(placement.values())
            # G-51: a word placed through another mention of its entity is weaker
            # evidence than the word itself, and that entity is not the answer.
            aliased = sum(k not in literal[j] for k, j in placement.items())
            # The noun of the interrogative phrase («qué calle») is the gap's kind, not a named thing.
            named = self._same_entity(row, aligned - {placement.get(noun_key)})
            negated = self.negated(sum(swords[k].lower() in negators and sheads[k] - 1 in aligned for k in range(n)))
            if negated != polarity or self._subordinate(enhanced, stags, sheads, aligned):
                continue
            covered = [False] * n

            def mark(node):
                inside = node in aligned
                for child in children[node]:
                    inside = mark(child) or inside
                covered[node] = inside
                return inside
            for root in (d for d, h in enumerate(sheads) if not h):
                mark(root)
            host = placement.get(noun_key) if noun_key is not None else None
            first = -(host is not None) if getattr(self, 'g47b_structure', True) else 0
            if predicate_gap:
                # G-52: what the sentence predicates, with a copula, of a placed word.
                for node, span in self._predicates_of(swords, stags, sheads, slabels, children, aligned):
                    text = self._span_text(row, swords, span)
                    if text:
                        out.append(((first, -len(placement), aliased, 0, False, False), text, row, node))
            nodes = []
            for node in range(n):
                # G-56 (``named_conjuncts``): a coordinated noun shares its first
                # element's place: it answers alone when the question named that
                # one («además del paraguas»), or else with it (G-47).  A
                # coordinated predicate is a clause of its own.
                if covered[node] or (slabels[node] == 'conj' and (
                        self._clause_head(stags, sheads, slabels, node)
                        or not getattr(self, 'named_conjuncts', True))):
                    continue
                parent = sheads[node] - 1
                if parent >= 0 and not covered[parent]:
                    continue
                if host is not None and host not in self._ancestors(enhanced, node):
                    continue
                if (host is None and noun is not None and stags[node] == 'NOUN' and noun_key not in keys[node]
                        and getattr(self, 'noun_clash', True) and noun_key not in categories):
                    continue        # G-45: another noun speaks of another thing
                span, stack = [], [node]
                while stack:
                    k = stack.pop(); span.append(k); stack.extend(children[k])
                if slabels[node] == 'conj':         # its conjunction belongs to the coordination
                    span = [k for k in span if not (sheads[k] - 1 == node and slabels[k] == 'cc')]
                if all(stags[k] in FUNCTION_TAGS or not _is_word(swords[k]) for k in span):
                    continue
                nodes.append((node, span))
            for node, span in self._joined_siblings(nodes, sheads, slabels, stags, swords):
                if node in named or self._subject_taken(node, placement, structure, tree, keys, enhanced):
                    continue
                sdist = self._graph_distances(graph, node, stags)
                mirror = sum(abs(qdist[where[k]] - sdist[placement[k]]) for k in where)
                # The gap's preposition: any preposition the answer's head carries.
                own = {swords[k].lower() for k in children[node] if stags[k] == 'ADP'}
                text = self._span_text(row, swords, span)
                if text:
                    # G-47b: a sentence holding the noun of the interrogative phrase comes first.
                    out.append(((first, -len(placement), aliased, mirror, case not in own if case else bool(own),
                                 slabels[node] != qlabel), text, row, node))
        return out

    @staticmethod
    def _predicates_of(words, tags, heads, labels, children, aligned):
        """G-52: predicates with a copula whose subject is a placed word (the
        subject may hang from the copula, or the predicate be taken as an
        apposition of it, the parser's slips), each with its span: the predicate
        and its dependents without the copula, the subject, punctuation,
        coordinated elements or anything placed."""
        out = []
        for p in range(len(words)):
            copulas = [k for k in children[p] if labels[k] == 'cop']
            if not copulas or p in aligned:
                continue
            subjects = [k for k in children[p] if str(labels[k]).startswith('nsubj')]
            subjects += [k for c in copulas for k in children[c] if str(labels[k]).startswith('nsubj')]
            if labels[p] == 'appos' and heads[p]:
                subjects.append(heads[p] - 1)
            if not any(k in aligned for k in subjects):
                continue
            span, stack = [], [p]
            while stack:
                k = stack.pop()
                if k in aligned:
                    continue
                inside = [k]
                queue = list(children[k])
                while queue:
                    c = queue.pop()
                    inside.append(c)
                    queue.extend(children[c])
                if k != p and any(c in aligned for c in inside):
                    continue
                span.append(k)
                stack.extend(c for c in children[k] if k != p or (
                    labels[c] not in ('cop', 'punct', 'conj', 'cc') and not str(labels[c]).startswith('nsubj')))
            if any(tags[k] not in FUNCTION_TAGS and _is_word(words[k]) for k in span):
                out.append((p, span))
        return out

    def _span_text(self, row, words, span) -> str:
        """The words of an answer as they were said: a span of a resolved copy
        is shown with the original words it covers (G-47)."""
        origin = (row.get('resolved') or [None] * 5)[4] if isinstance(row, dict) else None
        if origin:
            said = self._utterance_tree(row['text'])
            kept = [origin[k] for k in span if origin[k] >= 0]
            if said is None or not kept:
                return ''
            words, span = said[0], kept
        a, b = min(span), max(span)
        while a <= b and not _is_word(words[a]):
            a += 1
        while b >= a and not _is_word(words[b]):
            b -= 1
        return self._surface(words[a:b + 1])

    def _surface(self, words) -> str:
        """G-47b: syntactic words back to how they are written: two words the
        learned splitting (G-35) takes apart are joined again («de el» → «del»)."""
        joined = self.__dict__.get('_joined_forms')
        table = self.syntax_model.get('split_table', {})
        if joined is None or joined[0] != len(table):
            forms: dict = {}
            for surface, parts in sorted(table.items()):
                if len(parts) == 2:
                    forms.setdefault((parts[0].lower(), parts[1].lower()), surface)
            joined = self.__dict__['_joined_forms'] = (len(table), forms)
        out, k = [], 0
        while k < len(words):
            pair = (words[k].lower(), words[k + 1].lower()) if k + 1 < len(words) else None
            if pair in joined[1]:
                surface = joined[1][pair]
                out.append(surface.capitalize() if words[k][:1].isupper() else surface)
                k += 2
            else:
                out.append(words[k])
                k += 1
        return ' '.join(out)

    def _subject_taken(self, node, placement, structure, tree, keys, enhanced) -> bool:
        """G-47: a candidate that is the subject of a placed word whose subject
        the question already names (a verb has one subject; coordinated
        predicates share it) is not the gap."""
        words, tags, heads, labels = tree
        if not str(labels[node]).startswith('nsubj') or not structure.get('subjects'):
            return False
        head = heads[node] - 1
        placed = set(placement.values())
        governed = {head} | {d for d in range(len(heads)) if labels[d] == 'conj' and heads[d] - 1 == head
                             and not any(heads[k] == d + 1 and str(labels[k]).startswith('nsubj')
                                         for k in range(len(heads)))}
        return any(g in placed and any((k, 'nsubj') in structure['subjects'] for k in keys[g]) for g in governed)

    @staticmethod
    def _joined_siblings(nodes, heads, labels, tags, words):
        """G-47: siblings with the same function, joined only by a conjunction
        or a comma, answer together («cuarenta y dos» analysed as two numbers)."""
        nodes = sorted(nodes, key=lambda item: min(item[1]))
        groups = []
        for node, span in nodes:
            last = groups[-1] if groups else None
            if last is not None and heads[last[0]] == heads[node] and labels[last[0]] == labels[node]:
                gap = range(max(last[1]) + 1, min(span))
                if gap and all(tags[k] in ('CCONJ', 'PUNCT') and words[k] != '.' for k in gap) \
                        and any(tags[k] == 'CCONJ' or words[k] == ',' for k in gap):
                    last[1].extend(list(gap) + span)
                    continue
            groups.append((node, list(span)))
        return groups

    def _legacy_candidates(self, row, tree, keys, where, noun, noun_key, required, categories, qdist, qlabel, case):
        """The G-45 candidates (the ``same_fact`` ablation)."""
        swords, stags, sheads, slabels = tree
        aligned = {j for j, w in enumerate(swords)
                   if _is_word(w) and (keys[j] in where or keys[j] == noun_key)}
        if not required <= {keys[j] for j in aligned}:
            return []
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
        out = []
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
            out.append(((-coverage, mirror, own_case != case, slabels[node] != qlabel),
                        self._surface(swords[a:b + 1]), row, None))
        return out

    @staticmethod
    def _graph_distances(graph, start: int, tags) -> list[int]:
        """G-47: content steps from ``start`` in an undirected graph of links
        (function words are transparent)."""
        n = len(graph)
        far = [n] * n
        far[start] = 0
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for other in sorted(graph[node]):
                cost = far[node] + (0 if tags[other] in FUNCTION_TAGS else 1)
                if cost < far[other]:
                    far[other] = cost
                    (queue.appendleft if cost == far[node] else queue.append)(other)
        return far

    # ----- G-53: the kind of answer a question asks for --------------------
    def _kind_keys(self, words):
        """The kinds of a question: its interrogative, and with the noun after it."""
        q = self.asking_word(words)
        if q is None:
            return []
        keys = [_fold(words[q])]
        if q + 1 < len(words) and self._majority_tag(words[q + 1]) == 'NOUN':
            keys.append(_fold(words[q]) + ' ' + _fold(words[q + 1]))
        return keys

    def observe_answer_kind(self, question: str, answer: str) -> None:
        """G-53: count, from one worked question, the class of its answer and
        its words (no text is kept, no parsing).  The words that ask must be
        learned first (G-42)."""
        lead = [t.lower() for t in _TOKEN.findall(question) if _is_word(t)][:LEAD_WORDS]
        answer_words = [t for t in _TOKEN.findall(answer) if _is_word(t)][:ANSWER_WORDS]
        keys = self._kind_keys(lead)
        if not keys or not answer_words:
            return
        tags = self.tag_words(answer_words) or []
        content = [(w, t) for w, t in zip(answer_words, tags) if t not in FUNCTION_TAGS]
        if not content:
            return
        # G-55: whether the kind's noun is completed by the learned case of a
        # noun's complement («qué tipo de música»): then that complement names the kind.
        q, case = self.asking_word(lead), self.syntax_model.get('possessor_case')
        after = lead[q + 2] if q is not None and q + 2 < len(lead) else None
        complemented = after is not None and case is not None and \
            self.syntax_model.get('split_table', {}).get(after, [after])[0] == case
        table = self.reading_model.setdefault('answer_kinds', {})
        for key in keys:
            row = table.setdefault(key, {'n': 0, 'classes': {}, 'members': {}})
            row['n'] += 1
            row['classes'][content[0][1]] = row['classes'].get(content[0][1], 0) + 1
            if ' ' in key:
                row['complemented'] = row.get('complemented', 0) + complemented
                for w, t in content:
                    member = self.lemma_key(w) + '\x1f' + t
                    row['members'][member] = row['members'].get(member, 0) + 1

    def observe_question_presence(self, question: str, sentence: str) -> None:
        """G-56: count, from one worked question, which of its words (by
        dictionary form) the sentence that holds the answer says (no parsing)."""
        said = set()
        for t in _TOKEN.findall(sentence):
            if _is_word(t):
                said |= self.lemma_keys(t)
        table = self.reading_model.setdefault('question_presence', {})
        for key in sorted({self.lemma_key(t) for t in _TOKEN.findall(question) if _is_word(t)}):
            row = table.setdefault(key, [0, 0])
            row[0] += 1
            row[1] += key not in said
        self.__dict__.pop('_optional_cache', None)

    def _optional_words(self) -> set:
        """G-56: question words the answering sentence usually does not say."""
        table = self.reading_model.get('question_presence', {})
        cache = self.__dict__.get('_optional_cache')
        if cache is None or cache[0] != len(table):
            cache = self.__dict__['_optional_cache'] = (len(table), {
                key for key, (n, absent) in table.items() if n >= OPTIONAL_SUPPORT and absent >= OPTIONAL_RATE * n})
        return cache[1]

    def _skippable(self, words, tags, labels, negators) -> set:
        """G-56 (``optional_words``): positions of the question whose word is a
        modifier (an adverb, or hung as ``advmod``), learned as optional, not a
        negator, and not said in anything remembered."""
        if not getattr(self, 'optional_words', True):
            return set()
        optional = self._optional_words()
        if not optional:
            return set()
        index = self._reading_index()
        return {i for i, w in enumerate(words) if _is_word(w) and w.lower() not in negators
                and (tags[i] == 'ADV' or str(labels[i]).split(':')[0] == 'advmod')
                and self.lemma_key(w) in optional and not index.get(self._search_key(w))}

    def _head_of(self, entry):
        """G-53: the head word of a candidate answer and its class in the sentence."""
        _, _, row, node = entry
        tree = self._tree_of(row) if node is not None else None
        return (tree[0][node], tree[1][node]) if tree is not None and node < len(tree[0]) else None

    def _kind_row(self, low, q, noun):
        table = self.reading_model.get('answer_kinds', {})
        keys = ([_fold(low[q]) + ' ' + _fold(low[noun])] if noun is not None else []) + [_fold(low[q])]
        for key in keys:
            row = table.get(key)
            if row and row['n'] >= KIND_SUPPORT:
                return key, row
        return None, None

    def _taught_members(self, noun_key) -> set:
        """G-53: words said in conversation right under the question's noun («de color café»)."""
        out = set()
        for row in self.reading_utterances:
            if not self._conversational(row):
                continue
            tree = self._tree_of(row)
            if tree is None:
                continue
            words, _, heads, labels = tree
            for k, h in enumerate(heads):
                if h and labels[k] in MEMBER_LABELS and self._word_key(words[h - 1]) == noun_key:
                    out.add(self._word_key(words[k]))
        return out

    def _kind_fits(self, low, q, noun, text, head=None) -> bool | None:
        """G-53: whether a candidate answer is of the kind the question asks
        for, as learned from worked questions; None when too little was learned.
        ``head`` is the answer's head word and learned class, when known (its
        class is the answer's class); otherwise the first content word."""
        if not getattr(self, 'answer_kind', True):
            return None
        key, row = self._kind_row(low, q, noun)
        if row is None:
            return None
        if head is None:
            words = [w for w in text.split() if _is_word(w)]
            tags = self.tag_words(words) or []
            head = next(((w, t) for w, t in zip(words, tags) if t not in FUNCTION_TAGS), None)
        if head is None:
            return False
        word, tag = head
        # The class, only where the kind clearly asks for one class of word.
        if max(row['classes'].values()) >= KIND_DOMINANT * row['n'] and \
                row['classes'].get(tag, 0) < KIND_SHARE * row['n']:
            return False
        if ' ' not in key or tag == 'PROPN':
            return True            # a name is an arbitrary label: never having seen it says nothing
        members = row['members']
        # Open or closed: how often an answer word of this kind was new (Good-Turing).
        tokens, hapax = sum(members.values()), sum(count == 1 for count in members.values())
        if tokens >= OPEN_TOKENS and hapax >= OPEN_RATE * tokens:
            return True
        if self.lemma_key(word) in {m.split('\x1f')[0] for m in members}:
            return True
        return self._word_key(word) in self._taught_members(self._word_key(low[noun]))

    def _answer_class(self, words) -> str | None:
        """G-43/G-47: the class of an answer, the learned tag of its first content word."""
        words = [w for w in words if _is_word(w)]
        if not words:
            return None
        tags = self.tag_words(words) or []
        return next((t for t in tags if t not in FUNCTION_TAGS), None)

    def _answer_classes_for(self, low, q, noun):
        """G-47: the answer classes seen for this kind of question, if seen
        often enough to rule out the others; the interrogative with its noun
        when that has the support, otherwise the interrogative alone."""
        table = self.reading_model.get('answer_classes', {})
        keys = ([_fold(low[q]) + ' ' + _fold(low[noun])] if noun is not None else []) + [_fold(low[q])]
        for key in keys:
            row = table.get(key)
            if row and sum(row.values()) >= TYPE_SUPPORT:
                return {cls: row.get(cls, 0) for cls in self._tag_list()}
        return None

    def _compile_answer_classes(self) -> None:
        """G-47: count the class of each worked answer by the kind of question."""
        table: dict = {}
        for key, n in sorted(self.reading_model.get('answer_leads', {}).items()):
            lead, answer = key.split('\x1e')
            words = lead.split()
            q = self.asking_word(words)
            cls = self._answer_class(answer.split())
            if q is None or cls is None:
                continue
            names = [_fold(words[q])]
            if q + 1 < len(words) and self._majority_tag(words[q + 1]) == 'NOUN':
                names.append(_fold(words[q]) + ' ' + _fold(words[q + 1]))
            for name in names:
                row = table.setdefault(name, {})
                row[cls] = row.get(cls, 0) + n
        self.reading_model['answer_classes'] = table

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

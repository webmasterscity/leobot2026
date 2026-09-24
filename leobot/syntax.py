"""G-29: word classes and syntactic dependencies learned only by counting.

Demonstrations are sentences with word classes and heads.  A trigram hidden
Markov tagger with a suffix model for unknown words (after TnT, Brants 2000)
and an arc-factored dependency scorer decoded with Eisner's projective
algorithm (Eisner 1996) are compiled from counts: no neural network,
perceptron or gradient.  Arc scores are log-ratios of how often a
configuration is a real arc versus an opportunity for one, estimated along a
chain of contexts from general to specific (G-32).
"""
from __future__ import annotations

import math
import re
import unicodedata

MAX_PARSE = 60
LEXICAL_MIN = 3
SUFFIX_MAX = 5
SUFFIX_FREQ = 10
BEAM = 12
ARC_SMOOTHING = 5.0   # G-32: each arc context is smoothed toward the more general one
LABEL_SMOOTHING = 3.0
PRUNE_OPPORTUNITIES = 2
SPLIT_TABLE_MIN = 2       # G-35: a surface form seen split this often is stored
SPLIT_RULE_SUPPORT = 3    # distinct forms supporting an ending rule
SPLIT_RULE_RATE = 0.9     # share of words with that ending that were split
OPENER_WORDS = 3          # G-42: leading words kept per sentence (prepositions are skipped later)
OPENER_SUPPORT = 3        # questions a word must open to be learned as interrogative
OPENER_RATE = 0.9         # ... and its balanced share of question openings
MORPH_TAGS = frozenset({'PRON', 'DET', 'NOUN', 'VERB', 'AUX'})   # G-47: words whose features are kept
MORPH_NAMES = frozenset({'Person', 'Number', 'Gender', 'Poss', 'PronType', 'Reflex', 'Case'})
LEMMA_SUPPORT = 3          # G-47b: an annotated lemma kept as an alternative this often ...
LEMMA_SHARE = 0.2          # ... and in at least this share of the form's occurrences
IMPERSONAL_SUPPORT = 30   # G-47: a verb seen this often ...
IMPERSONAL_RATE = 0.05    # ... with an explicit subject less often than this is impersonal
_WORD = re.compile(r'\w+|[^\w\s]')


def _empty_syntax() -> dict:
    return {'sentences': 0, 'tags': {}, 'bigrams': {}, 'trigrams': {}, 'lexicon': {},
            'suffixes': {}, 'word_counts': {}, 'arcs': {}, 'opportunities': {},
            'arc_total': 0, 'opportunity_total': 0, 'compiled': False, 'labels': {},
            'multiword': {}, 'split_table': {}, 'split_rules': {}}


def _distance(d: int) -> str:
    d = abs(d)
    for edge in (1, 2, 3, 4, 6, 10, 20):
        if d <= edge:
            return str(edge)
    return '20+'


def _cap(word: str) -> str:
    if any(ch.isdigit() for ch in word):
        return 'D'
    return 'C' if word[:1].isupper() else 'l'


def _add(table: dict, key: str, amount: int = 1) -> None:
    table[key] = table.get(key, 0) + amount


class SyntaxMixin:
    """Mixed into Bot; learned state lives in ``syntax_model``."""

    # ----- learning ------------------------------------------------------
    def observe_parsed_sentence(self, words, tags, heads, labels=None, feats=None, lemmas=None) -> dict:
        """Learn from one annotated sentence (heads are 1-based, 0 = root);
        dependency functions are learned too when the demonstration has them.
        G-41: with morphological features, which words mark negative polarity
        and which ones ask are counted too (``Polarity=Neg``, ``PronType=Int``)."""
        if not (len(words) == len(tags) == len(heads)) or not words:
            return {'status': 'syntax_example_rejected'}
        if labels is not None and len(labels) != len(words):
            return {'status': 'syntax_example_rejected'}
        if feats is not None and len(feats) != len(words):
            return {'status': 'syntax_example_rejected'}
        if lemmas is not None and len(lemmas) != len(words):
            return {'status': 'syntax_example_rejected'}
        model = self.syntax_model
        model['sentences'] += 1
        model['compiled'] = False
        history = ['<s>', '<s>'] + list(tags) + ['</s>']
        for i in range(2, len(history)):
            _add(model['tags'], history[i])
            _add(model['bigrams'], history[i - 1] + '\x1f' + history[i])
            _add(model['trigrams'], history[i - 2] + '\x1f' + history[i - 1] + '\x1f' + history[i])
        for word, tag in zip(words, tags):
            _add(model['lexicon'], word + '\x1f' + tag)
            _add(model['word_counts'], word)
        # Arc statistics: every (head, dependent) pair is an opportunity.
        lowered = [w.lower() for w in words]
        for d in range(1, len(words) + 1):
            gold = heads[d - 1]
            for h in range(0, len(words) + 1):
                if h == d:
                    continue
                arc = h == gold
                for feature in self._arc_features(h, d, lowered, tags, model['word_counts']):
                    _add(model['opportunities'], feature)
                    if arc:
                        _add(model['arcs'], feature)
        model['arc_total'] += len(words)
        model['opportunity_total'] += len(words) * len(words)
        self._observe_opener(words, '¿' in words or '?' in words)
        if lemmas is not None:
            # G-44: dictionary forms, so that inflected forms align and
            # different words that share a beginning do not.
            table = model.setdefault('lemma_counts', {})
            for word, lemma in zip(lowered, lemmas):
                if lemma and lemma != '_':
                    row = table.setdefault(word, {})
                    row[lemma.lower()] = row.get(lemma.lower(), 0) + 1
        if feats is not None:
            marks = model.setdefault('word_marks', {})
            for word, feat in zip(lowered, feats):
                values = set(str(feat).split('|'))
                row = marks.setdefault(word, [0, 0, 0])
                row[0] += 1
                row[1] += 'Polarity=Neg' in values
                row[2] += 'PronType=Int' in values
            # G-47: person, number, gender and kind of reference, per word and class.
            morph = model.setdefault('morph_counts', {})
            for word, tag, feat in zip(lowered, tags, feats):
                if tag not in MORPH_TAGS:
                    continue
                row = morph.setdefault(word + '\x1f' + tag, {})
                row['n'] = row.get('n', 0) + 1
                for value in str(feat).split('|'):
                    if value.split('=')[0] in MORPH_NAMES:
                        row[value] = row.get(value, 0) + 1
        if feats is not None and labels is not None:
            # G-49: which preposition marks a noun's nominal complement, and
            # which one the complement doubled by a dative clitic.
            cases = model.setdefault('complement_cases', {'nmod': {}, 'dative': {}})
            marks = {d: [lowered[k] for k in range(len(words)) if heads[k] == d + 1 and labels[k] == 'case']
                     for d in range(len(words))}
            dative_heads = {heads[k] for k in range(len(words))
                            if tags[k] == 'PRON' and 'Case=Dat' in str(feats[k]).split('|')}
            for d, (tag, label) in enumerate(zip(tags, labels)):
                if tag not in ('NOUN', 'PROPN') or len(marks[d]) != 1:
                    continue
                head = heads[d] - 1
                if label == 'nmod' and head >= 0 and tags[head] == 'NOUN':
                    _add(cases['nmod'], marks[d][0])
                elif label in ('obl', 'iobj') and heads[d] in dative_heads:
                    _add(cases['dative'], marks[d][0])
        if lemmas is not None and labels is not None:
            # G-47: how often each verb has a subject of its own.
            subjects = model.setdefault('subject_counts', {})
            with_subject = {heads[d] for d, label in enumerate(labels) if str(label).startswith('nsubj')}
            for d, (tag, lemma) in enumerate(zip(tags, lemmas)):
                if tag == 'VERB' and lemma and lemma != '_':
                    row = subjects.setdefault(lemma.lower(), [0, 0])
                    row[0] += 1
                    row[1] += (d + 1) in with_subject
        if labels is not None:
            table = model.setdefault('labels', {})
            for d, label in enumerate(labels, 1):
                for context in self._label_contexts(d, heads[d - 1], lowered, tags, heads,
                                                    model['word_counts'], True):
                    row = table.setdefault(context, {})
                    row[label] = row.get(label, 0) + 1
        return {'status': 'syntax_example_learned'}

    def _observe_opener(self, words, question: bool) -> None:
        """G-42: the first words of a sentence, counted apart for questions and
        assertions.  Which leading words are prepositions is decided when
        compiling, from the learned tags, so the counts do not depend on the
        order in which sentences arrive."""
        lead = [w.lower() for w in words if any(ch.isalnum() for ch in w)][:OPENER_WORDS]
        if not lead:
            return
        table = self.syntax_model.setdefault('openers', {'q': {}, 'a': {}, 'nq': 0, 'na': 0})
        kind = 'q' if question else 'a'
        table['n' + kind] += 1
        _add(table[kind], '\x1f'.join(lead))

    def _compile_question_words(self) -> None:
        """Interrogatives: words annotated as asking (G-41) and words that open
        questions far more than assertions once prepositions are skipped
        (G-42), both with G-35's rule (support >= 3 and >= 90 %)."""
        model = self.syntax_model
        marks = model.get('word_marks', {})
        learned = {w for w, (n, _, q) in marks.items() if q >= 3 and q >= 0.9 * n}
        openers = model.get('openers')
        if openers and openers['nq'] and openers['na']:
            tags: dict = {}
            for key, count in model['lexicon'].items():
                word, tag = key.rsplit('\x1f', 1)
                row = tags.setdefault(word.lower(), {})
                row[tag] = row.get(tag, 0) + count

            def preposition(word):
                row = tags.get(word)
                return bool(row) and max(row.items(), key=lambda kv: (kv[1], kv[0]))[0] == 'ADP'
            opened: dict = {'q': {}, 'a': {}}
            for kind in ('q', 'a'):
                for key, count in openers[kind].items():
                    word = next((w for w in key.split('\x1f') if not preposition(w)), None)
                    if word is not None:
                        _add(opened[kind], word, count)
            for word, count in opened['q'].items():
                asked = count / openers['nq']
                stated = opened['a'].get(word, 0) / openers['na']
                if count >= OPENER_SUPPORT and asked / (asked + stated) >= OPENER_RATE:
                    learned.add(word)
        model['interrogatives'] = sorted(learned)

    def morphology(self, word: str, tag: str) -> set:
        """G-47: the learned features of a word in a class (empty if unknown)."""
        low = word.lower()
        value = self.syntax_model.get('morph_table', {}).get(low + '\x1f' + tag)
        if not value and tag == 'VERB':
            endings = self.syntax_model.get('morph_endings', {})
            value = next((endings[low[-size:]] for size in range(SUFFIX_MAX, 0, -1)
                          if len(low) > size and low[-size:] in endings), None)
        return set(value.split('|')) if value else set()

    def lemma_key(self, word: str) -> str:
        """G-44: the learned dictionary form of a word, without accents; an
        unknown word stands for itself."""
        low = word.lower()
        lemma = self.syntax_model.get('lemma_table', {}).get(low, low)
        decomposed = unicodedata.normalize('NFKD', lemma)
        return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))

    def lemma_keys(self, word: str) -> set:
        """G-47b: the majority dictionary form and every other form the word
        was annotated with often enough, without accents."""
        keys = {self.lemma_key(word)}
        for lemma in self.syntax_model.get('lemma_sets', {}).get(word.lower(), ()):
            decomposed = unicodedata.normalize('NFKD', lemma)
            keys.add(''.join(ch for ch in decomposed if not unicodedata.combining(ch)))
        return keys

    def observe_multiword(self, surface: str, words) -> dict:
        """Learn that a written form stands for several syntactic words (G-35)."""
        words = [w for w in words if w]
        if len(words) < 2 or not surface:
            return {'status': 'multiword_rejected'}
        key = surface.lower() + '\x1f' + '\x1f'.join(w.lower() for w in words)
        table = self.syntax_model.setdefault('multiword', {})
        table[key] = table.get(key, 0) + 1
        self.syntax_model['compiled'] = False
        return {'status': 'multiword_learned'}

    def _compile_splitting(self) -> None:
        """Table of seen forms and ending rules induced from them, kept only
        when the ending is almost always split in the demonstrations."""
        model = self.syntax_model
        by_surface: dict = {}
        rules: dict = {}
        for key, count in model.get('multiword', {}).items():
            surface, *words = key.split('\x1f')
            best = by_surface.get(surface)
            if best is None or count > best[1]:
                by_surface[surface] = (words, count)
            first = words[0]
            common = 0
            while common < min(len(surface), len(first)) and surface[common] == first[common]:
                common += 1
            if common < 2:
                continue
            ending = surface[common - 1:]
            rule = rules.setdefault(ending, {})
            target = '\x1f'.join([first[common - 1:]] + words[1:])
            rule.setdefault(target, set()).add(surface)
        model['split_table'] = {s: w for s, (w, c) in by_surface.items()
                                if c >= SPLIT_TABLE_MIN}
        split_counts: dict = {}
        for key, count in model.get('multiword', {}).items():
            surface = key.split('\x1f')[0]
            split_counts[surface] = split_counts.get(surface, 0) + count
        kept = {}
        for ending, targets in rules.items():
            target, forms = max(targets.items(), key=lambda kv: (len(kv[1]), kv[0]))
            if len(forms) < SPLIT_RULE_SUPPORT:
                continue
            split = sum(c for s, c in split_counts.items() if s.endswith(ending))
            whole = sum(c for w, c in model['word_counts'].items() if w.lower().endswith(ending))
            if split / max(1, split + whole) >= SPLIT_RULE_RATE:
                kept[ending] = target.split('\x1f')
        model['split_rules'] = kept

    def split_words(self, text: str) -> list[str]:
        """Raw text into syntactic words with the learned splitting."""
        model = self.syntax_model
        if not model.get('compiled'):
            self.consolidate_syntax()
        table, rules = model.get('split_table', {}), model.get('split_rules', {})
        known = model['word_counts']
        endings = sorted(rules, key=lambda e: (-len(e), e))
        out = []
        for token in _WORD.findall(text):
            low = token.lower()
            words = table.get(low)
            if words is None:
                for ending in endings:
                    if low.endswith(ending) and len(low) > len(ending) + 1:
                        first = low[:len(low) - len(ending)] + rules[ending][0]
                        if known.get(first, 0) or known.get(first.capitalize(), 0):
                            words = [first] + rules[ending][1:]
                            break
            if words is None:
                out.append(token)
                continue
            head = words[0]
            out.append(head.capitalize() if token[:1].isupper() else head)
            out.extend(words[1:])
        return out

    @staticmethod
    def _label_contexts(d, h, words, tags, heads, counts, lexical) -> list[str]:
        """Contexts for a dependency's function, most general first.  The
        marker is the leftmost word attached to the dependent before it (a
        preposition or article, learned from the data; no class names)."""
        head_tag = tags[h - 1] if h else 'ROOT'
        dep_tag = tags[d - 1]
        direction = 'R' if h < d else 'L'
        distance = _distance(h - d) if h else 'root'
        before = [i for i in range(1, d) if heads[i - 1] == d]
        marker = words[before[0] - 1] if before else '-'
        if counts.get(marker, 0) < LEXICAL_MIN:
            marker = '?' if before else '-'
        contexts = [f'1\x1f{dep_tag}', f'2\x1f{head_tag}\x1f{dep_tag}\x1f{direction}']
        if lexical:
            contexts.append(f'3\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{marker}')
        contexts.append(f'4\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{distance}')
        if lexical and h:
            # G-32c: agreement learned from endings (no grammar written down).
            contexts.append(f'7\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{words[h - 1][-1:]}\x1f{words[d - 1][-1:]}')
        if lexical:
            contexts.append(f'5\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{distance}\x1f{marker}')
            head_word = words[h - 1] if h else '<root>'
            if h and counts.get(head_word, 0) >= LEXICAL_MIN:
                # G-32c: each frequent head's own tendencies (e.g. which verbs
                # take a subject after them).
                contexts.append(f'8\x1f{head_word}\x1f{dep_tag}\x1f{direction}\x1f{marker}')
            dep_word = words[d - 1]
            if counts.get(dep_word, 0) >= LEXICAL_MIN:
                contexts.append(f'6\x1f{head_tag}\x1f{dep_tag}\x1f{dep_word}\x1f{direction}\x1f{marker}')
        return contexts

    def label_arcs(self, words, tags, heads, lexical: bool = True) -> list[str] | None:
        """Most probable function of each arc, smoothing each context toward
        the more general one (no gradient, no classifier weights)."""
        table = self.syntax_model.get('labels') or {}
        if not table:
            return None
        lowered = [w.lower() for w in words]
        counts = self.syntax_model['word_counts']
        inventory = sorted({label for row in table.values() for label in row})
        estimates = []
        for d in range(1, len(words) + 1):
            estimate = {label: 1.0 / len(inventory) for label in inventory}
            for context in self._label_contexts(d, heads[d - 1], lowered, tags, heads, counts, lexical):
                row = table.get(context)
                if not row:
                    continue
                seen = sum(row.values())
                estimate = {label: (row.get(label, 0) + LABEL_SMOOTHING * p) / (seen + LABEL_SMOOTHING)
                            for label, p in estimate.items()}
            estimates.append(estimate)
        # Enforcing a learned one-per-head uniqueness was tried in development
        # and lowered LAS (0.693 -> 0.682); functions are chosen per arc.
        out = [max(inventory, key=lambda label: (e[label], label)) for e in estimates]
        return out

    @staticmethod
    def _arc_features(h, d, words, tags, counts) -> list[str]:
        """Arc contexts, most general first (G-32).  Each is smoothed toward the
        previous one instead of summing correlated evidence."""
        head_tag = tags[h - 1] if h else 'ROOT'
        dep_tag = tags[d - 1]
        direction = 'R' if h < d else 'L'
        distance = _distance(h - d) if h else 'root'
        low, high = (h, d) if h < d else (d, h)
        between = tags[low:high - 1] if h else ()
        verb = 'v' if 'VERB' in between or 'AUX' in between else '-'
        punct = 'p' if 'PUNCT' in between else '-'
        same = 'y' if dep_tag in between else 'n'
        contexts = [f'A1\x1f{head_tag}\x1f{dep_tag}\x1f{direction}',
                    f'A2\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{distance}',
                    f'A3\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{distance}\x1f{verb}{punct}{same}']
        head_word = words[h - 1] if h else '<root>'
        dep_word = words[d - 1]
        if h and counts.get(head_word, 0) >= LEXICAL_MIN:
            contexts.append(f'A4\x1f{head_word}\x1f{dep_tag}\x1f{direction}\x1f{distance}')
        if counts.get(dep_word, 0) >= LEXICAL_MIN:
            contexts.append(f'A5\x1f{head_tag}\x1f{dep_word}\x1f{direction}\x1f{distance}')
        return contexts

    def consolidate_syntax(self) -> dict:
        """Compile suffix statistics and interpolation weights from the counts."""
        model = self.syntax_model
        self._compile_splitting()
        # G-41: learned lexicons, with G-35's promotion rule (support >= 3 and
        # the feature in >= 90 % of the word's annotated occurrences).
        marks = model.get('word_marks', {})
        model['negators'] = sorted(w for w, (n, neg, _) in marks.items() if neg >= 3 and neg >= 0.9 * n)
        # G-47: each word's features with the same rule, and the verbs that
        # almost never take a subject.
        model['morph_table'] = {key: '|'.join(sorted(v for v, c in row.items() if v != 'n' and c >= 3
                                                     and c >= 0.9 * row['n']))
                                for key, row in model.get('morph_counts', {}).items()}
        model['morph_table'] = {k: v for k, v in model['morph_table'].items() if v}
        # G-47: person and number of verb forms never seen often enough, from
        # their endings, with G-35's rule over distinct forms.
        endings: dict = {}
        for key, value in model['morph_table'].items():
            word, tag = key.rsplit('\x1f', 1)
            bundle = '|'.join(v for v in value.split('|') if v.split('=')[0] in ('Person', 'Number'))
            if tag != 'VERB' or 'Person=' not in bundle:
                continue
            for size in range(1, SUFFIX_MAX + 1):
                if len(word) > size:
                    row = endings.setdefault(word[-size:], {})
                    row[bundle] = row.get(bundle, 0) + 1
        model['morph_endings'] = {}
        for ending, row in endings.items():
            total, (bundle, count) = sum(row.values()), max(sorted(row.items()), key=lambda kv: kv[1])
            if count >= SPLIT_RULE_SUPPORT and count >= SPLIT_RULE_RATE * total:
                model['morph_endings'][ending] = bundle
        cases = model.get('complement_cases', {})
        for name, key in (('possessor_case', 'nmod'), ('dative_case', 'dative')):
            row = cases.get(key, {})
            model[name] = max(sorted(row), key=lambda w: row[w]) if row else None
        model['impersonal'] = sorted(lemma for lemma, (n, s) in model.get('subject_counts', {}).items()
                                     if n >= IMPERSONAL_SUPPORT and s < IMPERSONAL_RATE * n)
        self._compile_question_words()
        model['lemma_table'] = {w: max(sorted(row), key=lambda k: row[k])
                                for w, row in model.get('lemma_counts', {}).items()
                                if max(sorted(row), key=lambda k: row[k]) != w}
        # G-47b: every lemma a form was annotated with often enough.
        model['lemma_sets'] = {}
        for w, row in model.get('lemma_counts', {}).items():
            total = sum(row.values())
            kept = sorted(l for l, c in row.items() if c >= LEMMA_SUPPORT and c >= LEMMA_SHARE * total)
            if len(kept) > 1:
                model['lemma_sets'][w] = kept
        # G-32b: a context never seen as an arc and seen as an opportunity at
        # most PRUNE_OPPORTUNITIES times barely moves its parent's rate; drop it
        # so the learned memory stays loadable.
        arcs = model['arcs']
        model['opportunities'] = {key: count for key, count in model['opportunities'].items()
                                  if count > PRUNE_OPPORTUNITIES or arcs.get(key)}
        suffixes: dict = {}
        for key, count in model['lexicon'].items():
            word, tag = key.rsplit('\x1f', 1)
            if model['word_counts'].get(word, 0) > SUFFIX_FREQ:
                continue
            low = word.lower()
            for size in range(0, min(SUFFIX_MAX, len(low)) + 1):
                _add(suffixes, _cap(word) + '\x1f' + low[len(low) - size:] + '\x1f' + tag, count)
        model['suffixes'] = suffixes
        # Deleted interpolation for trigram transitions (Brants 2000).
        l1 = l2 = l3 = 0
        tags, bigrams = model['tags'], model['bigrams']
        total = sum(tags.values())
        for key, count in model['trigrams'].items():
            t1, t2, t3 = key.split('\x1f')
            c12 = bigrams.get(t1 + '\x1f' + t2, 0)
            c2 = tags.get(t2, 0) if t2 != '<s>' else model['sentences']
            c23 = bigrams.get(t2 + '\x1f' + t3, 0)
            options = [((count - 1) / (c12 - 1)) if c12 > 1 else 0,
                       ((c23 - 1) / (c2 - 1)) if c2 > 1 else 0,
                       ((tags.get(t3, 0) - 1) / (total - 1)) if total > 1 else 0]
            best = options.index(max(options))
            if best == 0:
                l3 += count
            elif best == 1:
                l2 += count
            else:
                l1 += count
        norm = (l1 + l2 + l3) or 1
        model['lambdas'] = [l1 / norm, l2 / norm, l3 / norm]
        probabilities = [c / total for t, c in tags.items() if t != '</s>'] if total else [0]
        mean = sum(probabilities) / len(probabilities)
        model['theta'] = math.sqrt(sum((p - mean) ** 2 for p in probabilities) / max(1, len(probabilities) - 1))
        model['compiled'] = True
        self._syntax_cache = None
        return {'status': 'syntax_consolidated', 'sentences': model['sentences'],
                'suffix_entries': len(suffixes)}

    # ----- tagging -------------------------------------------------------
    def _tag_list(self) -> list[str]:
        return sorted(t for t in self.syntax_model['tags'] if t != '</s>')

    def _transition(self, t1: str, t2: str, t3: str) -> float:
        model = self.syntax_model
        l1, l2, l3 = model['lambdas']
        tags, bigrams, trigrams = model['tags'], model['bigrams'], model['trigrams']
        total = sum(tags.values())
        c12 = bigrams.get(t1 + '\x1f' + t2, 0)
        c2 = tags.get(t2, 0) if t2 != '<s>' else model['sentences']
        p = l1 * tags.get(t3, 0) / total
        if c2:
            p += l2 * bigrams.get(t2 + '\x1f' + t3, 0) / c2
        if c12:
            p += l3 * trigrams.get(t1 + '\x1f' + t2 + '\x1f' + t3, 0) / c12
        return math.log(p) if p > 0 else -30.0

    def _emissions(self, word: str) -> dict:
        model = self.syntax_model
        tags = self._tag_list()
        counts = {t: model['lexicon'].get(word + '\x1f' + t, 0) for t in tags}
        if sum(counts.values()) == 0 and word[:1].isupper():
            counts = {t: model['lexicon'].get(word.lower() + '\x1f' + t, 0) for t in tags}
        if sum(counts.values()):
            return {t: math.log(c / model['tags'][t]) for t, c in counts.items() if c}
        # Unknown word: TnT suffix model, P(t | suffix) by successive
        # abstraction, turned into P(word | t) up to a constant.
        total = sum(c for t, c in model['tags'].items() if t != '</s>')
        estimate = self._suffix_estimate(word)
        return {t: math.log(p / (model['tags'][t] / total)) for t, p in estimate.items() if p > 0}

    def _suffix_estimate(self, word: str) -> dict:
        model = self.syntax_model
        tags = self._tag_list()
        low, cap, theta = word.lower(), _cap(word), model['theta']
        total = sum(c for t, c in model['tags'].items() if t != '</s>')
        estimate = {t: model['tags'][t] / total for t in tags}
        for size in range(0, min(SUFFIX_MAX, len(low)) + 1):
            suffix = low[len(low) - size:]
            local = {t: model['suffixes'].get(cap + '\x1f' + suffix + '\x1f' + t, 0) for t in tags}
            seen = sum(local.values())
            if not seen:
                break
            estimate = {t: (local[t] / seen + theta * estimate[t]) / (1 + theta) for t in tags}
        return estimate

    def tag_words(self, words) -> list[str] | None:
        model = self.syntax_model
        if not model['sentences']:
            return None
        if not model.get('compiled'):
            self.consolidate_syntax()
        beam = {('<s>', '<s>'): (0.0, [])}
        for word in words:
            emissions = self._emissions(word)
            nxt: dict = {}
            for (t1, t2), (score, path) in beam.items():
                for t3, emit in emissions.items():
                    value = score + self._transition(t1, t2, t3) + emit
                    state = (t2, t3)
                    if state not in nxt or value > nxt[state][0]:
                        nxt[state] = (value, path + [t3])
            beam = dict(sorted(nxt.items(), key=lambda kv: (-kv[1][0], kv[0]))[:BEAM])
        final = max(beam.items(), key=lambda kv: (kv[1][0] + self._transition(kv[0][0], kv[0][1], '</s>'),
                                                   kv[0]))
        return final[1][1]

    # ----- parsing -------------------------------------------------------
    def _arc_score(self, contexts, prior: float) -> float:
        model = self.syntax_model
        arcs, chances = model['arcs'], model['opportunities']
        rate = prior
        for context in contexts:
            rate = (arcs.get(context, 0) + ARC_SMOOTHING * rate) / (chances.get(context, 0) + ARC_SMOOTHING)
        rate = min(max(rate, 1e-9), 1 - 1e-9)
        return math.log(rate / (1 - rate)) - math.log(prior / (1 - prior))

    def parse_words(self, words, tags=None) -> dict | None:
        model = self.syntax_model
        if not model['sentences'] or not words:
            return None
        if len(words) > MAX_PARSE:
            return {'status': 'syntax_too_long', 'words': list(words)}
        tags = list(tags) if tags is not None else self.tag_words(words)
        lowered = [w.lower() for w in words]
        prior = model['arc_total'] / max(1, model['opportunity_total'])
        n = len(words)
        score = [[0.0] * (n + 1) for _ in range(n + 1)]
        memo: dict = {}
        for h in range(n + 1):
            for d in range(1, n + 1):
                if h == d:
                    continue
                contexts = tuple(self._arc_features(h, d, lowered, tags, model['word_counts']))
                value = memo.get(contexts)
                if value is None:
                    value = memo[contexts] = self._arc_score(contexts, prior)
                score[h][d] = value
        heads = self._eisner(score, n)
        result = {'status': 'parsed_syntax', 'words': list(words), 'tags': tags, 'heads': heads}
        labels = self.label_arcs(words, tags, heads)
        if labels is not None:
            result['labels'] = labels
        return result

    @staticmethod
    def _eisner(score, n) -> list[int]:
        """First-order projective maximum spanning tree (Eisner 1996)."""
        neg = float('-inf')
        size = n + 1
        # complete[s][t][dir], incomplete[s][t][dir]; dir 1 = head on the left.
        complete = [[[0.0, 0.0] for _ in range(size)] for _ in range(size)]
        incomplete = [[[neg, neg] for _ in range(size)] for _ in range(size)]
        cback = [[[0, 0] for _ in range(size)] for _ in range(size)]
        iback = [[[0, 0] for _ in range(size)] for _ in range(size)]
        for length in range(1, size):
            for s in range(0, size - length):
                t = s + length
                best, arg = neg, s
                for r in range(s, t):
                    value = complete[s][r][1] + complete[r + 1][t][0]
                    if value > best:
                        best, arg = value, r
                if s > 0:
                    incomplete[s][t][0] = best + score[t][s]
                iback[s][t][0] = arg
                incomplete[s][t][1] = best + score[s][t]
                iback[s][t][1] = arg
                best, arg = neg, s
                for r in range(s, t):
                    value = complete[s][r][0] + incomplete[r][t][0]
                    if value > best:
                        best, arg = value, r
                complete[s][t][0] = best
                cback[s][t][0] = arg
                best, arg = neg, t
                for r in range(s + 1, t + 1):
                    value = incomplete[s][r][1] + complete[r][t][1]
                    if value > best:
                        best, arg = value, r
                complete[s][t][1] = best
                cback[s][t][1] = arg
        heads = [0] * size
        stack = [('c', 0, n, 1)]
        while stack:
            kind, s, t, direction = stack.pop()
            if s == t:
                continue
            if kind == 'c':
                r = cback[s][t][direction]
                if direction == 0:
                    stack.append(('c', s, r, 0)); stack.append(('i', r, t, 0))
                else:
                    stack.append(('i', s, r, 1)); stack.append(('c', r, t, 1))
            else:
                r = iback[s][t][direction]
                if direction == 0:
                    heads[s] = t
                else:
                    heads[t] = s
                stack.append(('c', s, r, 1)); stack.append(('c', r + 1, t, 0))
        return heads[1:]

    def parse_sentence(self, text: str) -> dict | None:
        if not self.syntax_model['sentences']:
            return None
        return self.parse_words(self.split_words(text))

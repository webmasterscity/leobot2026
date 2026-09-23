"""G-29: word classes and syntactic dependencies learned only by counting.

Demonstrations are sentences with word classes and heads.  A trigram hidden
Markov tagger with a suffix model for unknown words (after TnT, Brants 2000)
and an arc-factored dependency scorer decoded with Eisner's projective
algorithm (Eisner 1996) are compiled from counts: no neural network,
perceptron or gradient.  Arc scores are smoothed log-ratios between how often a
configuration is a real arc and how often it was an opportunity for one.
"""
from __future__ import annotations

import math
import re

MAX_PARSE = 60
LEXICAL_MIN = 3
SUFFIX_MAX = 5
SUFFIX_FREQ = 10
BEAM = 12
ARC_SMOOTHING = 2.0
LABEL_SMOOTHING = 3.0
_WORD = re.compile(r'\w+|[^\w\s]')


def _empty_syntax() -> dict:
    return {'sentences': 0, 'tags': {}, 'bigrams': {}, 'trigrams': {}, 'lexicon': {},
            'suffixes': {}, 'word_counts': {}, 'arcs': {}, 'opportunities': {},
            'arc_total': 0, 'opportunity_total': 0, 'compiled': False, 'labels': {}}


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
    def observe_parsed_sentence(self, words, tags, heads, labels=None) -> dict:
        """Learn from one annotated sentence (heads are 1-based, 0 = root);
        dependency functions are learned too when the demonstration has them."""
        if not (len(words) == len(tags) == len(heads)) or not words:
            return {'status': 'syntax_example_rejected'}
        if labels is not None and len(labels) != len(words):
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
        if labels is not None:
            table = model.setdefault('labels', {})
            for d, label in enumerate(labels, 1):
                for context in self._label_contexts(d, heads[d - 1], lowered, tags, heads,
                                                    model['word_counts'], True):
                    row = table.setdefault(context, {})
                    row[label] = row.get(label, 0) + 1
        return {'status': 'syntax_example_learned'}

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
        if lexical:
            contexts.append(f'5\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{distance}\x1f{marker}')
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
        head_tag = tags[h - 1] if h else 'ROOT'
        dep_tag = tags[d - 1]
        direction = 'R' if h < d else 'L'
        distance = _distance(h - d) if h else 'root'
        low, high = (h, d) if h < d else (d, h)
        between = tags[low:high - 1] if h else ()
        verb = 'v' if 'VERB' in between or 'AUX' in between else '-'
        punct = 'p' if 'PUNCT' in between else '-'
        features = [f'a\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{distance}',
                    f'b\x1f{head_tag}\x1f{dep_tag}\x1f{direction}\x1f{verb}{punct}']
        head_word = words[h - 1] if h else '<root>'
        dep_word = words[d - 1]
        if h and counts.get(head_word, 0) >= LEXICAL_MIN:
            features.append(f'c\x1f{head_word}\x1f{dep_tag}\x1f{direction}')
        if counts.get(dep_word, 0) >= LEXICAL_MIN:
            features.append(f'd\x1f{head_tag}\x1f{dep_word}\x1f{direction}')
        return features

    def consolidate_syntax(self) -> dict:
        """Compile suffix statistics and interpolation weights from the counts."""
        model = self.syntax_model
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
        return {t: math.log(p / (model['tags'][t] / total)) for t, p in estimate.items() if p > 0}

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
    def _arc_score(self, feature: str, prior: float) -> float:
        model = self.syntax_model
        arcs = model['arcs'].get(feature, 0)
        chances = model['opportunities'].get(feature, 0)
        rate = (arcs + ARC_SMOOTHING * prior) / (chances + ARC_SMOOTHING)
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
                total = 0.0
                for feature in self._arc_features(h, d, lowered, tags, model['word_counts']):
                    value = memo.get(feature)
                    if value is None:
                        value = memo[feature] = self._arc_score(feature, prior)
                    total += value
                score[h][d] = total
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
        return self.parse_words(_WORD.findall(text))

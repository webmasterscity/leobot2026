"""G-48: which path of a sentence answers which path of a question, learned from worked examples.

In a worked example (context, question, answer) the question and the sentence
holding the answer are parsed; the question's content words are aligned with
the sentence by dictionary form (one occurrence each, the one nearest to the
answer).  For each aligned word (an anchor) two paths are recorded as
sequences of functions with direction in the enhanced tree with shared
subjects: the question's, from the head of the interrogative phrase to the
anchor, with the dictionary form of each unaligned content word on the way
(«llamar»); and the sentence's, from the head of the answer to the anchor,
functions only.  Pairs seen often enough become correspondences (after DIRT,
Lin & Pantel 2001; Cui et al. 2005; Shen & Klakow 2006, all symbolic).  They
answer an open question only when structural alignment finds nothing: a
candidate is valid when every anchor's pair of paths was learned.
"""
from __future__ import annotations

import math
from collections import deque

from .reading import FUNCTION_TAGS, _TOKEN, _is_word

PATH_STEPS = 4          # longest path kept, in steps
PATH_SUPPORT = 3        # worked examples before a pair of paths is kept
PATH_SHARE = 0.1        # ... and its share among the sentence paths of its question path


def _base(label) -> str:
    return str(label).split(':')[0]


class PathMixin:
    """Mixed into Bot; counts live in ``reading_model['path_pairs']``."""

    # ----- trees and paths ------------------------------------------------
    def _parse_text(self, text: str):
        words = self.split_words(text)
        parse = self.parse_words(words)
        if not parse or parse.get('status') != 'parsed_syntax':
            return None
        return words, parse['tags'], parse['heads'], parse.get('labels') or [None] * len(words)

    def _labeled_links(self, heads, labels):
        """Directed, labelled links of the enhanced tree with shared subjects:
        for each word, (neighbour, step) with step '^f' going up from a
        dependent with function f and 'vf' going down to one."""
        enhanced, elabels = self._enhanced(heads, labels)
        links = [[] for _ in heads]
        for d, h in enumerate(enhanced):
            if h:
                links[d].append((h - 1, '^' + _base(elabels[d])))
                links[h - 1].append((d, 'v' + _base(elabels[d])))
        for d, h in enumerate(heads):
            if labels[d] == 'conj' and h and not any(heads[k] == d + 1 and _base(labels[k]) == 'nsubj'
                                                     for k in range(len(heads))):
                for k in range(len(heads)):
                    if heads[k] == h and _base(labels[k]) == 'nsubj':
                        links[d].append((k, 'vnsubj'))
                        links[k].append((d, '^nsubj'))
        return links

    @staticmethod
    def _path(links, start, goal):
        """The shortest path of steps between two words (None if too long)."""
        if start == goal:
            return []
        before, queue = {start: None}, deque([start])
        while queue:
            node = queue.popleft()
            for other, step in links[node]:
                if other in before:
                    continue
                before[other] = (node, step)
                if other == goal:
                    steps, cur = [], goal
                    while before[cur] is not None:
                        prev, s = before[cur]
                        steps.append((s, cur)); cur = prev
                    steps.reverse()
                    return steps if len(steps) <= PATH_STEPS else None
                queue.append(other)
        return None

    def _question_path(self, qtree, qlinks, start, anchor, aligned) -> str | None:
        words, tags, _, _ = qtree
        steps = self._path(qlinks, start, anchor)
        if steps is None:
            return None
        out = []
        for k, (step, node) in enumerate(steps):
            out.append(step)
            if k + 1 < len(steps) and tags[node] not in FUNCTION_TAGS and node not in aligned:
                out.append(self.lemma_key(words[node]))
        return ' '.join(out)

    def _sentence_path(self, slinks, start, anchor) -> str | None:
        steps = self._path(slinks, start, anchor)
        return None if steps is None else ' '.join(step for step, _ in steps)

    def _gap_head(self, qtree):
        """The asking word of a question and the head of its phrase (its noun)."""
        words, tags, _, _ = qtree
        q = self.asking_word(words, tags)
        if q is None:
            return None, None
        noun = q + 1 if q + 1 < len(words) and tags[q + 1] == 'NOUN' else None
        return q, (noun if noun is not None else q)

    # ----- learning -------------------------------------------------------
    def observe_answer_paths(self, context: str, question: str, answer: str) -> dict:
        """Learn the pairs of paths of one worked example (nothing of its text is kept)."""
        if not self.syntax_model.get('compiled') or not self.syntax_model.get('interrogatives'):
            return {'status': 'answer_paths_skipped', 'reason': 'no_syntax'}
        sentence = next((s for s in self._document_sentences(context) if answer and answer in s), None)
        qtree = self._parse_text(question) if sentence else None
        stree = self._parse_text(sentence) if qtree else None
        if stree is None:
            return {'status': 'answer_paths_skipped', 'reason': 'no_parse'}
        q, start = self._gap_head(qtree)
        if q is None:
            return {'status': 'answer_paths_skipped', 'reason': 'no_asking_word'}
        swords, stags, sheads, slabels = stree
        target = [w.lower() for w in self.split_words(answer) if _is_word(w)]
        low = [w.lower() for w in swords]
        span = next((list(range(k, k + len(target))) for k in range(len(low) - len(target) + 1)
                     if target and low[k:k + len(target)] == target), None)
        if span is None:
            return {'status': 'answer_paths_skipped', 'reason': 'answer_not_found'}
        inside = set(span)
        head = next((k for k in span if sheads[k] - 1 not in inside), span[0])
        slinks = self._labeled_links(sheads, slabels)
        qwords, qtags, qheads, qlabels = qtree
        qlinks = self._labeled_links(qheads, qlabels)
        interrogatives = set(self.syntax_model.get('interrogatives', ()))
        sets = [self.lemma_keys(w) for w in swords]
        anchors = {}
        for i, (w, t) in enumerate(zip(qwords, qtags)):
            if i in (q, start) or t in FUNCTION_TAGS or not _is_word(w) or w.lower() in interrogatives:
                continue
            key = self.lemma_key(w)
            places = [j for j in range(len(swords)) if key in sets[j] and j not in inside]
            if places:
                nearest = min(places, key=lambda j: (len(self._path(slinks, head, j) or [0] * 99), j))
                anchors[i] = nearest
        table = self.reading_model.setdefault('path_pairs', {})
        pairs = 0
        for i, j in sorted(anchors.items()):
            qpath = self._question_path(qtree, qlinks, start, i, set(anchors))
            spath = self._sentence_path(slinks, head, j)
            if qpath is None or spath is None:
                continue
            row = table.setdefault(qpath, {})
            row[spath] = row.get(spath, 0) + 1
            pairs += 1
        return {'status': 'answer_paths_learned', 'pairs': pairs}

    def consolidate_answer_paths(self) -> dict:
        """Keep the pairs seen often enough, as log-probabilities."""
        learned = {}
        for qpath, row in self.reading_model.get('path_pairs', {}).items():
            total = sum(row.values())
            kept = {s: round(math.log(c / total), 6) for s, c in row.items()
                    if c >= PATH_SUPPORT and c >= PATH_SHARE * total}
            if kept:
                learned[qpath] = kept
        self.reading_model['learned_paths'] = learned
        return {'status': 'answer_paths_consolidated', 'question_paths': len(learned)}

    # ----- answering ------------------------------------------------------
    def _path_candidates(self, question, qtree, q, noun, categories):
        """G-48: candidates by learned correspondence of paths, for sentences
        holding the question's nominal anchors (the verb may be missing)."""
        learned = self.reading_model.get('learned_paths')
        if not learned:
            return []
        words, tags, heads, labels = qtree
        start = noun if noun is not None else q
        interrogatives = set(self.syntax_model.get('interrogatives', ()))
        anchors = {self._word_key(w): i for i, (w, t) in enumerate(zip(words, tags))
                   if i not in (q, start) and t in ('NOUN', 'PROPN', 'NUM', 'ADJ') and _is_word(w)
                   and w.lower() not in interrogatives}
        if not anchors:
            return []
        content = {self._word_key(w): i for i, (w, t) in enumerate(zip(words, tags))
                   if i not in (q, start) and t not in FUNCTION_TAGS and _is_word(w)
                   and w.lower() not in interrogatives}
        index = self._reading_index()
        lists = sorted((index.get(self._search_key(words[i]), ()) for i in anchors.values()), key=len)
        positions = set(lists[0]).intersection(*lists[1:])
        qlinks = self._labeled_links(heads, labels)
        structure = self._open_structure(qtree, q, anchors, noun, False)
        negators = set(self.syntax_model.get('negators', ()))
        polarity = sum(w.lower() in negators for w in words) % 2
        out = []
        for position in sorted(positions):
            row = self.reading_utterances[position]
            tree = self._tree_of(row)
            if tree is None:
                continue
            swords, stags, sheads, slabels = tree
            sets = self._key_sets(swords)
            present = set().union(*sets) if sets else set()
            slinks = self._labeled_links(sheads, slabels)
            enhanced, _ = self._graph(sheads, slabels)
            aligned_q = {i for k, i in content.items() if k in present}
            for placement in self._placements(structure, tree, sets):
                placed = set(placement.values())
                negated = sum(swords[k].lower() in negators and sheads[k] - 1 in placed
                              for k in range(len(swords))) % 2
                if negated != polarity or self._subordinate(enhanced, stags, sheads, placed):
                    continue
                qpaths = {k: self._question_path(qtree, qlinks, start, anchors[k], aligned_q) for k in placement}
                everyone = getattr(self, 'path_quorum', 'all') == 'all'
                known = {k for k, p in qpaths.items() if p is not None and p in learned}
                if (everyone and len(known) < len(qpaths)) or not known:
                    continue
                for node in range(len(swords)):
                    if node in placed or stags[node] in FUNCTION_TAGS or not _is_word(swords[node]):
                        continue
                    span, stack = [], [node]
                    while stack:
                        m = stack.pop(); span.append(m)
                        stack.extend(d for d in range(len(sheads)) if sheads[d] == m + 1)
                    if placed & set(span):
                        continue
                    score = 0.0
                    for k, j in placement.items():
                        if k not in known:
                            continue
                        spath = self._sentence_path(slinks, node, j)
                        if spath is None or spath not in learned[qpaths[k]]:
                            break
                        score += learned[qpaths[k]][spath]
                    else:
                        text = self._span_text(row, swords, span)
                        if text:
                            out.append(((-score,), text, row))
        return out

"""G-106/G-107: general knowledge taught from human-made resources.

Relations between words (``observe_relation``) are kept as dictionary forms, in
compact rows: ``{relation: {head: 'tail^source;tail^source'}}``.  The relation
names are whatever the source calls them; the engine holds no list of words and
no rule about any word.  What the engine learns about each kind of relation is
counted: how often a word related that way to a customer's word is in the right
answer (G-106, ``context_model['knowledge_share']``), which fixed words the
people who wrote the source used to say it (``observe_relation_template``) and
how often its paths close (``observe_relation_closure``).

Answering general questions (G-107) is kept apart from answering from a loaded
business text: ``Bot.answer`` never reads this store to state a fact.
"""
from __future__ import annotations

import math
import re

from .context import _plain, _TOKEN

SLOT = re.compile(r'\{([01])\}')
CHAIN_STEPS = 6
CHAIN_RATE = 0.05
CHAIN_LIFT = 5.0
ANSWERS = 3
ANSWER_TAILS = 6


def _empty_knowledge() -> dict:
    return {'edges': {}, 'display': {}, 'sources': [], 'templates': {}, 'closure': {}, 'count': 0}


class KnowledgeMixin:
    """Mixed into Bot; state lives in ``knowledge_model``."""

    # ----- teaching -----------------------------------------------------
    def _knowledge_term(self, phrase: str) -> str:
        return ' '.join(self.context_terms(phrase)) if phrase else ''

    def observe_relation(self, a: str, relation: str, b: str, source: str) -> bool:
        """Keep «a relation b» as dictionary forms, with the source's name."""
        model = self.knowledge_model
        head, tail = self._knowledge_term(a), self._knowledge_term(b)
        if not head or not tail or head == tail or not relation:
            return False
        if source not in model['sources']:
            model['sources'].append(source)
        mark = model['sources'].index(source)
        rows = model['edges'].setdefault(relation, {})
        row = rows.get(head, '')
        if any(item.rsplit('^', 1)[0] == tail for item in row.split(';') if item):
            return False
        rows[head] = f'{row};{tail}^{mark}' if row else f'{tail}^{mark}'
        display = model['display']
        for term, words in ((head, a), (tail, b)):
            display.setdefault(term, words)
        model['count'] += 1
        self._knowledge_cache = None
        return True

    def observe_relation_template(self, relation: str, template: str) -> None:
        """A way people wrote this relation, with ``{0}`` and ``{1}`` for its two ends."""
        rows = self.knowledge_model['templates'].setdefault(relation, [])
        if template not in rows and set(SLOT.findall(template)) == {'0', '1'}:
            rows.append(template)
            self._knowledge_cache = None

    def observe_relation_closure(self, relation: str, closed: int, paths: int) -> None:
        """Counted paths a→b→c of this relation and how many of them an asserted a→c closes."""
        self.knowledge_model['closure'][relation] = [int(closed), int(paths)]
        self._knowledge_cache = None

    # ----- index --------------------------------------------------------
    def _knowledge(self) -> dict:
        cache = getattr(self, '_knowledge_cache', None)
        if cache is None:
            forward, backward = {}, {}
            for relation, rows in self.knowledge_model['edges'].items():
                ahead, behind = forward.setdefault(relation, {}), backward.setdefault(relation, {})
                for head, row in rows.items():
                    for item in row.split(';'):
                        tail, mark = item.rsplit('^', 1)
                        ahead.setdefault(head, []).append((tail, int(mark)))
                        behind.setdefault(tail, []).append((head, int(mark)))
            cache = {'forward': forward, 'backward': backward, 'chained': self._chained()}
            self._knowledge_cache = cache
        return cache

    def _chained(self) -> set:
        """Relations whose counted closure rate is at least CHAIN_RATE and CHAIN_LIFT times
        the median rate of the other relations (G-107, preregistered)."""
        rates = {r: c / p for r, (c, p) in self.knowledge_model['closure'].items() if p}
        out = set()
        for relation, rate in rates.items():
            others = sorted(v for r, v in rates.items() if r != relation)
            median = others[len(others) // 2] if others else 0.0
            if rate >= CHAIN_RATE and rate >= CHAIN_LIFT * median:
                out.add(relation)
        return out

    def knowledge_related(self, term: str) -> list[tuple[str, str]]:
        """G-106: the terms related to this one and the kind of link: ``Rel>`` (term Rel other),
        ``Rel<`` (other Rel term) and ``IsA>>`` (a hypernym of a hypernym)."""
        if not getattr(self, 'general_knowledge', True) or not self.knowledge_model['count']:
            return []
        index = self._knowledge()
        out = []
        for relation, table in index['forward'].items():
            for tail, _ in table.get(term, ()):
                out.append((tail, relation + '>'))
        for relation, table in index['backward'].items():
            for head, _ in table.get(term, ()):
                out.append((head, relation + '<'))
        up = index['forward'].get('IsA', {})
        for parent, _ in up.get(term, ()):
            for grand, _ in up.get(parent, ()):
                if grand != term:
                    out.append((grand, 'IsA>>'))
        return out

    def _chain(self, term: str, relation: str, target: str | None = None):
        """Breadth-first path along a chained relation (at most CHAIN_STEPS links)."""
        table = self._knowledge()['forward'].get(relation, {})
        seen, frontier = {term: None}, [term]
        for _ in range(CHAIN_STEPS):
            nxt = []
            for node in frontier:
                for tail, mark in table.get(node, ()):
                    if tail not in seen:
                        seen[tail] = (node, mark)
                        if tail == target:
                            path = [tail]
                            while seen[path[-1]] is not None:
                                path.append(seen[path[-1]][0])
                            return list(reversed(path))
                        nxt.append(tail)
            frontier = nxt
            if not frontier:
                break
        return None if target is not None else [t for t in seen if t != term]

    # ----- answering general questions (G-107) ---------------------------
    def _template_words(self) -> dict:
        """The fixed words (dictionary forms) of each relation's human templates, and how
        many relations use each word (rarer words weigh more)."""
        cache = self._knowledge()
        if 'template_words' not in cache:
            words = {r: set(self.context_terms(SLOT.sub(' ', ' '.join(rows))))
                     for r, rows in self.knowledge_model['templates'].items()}
            spread: dict = {}
            for fixed in words.values():
                for w in fixed:
                    spread[w] = spread.get(w, 0) + 1
            cache['template_words'] = (words, spread)
        return cache['template_words']

    def _known_spans(self, terms: list[str], content=None) -> list[tuple[int, int, str]]:
        """Longest runs of the question's terms that name something in the store.  With
        ``content`` (one flag per term), a run must be made of content words only."""
        index = self._knowledge()
        known = lambda t: any(t in table for table in index['forward'].values()) or \
            any(t in table for table in index['backward'].values())
        spans, i = [], 0
        while i < len(terms):
            for j in range(min(len(terms), i + 4), i, -1):
                phrase = ' '.join(terms[i:j])
                if (content is None or all(content[i:j])) and known(phrase):
                    spans.append((i, j, phrase))
                    i = j
                    break
            else:
                i += 1
        return spans

    def _content_flags(self, question: str):
        """G-107: which words of the question carry content (noun, proper noun or adjective
        in the classes learned from AnCora); function words name nothing."""
        words = [w for w in self.split_words(question)]
        tags = self.tag_words(words) if words and self.syntax_model.get('sentences') else None
        if not tags:
            return None
        return [tag in ('NOUN', 'PROPN', 'ADJ') for w, tag in zip(words, tags) if w[:1].isalnum()]

    def includes(self, lower: str, upper: str) -> bool:
        """G-107: the store says ``lower`` is a kind of ``upper`` (directly, or along a chained relation)."""
        if not getattr(self, 'general_knowledge', True) or not self.knowledge_model['count']:
            return False
        index = self._knowledge()
        if any(t == upper for t, _ in index['forward'].get('IsA', {}).get(lower, ())):
            return True
        return 'IsA' in index['chained'] and self._chain(lower, 'IsA', upper) is not None

    def _general_rows(self, names: list[str]) -> list[dict]:
        """The store's relations of the named things, said with every template people wrote for
        each relation (at most ANSWER_TAILS ends per relation), as rows a reader can read."""
        index, sources, rows = self._knowledge(), self.knowledge_model['sources'], []
        for name in names:
            for relation, templates in sorted(self.knowledge_model['templates'].items()):
                for tail, mark in index['forward'].get(relation, {}).get(name, [])[:ANSWER_TAILS]:
                    for template in templates:
                        text = self._say_with(template, name, tail)
                        rows.append({'source': f'saber general ({sources[mark]}):{len(rows) + 1}',
                                     'document': 'saber general', 'text': text, 'tokens': _TOKEN.findall(text)})
        return rows

    def _say_with(self, template: str, head: str, tail: str) -> str:
        text = template.replace('{0}', self._display(head)).replace('{1}', self._display(tail)).strip()
        text = text[:1].upper() + text[1:]
        return text if text[-1:] in '.!?' else text + '.'

    def _neighbours(self, term: str) -> set:
        """Every term one relation away from this one, in either direction."""
        cache = self._knowledge().setdefault('neighbours', {})
        found = cache.get(term)
        if found is None:
            index = self._knowledge()
            found = set()
            for side in ('forward', 'backward'):
                for table in index[side].values():
                    found.update(t for t, _ in table.get(term, ()))
            found.discard(term)
            cache[term] = found
        return found

    def answer_by_intersection(self, question: str) -> dict | None:
        """G-107b: the term that the question's content words point to together (intersection
        search in semantic memory).  Each word linked to a candidate adds 1 / log(2 + its number
        of links); the best candidate is said only when it is linked to at least two different
        words of the question and strictly ahead of the second."""
        if not getattr(self, 'general_knowledge', True) or not self.knowledge_model['count']:
            return None
        words = self.split_words(question)
        negators = self.negator_words()
        if any(word.lower() in negators for word in words):
            return None
        if self.asking_word(words) is None:
            return None
        tags = self.tag_words(words) if words and self.syntax_model.get('sentences') else None
        if not tags:
            return None
        pairs = [(self._term(w), tag) for w, tag in zip(words, tags) if w[:1].isalnum() and tag in ('NOUN', 'PROPN', 'ADJ', 'VERB')]
        nouns = {t for t, tag in pairs if tag == 'NOUN'}
        asked = [t for t in dict.fromkeys(t for t, _ in pairs) if self._neighbours(t)]
        if len(asked) < 2:
            return None
        # The answer is a kind of something the question names (one or two «is a» links below it):
        # that word is its class; the other words must point to it.
        below = self._knowledge()['backward'].get('IsA', {})
        kinds: dict = {}
        for term in asked:
            if term not in nouns:
                continue
            for child, _ in below.get(term, ()):
                kinds.setdefault(child, term)
                for grandchild, _ in below.get(child, ()):
                    kinds.setdefault(grandchild, term)
        score, support = {}, {}
        for term in asked:
            links = self._neighbours(term)
            weight = 1.0 / math.log(2 + len(links))
            for other in links:
                if other in asked or other not in kinds or kinds[other] == term:
                    continue
                score[other] = score.get(other, 0.0) + weight
                support.setdefault(other, []).append(term)
        ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
        if not ranked or (len(ranked) > 1 and ranked[1][1] >= ranked[0][1]):
            return None
        best = ranked[0][0]
        support[best] = [kinds[best]] + support[best]
        because = ', '.join(self._display(t) for t in support[best])
        return {'text': f'Por lo que sé en general: {self._display(best)} (lo relaciono con {because}).',
                'status': 'general_intersection', 'answer': self._display(best), 'links': support[best]}

    def answer_general_by_reading(self, question: str) -> dict | None:
        """G-107 (variant B): the named things' relations are said with the people's templates
        and the learned reader answers from them, as from any text it has read."""
        if not getattr(self, 'general_knowledge', True) or not self.knowledge_model['count']:
            return None
        terms = self.context_terms(question)
        flags = self._content_flags(question)
        if flags is None or len(flags) != len(terms):
            return None
        names = [phrase for _, _, phrase in self._known_spans(terms, flags)]
        rows = self._general_rows(names)
        if not rows:
            return None
        view = object.__new__(type(self))
        view.__dict__.update(self.__dict__)
        view.reading_utterances = rows
        view._reading_index_cache = None
        view.general_route = None
        answer = view._answer_literally(question)
        if not answer or answer.get('status') in ('literal_unknown', 'unknown', None):
            return None
        answer = dict(answer)
        answer['status'] = 'general_' + answer['status']
        return answer

    def _display(self, term: str) -> str:
        return self.knowledge_model['display'].get(term, term)

    def _say(self, relation: str, head: str, tail: str) -> str:
        template = self.knowledge_model['templates'][relation][0]
        text = template.replace('{0}', self._display(head)).replace('{1}', self._display(tail))
        return text[:1].upper() + text[1:]

    def answer_general(self, question: str) -> dict | None:
        """G-107: a question about the world answered from the general store, or None.
        The relation asked for is the one whose people-written templates share the most
        (rarity-weighted) fixed words with what the question says besides the thing it
        names; a tie between relations is not answered."""
        if not getattr(self, 'general_knowledge', True) or not self.knowledge_model['count']:
            return None
        # Templates select a positive relation; they do not establish the scope of a negation.
        words = self.split_words(question)
        negators = self.negator_words()
        if any(word.lower() in negators for word in words):
            return None
        terms = self.context_terms(question)
        flags = self._content_flags(question)
        if flags is None or len(flags) != len(terms):
            return None
        spans = self._known_spans(terms, flags)
        if not spans:
            return None
        words, spread = self._template_words()
        inside = {k for i, j, _ in spans for k in range(i, j)}
        rest = {t for k, t in enumerate(terms) if k not in inside}
        index = self._knowledge()
        scored = []
        for relation, fixed in words.items():
            score = sum(1.0 / spread[w] for w in rest & fixed)
            if score > 0:
                scored.append((score, relation))
        if not scored:
            return None
        scored.sort(key=lambda x: (-x[0], x[1]))
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None
        relation = scored[0][1]
        names = [phrase for _, _, phrase in spans]
        forward = index['forward'].get(relation, {})
        sources = self.knowledge_model['sources']
        if len(names) >= 2:
            head, tail = names[0], names[-1]
            direct = [t for t, _ in forward.get(head, ())]
            path = [head, tail] if tail in direct else (
                self._chain(head, relation, tail) if relation in index['chained'] else None)
            if path:
                steps = '; '.join(self._say(relation, a, b).rstrip('.') for a, b in zip(path, path[1:]))
                return {'text': f'Sí. Por lo que sé en general: {steps}.', 'status': 'general_yes',
                        'relation': relation, 'path': path}
            return None
        head = names[0]
        found = forward.get(head, [])
        if not found:
            return None
        shown = found[:ANSWERS]
        said = '; '.join(self._say(relation, head, tail).rstrip('.') for tail, _ in shown)
        return {'text': f'Por lo que sé en general: {said}.', 'status': 'general',
                'relation': relation, 'answers': [self._display(t) for t, _ in shown],
                'sources': sorted({sources[m] for _, m in shown})}

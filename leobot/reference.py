"""G-47: what «su», «él», «la», «lo» or an omitted subject refer to.

A sentence said in conversation is aligned with a copy of its tree in which
each third-person pronoun is replaced by its antecedent, each third-person
possessive becomes «de» + antecedent under the possessed noun, and a singular
third-person verb without a subject gets its antecedent as subject.  Person,
number, gender and kind of reference are the features learned from the
treebank (``morph_table``); verbs that almost never take a subject there are
impersonal.  The antecedent is the most prominent compatible mention: for a
possessive, the subject of its own clause before it; then earlier mentions of
the same sentence, nearest first; then the mentions of the previous sentences,
most recent sentence first and subject first.  The original text is kept and
shown; only alignment uses the copy.
"""
from __future__ import annotations

WINDOW = 5          # previous conversation sentences searched for an antecedent
RANK = {'nsubj': 0, 'obj': 1, 'iobj': 2, 'obl': 3, 'nmod': 4}
KEEP = frozenset({'det', 'amod', 'nmod', 'flat', 'appos', 'compound', 'nummod'})   # under the mention's noun
INNER = frozenset({'det', 'amod', 'flat', 'compound', 'nummod', 'case'})          # under what it keeps


def _feature(features: set, name: str):
    return next((f.split('=', 1)[1] for f in sorted(features) if f.startswith(name + '=')), None)


class ReferenceMixin:
    """Mixed into Bot; resolved copies live in the conversation rows."""

    @staticmethod
    def _conversational(row) -> bool:
        return str(row.get('document', '')).startswith('conversación:')

    def _row_tree(self, row):
        """The tree a remembered sentence is aligned with (G-47: with its
        references resolved when it was said in conversation)."""
        if self._conversational(row) and getattr(self, 'reference_resolution', True) \
                and self.syntax_model.get('morph_table'):
            self._resolve_references()
            if row.get('resolved'):
                return tuple(row['resolved'][:4])
        return self._utterance_tree(row['text'])

    def _resolve_references(self) -> None:
        """Resolve, in order, every conversation sentence not yet resolved;
        the result is stored in its row, so it does not depend on when the
        question comes."""
        if not getattr(self, 'reference_resolution', True) or not self.syntax_model.get('morph_table'):
            return
        rows = self.reading_utterances
        # G-54: the first person is who speaks; once the conversation says that
        # person's name, every sentence is resolved again with it.
        speaker = self._speaker()
        marker = ' '.join(w for w, _, _, _ in self._copy(*speaker)) if speaker is not None else None
        applied = self.__dict__.get('_speaker_applied')
        if applied != (id(rows), marker):
            if any(self._conversational(row) and row.get('referenced') and row.get('speaker') != marker for row in rows):
                for row in rows:
                    if self._conversational(row):
                        for key in ('referenced', 'resolved', 'referents', 'genders', 'speaker', 'history_tree'):
                            row.pop(key, None)
                self.__dict__['_reference_cursor'] = None
            self.__dict__['_speaker_applied'] = (id(rows), marker)
        state = self.__dict__.get('_reference_cursor')
        start = state[1] if state and state[0] == id(rows) and state[1] <= len(rows) else 0
        pending = [p for p in range(start, len(rows)) if self._conversational(rows[p])
                   and not rows[p].get('referenced')]
        if pending:
            # G-47b: genders the conversation taught (a name taken up by «ella» is feminine).
            learned: dict = {}
            for row in rows[:pending[0]]:
                if self._conversational(row):
                    learned.update(row.get('genders', {}))
            history, p = [], pending[0] - 1
            while p >= 0 and len(history) < WINDOW:
                if self._conversational(rows[p]):
                    tree = self._history_tree(rows[p])
                    if tree is not None:
                        history.insert(0, tree)
                p -= 1
            for p in range(pending[0], len(rows)):
                row = rows[p]
                if not self._conversational(row):
                    continue
                tree = self._utterance_tree(row['text'])
                if not row.get('referenced') and tree is not None:
                    before = dict(learned)
                    resolved, added, plain = self._resolve_speaking(tree, history, learned, speaker)
                    if learned != before:
                        row['genders'] = {k: v for k, v in learned.items() if before.get(k) != v}
                    if added:
                        row['resolved'] = [list(part) for part in resolved]
                        row['referents'] = added
                        self._index_extend(p, added)
                    if plain is not resolved:
                        row['history_tree'] = [list(part) for part in plain[:4]]
                    if marker is not None:
                        row['speaker'] = marker
                row['referenced'] = True
                current = self._history_tree(row) if tree is not None else None
                if current is not None:
                    history.append(current)
                    del history[:-WINDOW]
        self.__dict__['_reference_cursor'] = (id(rows), len(rows))

    def _history_tree(self, row):
        """The tree later sentences look back at: resolved, but without the
        speaker's name (G-54), since a third person never refers to who speaks."""
        if row.get('history_tree'):
            return tuple(row['history_tree'])
        return tuple(row['resolved'][:4]) if row.get('resolved') else self._utterance_tree(row['text'])

    # ----- who speaks (G-54) ----------------------------------------------
    def _first_person_verb(self, words, tags, labels, children, v) -> bool:
        """Whether node ``v`` heads a clause whose finite verb (itself, or its
        copula or auxiliary) is learned as first person singular."""
        if labels[v] in ('cop', 'aux'):
            return False
        for k in [v] + [c for c in children[v] if labels[c] in ('cop', 'aux')]:
            if tags[k] in ('VERB', 'AUX'):
                # A verb form with a learned person is finite.
                if {'Person=1', 'Number=Sing'} <= self.morphology(words[k], tags[k]):
                    return True
        return False

    def _first_person_edits(self, tree, source) -> dict:
        """G-54: the edits that put ``source`` (a mention) where the tree speaks
        in the first person singular, by the learned features: a personal
        pronoun, a possessive, and a first-person verb without a subject.  A
        first-person object of a first-person verb («me llamo») is the subject
        itself and is left alone."""
        words, tags, heads, labels = tree
        n = len(words)
        children = [[] for _ in range(n)]
        for d, h in enumerate(heads):
            if h:
                children[h - 1].append(d)
        edits = {}
        for i in range(n):
            features = self.morphology(words[i], tags[i])
            if not {'Person=1', 'Number=Sing', 'PronType=Prs'} <= features:
                continue
            if 'Poss=Yes' in features:
                if heads[i] and tags[heads[i] - 1] in ('NOUN', 'PROPN'):
                    edits[i] = ('possessive', source)
            elif tags[i] == 'PRON' and (str(labels[i]).startswith('nsubj') or not heads[i] or not
                                        self._first_person_verb(words, tags, labels, children, heads[i] - 1)):
                edits[i] = ('pronoun', source)
        for v in range(n):
            governed = [v] + [k for k in children[v] if labels[k] in ('cop', 'aux')]
            if self._first_person_verb(words, tags, labels, children, v) and not any(
                    str(labels[k]).startswith(('nsubj', 'csubj')) for g in governed for k in children[g]):
                edits[('subject', v)] = ('subject', source)
        return edits

    def _speaker(self):
        """G-54: the name of who speaks, as a mention (tree, node): the other
        side of an identity (G-51: apposition, copula or a learned identity
        verb) whose one side is the first person; the last one said.  None if
        the conversation has not said it."""
        rows = self.reading_utterances
        if not getattr(self, 'speaker', True) or not self.syntax_model.get('morph_table') \
                or not hasattr(self, '_identity_pairs'):
            return None
        # Memory only grows by appending (G-41): only the rows not yet seen are looked at.
        cache = self.__dict__.get('_speaker_cache')
        if cache is None or cache[0] != id(rows) or cache[1] > len(rows):
            cache = (id(rows), 0, None)
        found = cache[2]
        if cache[1] < len(rows):
            place = (['\x00'], ['PROPN'], [0], ['root'])
            for row in rows[cache[1]:]:
                if not self._conversational(row):
                    continue
                tree = self._utterance_tree(row['text'])
                if tree is None:
                    continue
                edits = {k: e for k, e in self._first_person_edits(tree, (place, 0)).items() if e[0] != 'possessive'}
                if not edits:
                    continue
                new = self._rebuilt(tree, edits)[0][:4]
                marks = {k for k, w in enumerate(new[0]) if w == '\x00'}
                for a, b in sorted(self._identity_pairs(new)):
                    other = b if a in marks else a if b in marks else None
                    if other is not None and other not in marks and new[1][other] == 'PROPN':
                        found = (new, other)
            self.__dict__['_speaker_cache'] = (id(rows), len(rows), found)
        return found

    # ----- mentions -----------------------------------------------------
    def _agreement(self, words, tags, children, node, learned=None):
        """Gender and number of a mention, from its own form or its determiner
        (G-47b: or, for a name, from how the conversation took it up)."""
        features = self.morphology(words[node], tags[node]) if tags[node] == 'NOUN' else set()
        gender, number = _feature(features, 'Gender'), _feature(features, 'Number')
        for k in children[node]:
            if tags[k] == 'DET':
                det = self.morphology(words[k], 'DET')
                gender = gender or _feature(det, 'Gender')
                number = number or _feature(det, 'Number')
        if gender is None and learned and tags[node] == 'PROPN':
            gender = learned.get(words[node].lower())
        return gender, number

    def _mentions(self, tree):
        """Nominal mentions of a tree (not predicates, not parts of a name),
        ranked subject first, then by function, then left to right.  G-47b: a
        coordinated element has the function of the first one («Elena y
        Marcos» are both subjects)."""
        words, tags, heads, labels = tree
        if getattr(self, 'g47b_structure', True):
            labels = self._enhanced(heads, labels)[1]
        children = [[] for _ in words]
        for d, h in enumerate(heads):
            if h:
                children[h - 1].append(d)
        out = []
        for i, (t, label) in enumerate(zip(tags, labels)):
            if t not in ('NOUN', 'PROPN') or label in ('flat', 'compound', 'appos'):
                continue
            if any(labels[k] == 'cop' for k in children[i]):
                continue
            base = str(label).split(':')[0]
            out.append((RANK.get(base, 5), i, self._agreement(words, tags, children, i)))
        out.sort(key=lambda m: (m[0], m[1]))
        return [(i, agreement) for _, i, agreement in out]

    @staticmethod
    def _copy(tree, node, coordination=False):
        """The mention's words: the noun with its determiners, modifiers,
        name parts and «de» complement, one level deep, as (word, tag, local
        head, label) with local heads.  G-52: with ``coordination``, also the
        elements coordinated with it («Pedro y Luis»)."""
        words, tags, heads, labels = tree
        children = [[] for _ in words]
        for d, h in enumerate(heads):
            if h:
                children[h - 1].append(d)
        keep, stack = [], [node]
        while stack:
            k = stack.pop()
            keep.append(k)
            allowed = KEEP if k == node or labels[k] in ('appos', 'flat') else INNER
            if coordination and k == node:
                allowed = allowed | {'conj'}
            elif coordination and labels[k] == 'conj':
                allowed = KEEP | {'cc'}
            stack.extend(c for c in children[k] if labels[c] in allowed | ({'case'} if k != node else set()))
        keep.sort()
        position = {k: n for n, k in enumerate(keep)}
        return [(words[k], tags[k], position.get(heads[k] - 1) if k != node else None, labels[k]) for k in keep]

    # ----- resolution ---------------------------------------------------
    def _resolve_tree(self, tree, history, learned=None):
        """The tree with its third-person references resolved, and the words added."""
        edits = self._reference_edits(tree, history, learned)
        return self._rebuilt(tree, edits) if edits else (tree, [])

    def _resolve_speaking(self, tree, history, learned, speaker):
        """G-54: the tree resolved, the words added, and the tree without the
        speaker's name (what later sentences look back at)."""
        edits = self._reference_edits(tree, history, learned)
        first = {k: e for k, e in self._first_person_edits(tree, speaker).items()
                 if k not in edits} if speaker is not None else {}
        if not edits and not first:
            return tree, [], tree
        resolved, added = self._rebuilt(tree, {**edits, **first})
        if not first:
            return resolved, added, resolved
        return resolved, added, self._rebuilt(tree, edits)[0] if edits else tree

    def _reference_edits(self, tree, history, learned=None) -> dict:
        words, tags, heads, labels = tree
        n = len(words)
        children = [[] for _ in range(n)]
        for d, h in enumerate(heads):
            if h:
                children[h - 1].append(d)
        own = self._mentions(tree)
        earlier = [self._mentions(t) for t in history]
        edits = {}
        for i in range(n):
            features = self.morphology(words[i], tags[i])
            if 'Person=3' not in features or 'PronType=Prs' not in features or 'Reflex=Yes' in features:
                continue
            possessive = 'Poss=Yes' in features
            if possessive:
                possessed = heads[i] - 1
                if possessed < 0 or tags[possessed] not in ('NOUN', 'PROPN'):
                    continue
            elif tags[i] != 'PRON' or any(str(labels[k]).startswith('acl') for k in children[i]):
                continue            # «lo que …» does not point back
            gender, number = _feature(features, 'Gender'), _feature(features, 'Number')
            if possessive:
                gender = number = None    # «su» agrees with what is possessed
            clause = heads[i] - 1
            case = _feature(features, 'Case') or ''
            doubled = ('obj',) if case == 'Acc' else ('iobj', 'obl') if case == 'Dat' else ()
            if not possessive and clause >= 0 and any(
                    k != i and tags[k] in ('NOUN', 'PROPN') and labels[k] in doubled
                    and (labels[k] != 'obl' or any(words[c].lower() == self.syntax_model.get('dative_case')
                                                   for c in children[k]))
                    for k in children[clause]):
                continue            # a clitic doubling a complement of its own verb («le … a Julián»)
            # A pronoun does not refer to the subject of its own clause
            # (a coordinated clause shares the subject of the first one).
            subject = self._clause_subject(heads, labels, i)
            coarguments = {subject} if subject is not None and not possessive else set()
            inside = set(self._ancestors(heads, i)) | {i}
            # Subjects first: of its own clause (a possessive), of the
            # sentence's earlier clauses, of the previous sentences; then the
            # other mentions of the previous sentences and of its own sentence.
            order = []
            structural = getattr(self, 'g47b_structure', True)
            # G-47b: the possessor of a noun predicated with «ser» is not its subject («Consuelo es su esposa»).
            attribute = possessive and structural and any(labels[k] == 'cop' for k in children[possessed])
            if attribute and subject is not None:
                coarguments = {subject}
            if possessive and not attribute and subject is not None and subject < i and subject != possessed:
                order.append((tree, subject))
            subjects = [k for k in range(i) if str(labels[k]).startswith('nsubj') and tags[k] in ('NOUN', 'PROPN')]
            order += [(tree, k) for k in reversed(subjects)]
            if structural:
                # G-47b, as the G-47 amendment reads: the subjects of the previous
                # sentences (most recent first) before their other mentions.
                recent = list(reversed(range(len(history))))
                order += [(history[past], k) for past in recent for k, _ in earlier[past]
                          if self._is_subject(history[past], k)]
                order += [(history[past], k) for past in recent for k, _ in earlier[past]
                          if not self._is_subject(history[past], k)]
            else:
                for past in reversed(range(len(history))):
                    order += [(history[past], k) for k, _ in earlier[past]]
            order += [(tree, k) for k, _ in sorted(own, key=lambda m: -m[0]) if k < i]
            memory = learned if structural else None
            chosen = self._first_compatible(order, gender, number,
                                            exclude=inside | coarguments | ({possessed} if possessive else set()),
                                            current=tree, learned=memory)
            if chosen is not None:
                edits[i] = ('possessive' if possessive else 'pronoun', chosen)
                source, k = chosen
                if memory is not None and gender and source[1][k] == 'PROPN':
                    memory.setdefault(source[0][k].lower(), gender)
        root = next((d for d, h in enumerate(heads) if not h), None)
        # The subject may hang from the copula or auxiliary (a parser slip).
        governed = [root] + [k for k in children[root] if labels[k] in ('cop', 'aux')] if root is not None else []
        if root is not None and history and not any(str(labels[k]).startswith(('nsubj', 'csubj'))
                                                     for g in governed for k in children[g]):
            finite = self._finite(words, tags, labels, children, root)
            lemma = self.syntax_model.get('lemma_table', {}).get(words[root].lower(), words[root].lower())
            personal = lemma not in set(self.syntax_model.get('impersonal', ()))
            order = [(history[past], k) for past in reversed(range(len(history)))
                     for k, _ in self._mentions(history[past])]
            if finite is not None and 'Person=3' in finite and 'Number=Sing' in finite and personal:
                chosen = self._first_compatible(order, None, 'Sing', exclude=set(), current=tree,
                                                learned=learned if getattr(self, 'g47b_structure', True) else None)
                if chosen is not None:
                    edits[('subject', root)] = ('subject', chosen)
            elif finite is not None and 'Person=3' in finite and 'Number=Plur' in finite and personal \
                    and getattr(self, 'plural_subjects', True):
                # G-52: a plural verb takes the most prominent plural mention: a
                # noun learned as plural or a coordination, copied whole.
                chosen = next(((t, k) for t, k in order if self._plural(t, k)), None)
                if chosen is not None:
                    edits[('subject', root)] = ('subject', chosen + (True,))
        return edits

    def _plural(self, tree, k) -> bool:
        """G-52: a mention that stands for several: learned plural number or a coordination."""
        words, tags, heads, labels = tree
        children = [[] for _ in words]
        for d, h in enumerate(heads):
            if h:
                children[h - 1].append(d)
        if any(labels[c] == 'conj' and tags[c] in ('NOUN', 'PROPN') for c in children[k]):
            return True
        return self._agreement(words, tags, children, k)[1] == 'Plur'

    def _is_subject(self, tree, k) -> bool:
        return str(self._enhanced(tree[2], tree[3])[1][k]).startswith('nsubj')

    def _finite(self, words, tags, labels, children, root):
        """Features of the finite verb of a clause: the head itself, or its copula or auxiliary."""
        if tags[root] == 'VERB':
            features = self.morphology(words[root], 'VERB')
            if 'Person=3' in features:
                return features
        for k in children[root]:
            if labels[k] in ('cop', 'aux') and tags[k] == 'AUX':
                features = self.morphology(words[k], 'AUX')
                if 'Person=3' in features:
                    return features
        return None

    @staticmethod
    def _clause_subject(heads, labels, node):
        """The subject of the nearest clause head above ``node``."""
        seen, head = set(), heads[node] - 1
        while head >= 0 and head not in seen:
            seen.add(head)
            subject = next((k for k in range(len(heads)) if heads[k] == head + 1
                            and str(labels[k]).startswith('nsubj')), None)
            if subject is not None:
                return subject
            head = heads[head] - 1
        return None

    def _first_compatible(self, order, gender, number, exclude, current, learned=None):
        for tree, k in order:
            if tree is current and k in exclude:
                continue
            words, tags, heads, labels = tree
            children = [[] for _ in words]
            for d, h in enumerate(heads):
                if h:
                    children[h - 1].append(d)
            g, n = self._agreement(words, tags, children, k, learned)
            if (gender and g and g != gender) or (number and n and n != number):
                continue
            return tree, k
        return None

    def _rebuilt(self, tree, edits):
        """The tree with each edit applied; returns it and the added words."""
        words, tags, heads, labels = tree
        items = [{'word': w, 'tag': t, 'head': None, 'label': l, 'origin': k}
                 for k, (w, t, l) in enumerate(zip(words, tags, labels))]
        for d, h in enumerate(heads):
            items[d]['head'] = items[h - 1] if h else None
        order = list(items)
        added = []

        def graft(source, head, label):
            copied = [{'word': w, 'tag': t, 'head': None, 'label': l, 'origin': -1} for w, t, _, l in self._copy(*source)]
            for item, (_, _, local, _) in zip(copied, self._copy(*source)):
                item['head'] = copied[local] if local is not None else head
                if local is None:
                    item['label'] = label
            added.extend(item['word'] for item in copied)
            top = next(item for item, (_, _, local, _) in zip(copied, self._copy(*source)) if local is None)
            return copied, top
        for key in sorted(edits, key=lambda k: k if isinstance(k, int) else k[1]):
            kind, source = edits[key]
            if kind == 'pronoun':
                old = items[key]
                copied, top = graft(source, old['head'], old['label'])
                for item in items:
                    if item['head'] is old:
                        item['head'] = top
                # G-54: a dative clitic's antecedent takes the dative's learned preposition (G-49: «a»).
                dative = self.syntax_model.get('dative_case')
                case = [{'word': dative, 'tag': 'ADP', 'head': top, 'label': 'case', 'origin': -1}] \
                    if dative and getattr(self, 'dative_copy', True) and old['tag'] == 'PRON' \
                    and ('Case=Dat' in self.morphology(old['word'], 'PRON') or old['label'] == 'iobj') else []
                at = order.index(old)
                order[at:at + 1] = case + copied
            elif kind == 'possessive':
                old = items[key]
                noun = old['head']
                copied, top = graft(source, noun, 'nmod')
                order.remove(old)
                at = order.index(noun) + 1
                # G-49: the preposition of a noun's nominal complement, learned from the treebank.
                learned = self.syntax_model.get('possessor_case')
                case = [{'word': learned, 'tag': 'ADP', 'head': top, 'label': 'case', 'origin': -1}] if learned else []
                order[at:at] = case + copied
            else:
                verb = items[key[1]]
                copied, top = graft(source, verb, 'nsubj')
                at = order.index(verb)
                order[at:at] = copied
        index = {id(item): n for n, item in enumerate(order)}
        new = ([item['word'] for item in order], [item['tag'] for item in order],
               [index[id(item['head'])] + 1 if item['head'] is not None and id(item['head']) in index else 0
                for item in order],
               [item['label'] for item in order],
               # Where each word was in the sentence as said (-1: added).
               [item['origin'] for item in order])
        return new, added

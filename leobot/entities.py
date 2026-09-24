"""G-51: entities, one person or thing said in different ways.

Pairs of identity inside a sentence come from the Universal Dependencies
definitions: an apposition, and a nominal predicate with a copula and its
subject (also an apposition that carries a copula, the parser's usual slip
with «Fernando es el padre de Camila»).  They also come from identity verbs
learned from worked questions.  A question frame (interrogative, verb or
copula) whose answer was, in at least IDENTITY_RATE of at least
IDENTITY_SUPPORT worked examples, an apposition or copula partner of the
question's own noun asks for the same entity said another way.  A sentence
with that verb therefore states an identity («se llama», «llamado»).

Across sentences, mentions are joined only by a repeated name, by a definite
noun phrase (learned ``Definite=Def``) that takes up the most recent mention
of its word, or by a reference resolved in G-47.  A predicate without an
article joins only inside its sentence: a class does not join two people.
Mentions of one entity align with each other's words.  Identity questions are
answered with another mention, names first.  When the learned answers to an
interrogative are mostly names, a common noun is answered with its entity's
name.
"""
from __future__ import annotations

from .reading import FUNCTION_TAGS, LEMMA, _TOKEN, _fold, _is_word, _norm
from .reference import WINDOW, _feature

IDENTITY_SUPPORT = 10      # worked examples of a question frame before it can be learned
IDENTITY_RATE = 0.2        # ... and the share whose answer is an identity partner of the question's noun
NOMINAL = ('NOUN', 'PROPN')
NAME_PARTS = frozenset({'det', 'amod', 'flat', 'compound', 'nummod'})


class EntityMixin:
    """Mixed into Bot; learned frames live in ``reading_model``."""

    # ----- sentences ------------------------------------------------------
    def _parsed(self, text: str):
        words = self.split_words(text)
        parse = self.parse_words(words)
        if not parse or parse.get('status') != 'parsed_syntax' or not parse.get('labels'):
            return None
        return words, parse['tags'], parse['heads'], parse['labels']

    def _question_frame(self, tree):
        """The frame of a question, (interrogative, verb lemma or 'cop'), with
        the question's own noun (the nominal argument that is not asked
        about), the interrogative and its phrase."""
        words, tags, heads, labels = tree
        q = self.asking_word(words, tags)
        if q is None:
            return None, None, None, None
        phrase = {q}
        p = heads[q] - 1
        if p == q + 1 and tags[p] == 'NOUN':      # «qué color»: the noun belongs to the phrase
            phrase.add(p)
            p = heads[p] - 1
        if p < 0:
            return None, None, None, None
        children = [k for k in range(len(words)) if heads[k] == p + 1]
        if any(labels[k] == 'cop' for k in children):
            verb = 'cop'
        elif tags[p] in ('VERB', 'AUX'):
            verb = self._word_key(words[p])
        else:
            return None, None, None, None
        if verb == 'cop':
            # The copula's arguments are its subject and its predicate.
            anchor = p if p not in phrase and tags[p] in NOMINAL else next(
                (k for k in children if k not in phrase and tags[k] in NOMINAL
                 and str(labels[k]).startswith('nsubj')), None)
        else:
            anchor = next((k for k in children if k not in phrase and tags[k] in NOMINAL
                           and (str(labels[k]).startswith('nsubj') or labels[k] == 'obj')), None)
        return f'{_fold(words[q].lower())}\x1f{verb}', anchor, q, phrase

    def _identity_pairs(self, tree, learned: bool = True) -> set:
        """Pairs of nodes of one sentence that are the same entity."""
        words, tags, heads, labels = tree
        n = len(words)
        children = [[] for _ in range(n)]
        for d, h in enumerate(heads):
            if h:
                children[h - 1].append(d)
        negators = set(self.syntax_model.get('negators', ()))
        enhanced, _ = self._enhanced(heads, labels)

        def asserted(node) -> bool:
            return not any(words[k].lower() in negators for k in children[node]) and \
                not self._subordinate(enhanced, tags, heads, {node})
        pairs = set()
        number = {k: self._agreement(words, tags, children, k)[1] for k in range(n) if tags[k] in NOMINAL}
        # Two mentions of one entity have the same learned number («los domingos, la panadería» do not).
        agree = lambda a, b: not (number.get(a) and number.get(b) and number[a] != number[b])
        for m, h in enumerate(heads):
            if not h or tags[m] not in NOMINAL:
                continue
            head = h - 1
            if labels[m] == 'appos' and tags[head] in NOMINAL:
                if agree(head, m) and (not any(labels[k] == 'cop' for k in children[m])
                                       or (asserted(m) and asserted(head))):
                    pairs.add((head, m))
            elif str(labels[m]).startswith('nsubj'):
                predicate = None
                if any(labels[k] == 'cop' for k in children[head]):
                    predicate = head
                elif labels[head] == 'cop' and heads[head]:
                    predicate = heads[head] - 1        # the subject hung from the copula
                # A predicate with its own preposition («es de color negro») is a quality, not an identity.
                if predicate is not None and tags[predicate] in NOMINAL and asserted(predicate) \
                        and not any(tags[k] == 'ADP' for k in children[predicate]) and agree(predicate, m):
                    pairs.add((predicate, m))
        verbs = set(self.reading_model.get('identity_verbs', ())) \
            if learned and getattr(self, 'learned_identity', True) else set()
        for v in range(n):
            if not verbs or tags[v] not in ('VERB', 'AUX', 'ADJ') or not (self.lemma_keys(words[v]) & verbs) \
                    or not asserted(v):
                continue
            subject = next((k for k in children[v] if str(labels[k]).startswith('nsubj') and tags[k] in NOMINAL), None)
            if subject is None and heads[v] and tags[heads[v] - 1] in NOMINAL \
                    and str(labels[v]).split(':')[0] in ('acl', 'amod'):
                subject = heads[v] - 1                 # «un perro llamado Rocko»
            if subject is None:
                continue
            for k in children[v]:
                if k != subject and tags[k] in NOMINAL and not str(labels[k]).startswith('nsubj') \
                        and not any(tags[c] == 'ADP' for c in children[k]) and agree(subject, k):
                    pairs.add((subject, k))
        return pairs

    @staticmethod
    def _components(n: int, pairs) -> list[int]:
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b in sorted(pairs):
            parent[find(a)] = find(b)
        return [find(i) for i in range(n)]

    # ----- learning from worked questions ---------------------------------
    def _observe_identity_frame(self, question: str, sentence: str, answer: str) -> None:
        """Count whether the answer of a worked question is an identity
        partner (apposition or copula) of the question's own noun."""
        qtree, stree = self._parsed(question), self._parsed(sentence)
        if qtree is None or stree is None:
            return
        frame, anchor, _, _ = self._question_frame(qtree)
        if frame is None or anchor is None:
            return
        words, heads = stree[0], stree[2]
        target = [_norm(t) for t in _TOKEN.findall(answer) if _is_word(t)]
        normalized = [_norm(w) for w in words]
        span = next((set(range(k, k + len(target))) for k in range(len(words) - len(target) + 1)
                     if target and normalized[k:k + len(target)] == target), None)
        if span is None:
            return
        head = next((k for k in sorted(span) if heads[k] - 1 not in span), None)
        key = self._word_key(qtree[0][anchor])
        places = [j for j, w in enumerate(words) if j not in span and key in self.lemma_keys(w)]
        if head is None or not places:
            return
        row = self.reading_model.setdefault('identity_frames', {}).setdefault(frame, [0, 0])
        row[0] += 1
        component = self._components(len(words), self._identity_pairs(stree, learned=False))
        if any(component[j] == component[head] for j in places):
            row[1] += 1

    def _compile_identity_frames(self) -> None:
        table = self.reading_model.get('identity_frames', {})
        frames = sorted(f for f, (n, same) in table.items() if n >= IDENTITY_SUPPORT and same >= IDENTITY_RATE * n)
        self.reading_model['identity_frames_learned'] = frames
        self.reading_model['identity_verbs'] = sorted({f.split('\x1f')[1] for f in frames} - {'cop'})

    # ----- entities of the conversation -----------------------------------
    def _entities(self) -> dict:
        rows = self.reading_utterances
        switches = (getattr(self, 'learned_identity', True), len(self.reading_model.get('identity_verbs', ())))
        cache = self.__dict__.get('_entity_cache')
        if cache is not None and cache[0] == (id(rows), len(rows), switches):
            return cache[1]
        self._resolve_references()
        parent: dict = {}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        info, trees, positions, seen, counters = {}, {}, {}, {}, {}
        for pos, row in enumerate(rows):
            if not self._conversational(row):
                continue
            positions[id(row)] = pos
            tree = self._row_tree(row)
            if tree is None:
                continue
            trees[pos] = tree
            words, tags, heads, labels = tree
            resolved = row.get('resolved')
            origin = resolved[4] if resolved and len(resolved) > 4 else None
            children = [[] for _ in words]
            for d, h in enumerate(heads):
                if h:
                    children[h - 1].append(d)
            # Each sentence said is its own document; the conversation is their sequence (as in G-47).
            earlier = seen.setdefault('conversation', [])
            count = counters['conversation'] = counters.get('conversation', 0) + 1
            local = []
            for i in range(len(words)):
                if tags[i] not in NOMINAL or labels[i] in ('flat', 'compound'):
                    continue
                key = self._word_key(words[i])
                modifiers = {self._word_key(words[k]) for k in children[i]
                             if str(labels[k]).split(':')[0] in ('amod', 'nmod', 'nummod')
                             and tags[k] not in FUNCTION_TAGS and _is_word(words[k])}
                number = _feature(self.morphology(words[i], 'NOUN'), 'Number') if tags[i] == 'NOUN' else None
                definite = any(tags[k] == 'DET' and 'Definite=Def' in self.morphology(words[k], 'DET')
                               for k in children[i])
                inserted = origin is not None and i < len(origin) and origin[i] < 0
                mention = (pos, i)
                parent[mention] = mention
                info[mention] = (key, tags[i], number, modifiers)
                if tags[i] == 'PROPN' or definite or inserted:
                    for other, when in reversed(earlier + local):
                        okey, otag, onumber, omodifiers = info[other]
                        if okey != key or (tags[i] == 'NOUN' and count - when > WINDOW):
                            continue
                        if tags[i] == 'NOUN' and ((number and onumber and number != onumber)
                                                  or not modifiers <= omodifiers):
                            continue
                        parent[find(mention)] = find(other)
                        break
                local.append((mention, count))
            for a, b in sorted(self._identity_pairs(tree)):
                if (pos, a) in info and (pos, b) in info:
                    parent[find((pos, a))] = find((pos, b))
            earlier.extend(local)
        members: dict = {}
        for mention in sorted(info):
            members.setdefault(find(mention), []).append(mention)
        alias, postings = {}, {}
        for group in members.values():
            keys = {info[m][0] for m in group}
            if len(keys) < 2:
                continue
            for m in group:
                alias[m] = keys - {info[m][0]}
                for k in alias[m]:
                    postings.setdefault(LEMMA + k, set()).add(m[0])
        entities = {'root': {m: find(m) for m in info}, 'members': members, 'alias': alias,
                    'postings': postings, 'positions': positions, 'info': info, 'trees': trees}
        self.__dict__['_entity_cache'] = ((id(rows), len(rows), switches), entities)
        return entities

    def _alias_postings(self, key: str):
        """G-51: the rows where another mention of an entity named ``key`` sits."""
        if not getattr(self, 'entities', True) or not self.reading_utterances:
            return ()
        return self._entities()['postings'].get(key, ())

    def _row_key_sets(self, source, tree) -> list:
        """The keys each word of a remembered sentence aligns by, with the
        words of the other mentions of its entity (G-51)."""
        sets = self._key_sets(tree[0])
        if not isinstance(source, dict) or not getattr(self, 'entities', True) or not self._conversational(source):
            return sets
        entities = self._entities()
        pos = entities['positions'].get(id(source))
        if pos is None:
            return sets
        out = []
        for i, keys in enumerate(sets):
            extra = entities['alias'].get((pos, i))
            out.append(set(keys) | extra if extra else keys)
        return out

    def _same_entity(self, row, nodes) -> set:
        """Nodes of a remembered sentence that are the same entity as ``nodes``
        (G-51): what the question already names cannot be its answer."""
        if not getattr(self, 'entities', True) or not isinstance(row, dict) or not self._conversational(row):
            return set()
        entities = self._entities()
        pos = entities['positions'].get(id(row))
        roots = {entities['root'][(pos, j)] for j in nodes if (pos, j) in entities['root']}
        return {m[1] for root in roots for m in entities['members'][root] if m[0] == pos}

    def _mention_text(self, mention) -> str:
        entities = self._entities()
        pos, node = mention
        tree = entities['trees'].get(pos)
        if tree is None:
            return ''
        words, tags, heads, labels = tree
        span, stack = [], [node]
        while stack:
            k = stack.pop()
            span.append(k)
            stack.extend(c for c in range(len(words)) if heads[c] == k + 1 and labels[c] in NAME_PARTS)
        return self._span_text(self.reading_utterances[pos], words, span)

    # ----- answering --------------------------------------------------------
    def _identity_answer(self, qtree) -> dict | None:
        """An identity question («¿Quién es la hermana de Daniel?», a learned
        frame such as «¿Cómo se llama …?») answered with another mention of
        the entity its noun phrase names, names first."""
        if not getattr(self, 'entities', True) or not self.reading_utterances:
            return None
        words, tags, heads, labels = qtree
        frame, anchor, q, phrase = self._question_frame(qtree)
        if frame is None or anchor is None:
            return None
        learned = set(self.reading_model.get('identity_frames_learned', ())) \
            if getattr(self, 'learned_identity', True) else set()
        structural = frame.endswith('\x1fcop') and str(labels[q]).startswith('nsubj') and anchor == heads[q] - 1
        if frame not in learned and not structural:
            return None
        inside, stack = set(), [anchor]
        while stack:
            k = stack.pop()
            inside.add(k)
            stack.extend(c for c in range(len(words)) if heads[c] == k + 1 and c not in phrase
                         and labels[c] not in ('cop', 'punct') and not str(labels[c]).startswith('nsubj'))
        content = sorted(k for k in inside if tags[k] not in FUNCTION_TAGS and _is_word(words[k]))
        if anchor not in content:
            return None
        keyof = {k: self._word_key(words[k]) for k in content}
        links = []
        for k in content:
            node = heads[k] - 1
            while node >= 0 and node not in content:
                node = heads[node] - 1
            if node >= 0:
                links.append((keyof[k], keyof[node], 1))
        structure = {'stems': set(keyof.values()), 'links': links}
        index = self._reading_index()
        lists = sorted((set(index.get(self._search_key(words[k]), ())) |
                        set(self._alias_postings(self._search_key(words[k]))) for k in content), key=len)
        entities = self._entities()
        found: dict = {}
        for pos in sorted(set(lists[0]).intersection(*lists[1:])):
            row = self.reading_utterances[pos]
            if not self._conversational(row):
                continue
            tree = self._tree_of(row)
            if tree is None:
                continue
            for placement in self._placements(structure, tree, self._row_key_sets(row, tree)):
                root = entities['root'].get((pos, placement[keyof[anchor]]))
                if root is None:
                    continue
                used = {(pos, j) for j in placement.values()}
                for other in entities['members'][root]:
                    if other in used or entities['info'][other][0] in structure['stems']:
                        continue
                    text = self._mention_text(other)
                    if text:
                        found.setdefault(' '.join(_norm(t) for t in text.split()), (text, other))
        names = {k: v for k, v in found.items() if entities['info'][v[1]][1] == 'PROPN'}
        pick = names or found
        if not pick:
            return None
        if len(pick) > 1:
            return {'text': 'No lo sé con seguridad: lo que me dijeron admite más de una respuesta.',
                    'status': 'literal_ambiguous', 'candidates': len(pick)}
        text, (pos, _) = next(iter(pick.values()))
        row = self.reading_utterances[pos]
        return {'text': text, 'status': 'literal',
                'explanation': f'Según lo que me dijeron ({row["source"]}): «{row["text"]}».',
                'evidence': {'source': row['source'], 'utterance': row['text'], 'structural': True,
                             'identity': True}}

    def _name_of(self, row, node, interrogative: str, answer: str) -> str | None:
        """The name of the entity a common-noun answer speaks of, when the
        learned answers to this interrogative are mostly names (G-51)."""
        if not getattr(self, 'entities', True) or node is None or not isinstance(row, dict):
            return None
        table = self.reading_model.get('answer_classes', {}).get(_fold(interrogative.lower()))
        if not table or max(sorted(table), key=lambda c: table[c]) != 'PROPN':
            return None
        entities = self._entities()
        mention = (entities['positions'].get(id(row)), node)
        if mention not in entities['info'] or entities['info'][mention][1] != 'NOUN':
            return None
        names = {}
        for other in entities['members'][entities['root'][mention]]:
            if entities['info'][other][1] == 'PROPN':
                text = self._mention_text(other)
                if text:
                    names.setdefault(' '.join(_norm(t) for t in text.split()), text)
        if len(names) != 1:
            return None
        name = next(iter(names.values()))
        # An answer that already says the name («en la calle Real») is kept as it is.
        said = {_norm(t) for t in _TOKEN.findall(answer) if _is_word(t)}
        return None if {_norm(t) for t in _TOKEN.findall(name) if _is_word(t)} <= said else name

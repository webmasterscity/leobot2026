"""G-108: a compiled library of read sentences, kept apart from the bot's memory.

Reading is slow (a 30-word sentence takes about 20 ms to analyse) and answering
must be fast, so a large text read once is compiled: every sentence is stored
with its syntactic analysis (tags, heads, functions).  Attaching the library adds
its sentences to what the bot has read and its analyses to the tree cache, so a
question never analyses a library sentence again.  The library lives in its own
file: ``save`` never writes its rows into the bot's memory.
"""
from __future__ import annotations

import json
import copy
import os
import tempfile
from pathlib import Path

from .reading import _TOKEN

LIBRARY_LIMIT = 100 * 1024 * 1024


class LibraryMixin:
    def compile_sentences(self, sentences, document: str) -> list:
        """Analyse sentences: ``[document, text, tags, heads, labels, words]`` rows."""
        rows = []
        for text in sentences:
            if self._question_like(text) or not any(t[:1].isalnum() for t in _TOKEN.findall(text)):
                continue
            words = self.split_words(text)
            parse = self.parse_words(words) if words else None
            if parse and parse.get('status') == 'parsed_syntax':
                labels = parse.get('labels') or [None] * len(words)
                rows.append([document, text, ' '.join(parse['tags']), ','.join(map(str, parse['heads'])),
                             ' '.join(label or '_' for label in labels), words])
            else:
                rows.append([document, text, '', '', '', words])
        return rows

    @staticmethod
    def write_library(rows, path, meta=None) -> int:
        path = Path(path)
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as out:
                version = 2 if any(len(row) == 6 for row in rows) else 1
                json.dump({'version': version, 'meta': meta or {}, 'rows': rows}, out, ensure_ascii=False, separators=(',', ':'))
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path.stat().st_size

    def attach_library(self, path) -> dict:
        """Add a compiled library to what was read (not saved with the bot)."""
        path = Path(path)
        if path.stat().st_size > LIBRARY_LIMIT:
            raise ValueError('La biblioteca excede el límite de 100 MiB.')
        data = json.loads(path.read_text(encoding='utf8'))
        if not isinstance(data, dict) or data.get('version') not in (1, 2) or not isinstance(data.get('rows'), list):
            raise ValueError('Formato de biblioteca no compatible.')
        # Legacy files need the receiver's splitting.  Consolidation must not change
        # the receiver if a later row turns out to be invalid.
        view = self
        if not self.syntax_model.get('compiled'):
            view = object.__new__(type(self))
            view.__dict__.update(self.__dict__)
            view.syntax_model = copy.deepcopy(self.syntax_model)
        prepared = []
        for number, row in enumerate(data['rows']):
            if not isinstance(row, list) or len(row) not in (5, 6) or not all(isinstance(value, str) for value in row[:5]):
                raise ValueError(f'Fila de biblioteca inválida: {number + 1}.')
            document, text, tags, heads, labels = row[:5]
            stored = row[5] if len(row) == 6 else None
            if len(row) == 6 and (data['version'] != 2 or not isinstance(stored, list)
                                 or not all(isinstance(word, str) and word for word in stored)):
                raise ValueError(f'Palabras de biblioteca inválidas: {number + 1}.')
            tree = None
            if tags or heads or labels:
                words = stored if stored is not None else view.split_words(text)
                tag_list, label_list = tags.split(), labels.split()
                try:
                    head_list = [int(head) for head in heads.split(',')]
                except ValueError as error:
                    raise ValueError(f'Análisis de biblioteca inválido: {number + 1}.') from error
                size = len(tag_list)
                if (not size or len(head_list) != size or len(label_list) != size
                        or (stored is not None and len(stored) != size)
                        or not head_list.count(0) or any(head < 0 or head > size for head in head_list)):
                    raise ValueError(f'Análisis de biblioteca incompleto: {number + 1}.')
                # Every word must reach a root.  The existing parser can emit a forest.
                finished = set()
                for start in range(size):
                    visited, node = set(), start
                    while node not in finished:
                        if node in visited:
                            raise ValueError(f'Análisis de biblioteca con ciclo: {number + 1}.')
                        visited.add(node)
                        if head_list[node] == 0:
                            break
                        node = head_list[node] - 1
                    finished.update(visited)
                if len(words) == size:
                    tree = (words, tag_list, head_list, [None if label == '_' else label for label in label_list])
            prepared.append(({'source': f'{document}:oración:{number + 1}', 'document': document,
                              'text': text, 'tokens': _TOKEN.findall(text), 'library': True}, tree))
        trees = self.__dict__.setdefault('_utterance_trees', {})
        for row, tree in prepared:
            if tree is not None and not trees.get(row['text']):
                trees[row['text']] = tree
        self.reading_utterances.extend(row for row, _ in prepared)
        self._reading_index_cache = None
        self._reading_index()     # compiled now, not at the first question
        return {'status': 'library_attached', 'rows': len(prepared), 'meta': data.get('meta', {})}

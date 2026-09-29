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
import os
import tempfile
from pathlib import Path

from .reading import _TOKEN

LIBRARY_LIMIT = 100 * 1024 * 1024


class LibraryMixin:
    def compile_sentences(self, sentences, document: str) -> list:
        """Analyse sentences of one document: ``[document, text, tags, heads, labels]`` rows."""
        rows = []
        for text in sentences:
            if self._question_like(text) or not any(t[:1].isalnum() for t in _TOKEN.findall(text)):
                continue
            words = self.split_words(text)
            parse = self.parse_words(words) if words else None
            if parse and parse.get('status') == 'parsed_syntax':
                labels = parse.get('labels') or [None] * len(words)
                rows.append([document, text, ' '.join(parse['tags']), ','.join(map(str, parse['heads'])),
                             ' '.join(label or '_' for label in labels)])
            else:
                rows.append([document, text, '', '', ''])
        return rows

    @staticmethod
    def write_library(rows, path, meta=None) -> int:
        path = Path(path)
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as out:
                json.dump({'version': 1, 'meta': meta or {}, 'rows': rows}, out, ensure_ascii=False, separators=(',', ':'))
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
        if data.get('version') != 1:
            raise ValueError('Formato de biblioteca no compatible.')
        trees = self.__dict__.setdefault('_utterance_trees', {})
        added = 0
        for number, (document, text, tags, heads, labels) in enumerate(data['rows']):
            self.reading_utterances.append({'source': f'{document}:oración:{number + 1}', 'document': document,
                                            'text': text, 'tokens': _TOKEN.findall(text), 'library': True})
            if tags and text not in trees:
                words = self.split_words(text)
                tag_list = tags.split(' ')
                if len(tag_list) == len(words):
                    trees[text] = (words, tag_list, [int(h) for h in heads.split(',')],
                                   [None if label == '_' else label for label in labels.split(' ')])
            added += 1
        self._reading_index_cache = None
        self._reading_index()     # compiled now, not at the first question
        return {'status': 'library_attached', 'rows': added, 'meta': data.get('meta', {})}

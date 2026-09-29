import json
import tempfile
import unittest
from pathlib import Path

from leobot import Bot


class CompiledLibrary(unittest.TestCase):
    def test_attach_is_read_but_never_saved(self):
        bot = Bot()
        rows = bot.compile_sentences(['El paraguas sirve para protegerse de la lluvia.', '¿Qué es esto?'], 'Wikipedia: Paraguas')
        self.assertEqual([r[1] for r in rows], ['El paraguas sirve para protegerse de la lluvia.'])
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'biblioteca.json'
            bot.write_library(rows, library, meta={'prueba': True})
            report = bot.attach_library(library)
            self.assertEqual(report['rows'], 1)
            self.assertEqual(bot.reading_utterances[-1]['document'], 'Wikipedia: Paraguas')
            memory = Path(tmp) / 'bot.json'
            bot.save(memory)
            saved = json.loads(memory.read_text(encoding='utf8'))
            self.assertEqual(saved['reading_utterances'], [])
            self.assertEqual(Bot.load(memory).reading_utterances, [])

    def test_compiled_tree_goes_to_the_cache(self):
        bot = Bot()
        rows = [['Wikipedia: X', 'Uno dos tres.', 'NUM NUM NUM PUNCT', '0,1,1,1', 'root nmod nmod punct']]
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            bot.write_library(rows, library)
            bot.split_words = lambda text: ['Uno', 'dos', 'tres', '.']
            bot.attach_library(library)
        words, tags, heads, labels = bot._utterance_trees['Uno dos tres.']
        self.assertEqual((tags, heads, labels[0]), (['NUM', 'NUM', 'NUM', 'PUNCT'], [0, 1, 1, 1], 'root'))


if __name__ == '__main__':
    unittest.main()

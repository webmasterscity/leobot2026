import json
import tempfile
import unittest
from pathlib import Path

from leobot import Bot


class CompiledLibrary(unittest.TestCase):
    def test_compiled_tree_replaces_an_earlier_failed_analysis(self):
        text = 'El perro es un animal'
        bot = Bot()
        self.assertIsNone(bot._utterance_tree(text))
        rows = [['Manual', text, 'DET NOUN AUX DET NOUN', '2,0,2,5,2', 'det root cop det nsubj']]
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            bot.write_library(rows, library)
            bot.attach_library(library)
        self.assertIsNotNone(bot._utterance_tree(text))

    def test_invalid_library_is_rejected_without_partial_changes(self):
        import copy
        text = 'El perro es un animal'
        valid = ['Manual', text, 'DET NOUN AUX DET NOUN', '2,0,2,5,2', 'det root cop det nsubj']
        invalid = [
            ['Manual', 'Otro texto', 'NOUN NOUN', '0', 'root'],
            ['Manual', 'Otro texto', 'NOUN NOUN', '0,invalid', 'root nmod'],
            ['Manual', 'Otro texto', 'NOUN NOUN', '0,3', 'root nmod'],
            ['Manual', 'Otro texto', 'NOUN NOUN', '0,-1', 'root nmod'],
            ['Manual', 'Otro texto', 'NOUN NOUN', '0,2', 'root nmod'],
            ['Manual', 'Uno dos tres', 'NUM NUM NUM', '0,3,2', 'root nmod nmod'],
            ['Manual', 'Otro texto', 'NOUN NOUN', '1,1', 'nmod nmod'],
            ['Manual', 'Otro texto', '', '0,1', 'root nmod'],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            for bad in invalid:
                with self.subTest(row=bad):
                    bot = Bot()
                    bot._reading_index()
                    fields = ('reading_utterances', '_utterance_trees', '_reading_index_cache')
                    before = copy.deepcopy({name: bot.__dict__.get(name) for name in fields})
                    bot.write_library([valid, bad], library)
                    with self.assertRaises(ValueError):
                        bot.attach_library(library)
                    self.assertEqual({name: bot.__dict__.get(name) for name in fields}, before)

    def test_own_compiler_can_emit_several_roots(self):
        bot = Bot()
        for _ in range(5):
            bot.observe_parsed_sentence(['El', 'perro', 'es', 'un', 'animal', '.'],
                                       ['DET', 'NOUN', 'AUX', 'DET', 'NOUN', 'PUNCT'],
                                       [2, 5, 5, 5, 0, 5], ['det', 'nsubj', 'cop', 'det', 'root', 'punct'])
            bot.observe_parsed_sentence(['Hola', '.'], ['INTJ', 'PUNCT'], [0, 1], ['root', 'punct'])
        bot.consolidate_syntax()
        rows = bot.compile_sentences(['Hola . El perro es un animal .'], 'Manual')
        self.assertGreater(rows[0][3].split(',').count('0'), 1)
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            bot.write_library(rows, library)
            self.assertEqual(bot.attach_library(library)['rows'], 1)

    def test_compiled_words_survive_different_splitting_in_receiver(self):
        teacher = Bot()
        for _ in range(5):
            teacher.observe_parsed_sentence(['El', 'perro', 'es', 'del', 'barrio', '.'],
                                           ['DET', 'NOUN', 'AUX', 'ADP', 'NOUN', 'PUNCT'],
                                           [2, 5, 5, 5, 0, 5], ['det', 'nsubj', 'cop', 'case', 'root', 'punct'])
        teacher.consolidate_syntax()
        text = 'El perro es del barrio.'
        rows = teacher.compile_sentences([text], 'Manual')
        receiver = Bot()
        receiver.consolidate_syntax()
        receiver.syntax_model['split_table']['del'] = ['de', 'el']
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            teacher.write_library(rows, library)
            receiver.attach_library(library)
        tree = receiver._utterance_tree(text)
        self.assertIsNotNone(tree)
        self.assertEqual(tree[0], teacher.split_words(text))

    def test_legacy_library_with_different_splitting_keeps_its_text(self):
        bot = Bot()
        bot.consolidate_syntax()
        bot.syntax_model['split_table']['del'] = ['de', 'el']
        text = 'El perro es del barrio.'
        rows = [['Manual', text, 'DET NOUN AUX ADP NOUN PUNCT', '2,5,5,5,0,5', 'det nsubj cop case root punct']]
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            bot.write_library(rows, library)
            self.assertEqual(bot.attach_library(library)['rows'], 1)
        self.assertEqual(bot.reading_utterances[-1]['text'], text)
        self.assertNotIn(text, bot._utterance_trees)

    def test_rejected_library_does_not_consolidate_receiver_syntax(self):
        import copy
        bot = Bot()
        before = copy.deepcopy(bot.syntax_model)
        rows = [['Manual', 'Otro texto', 'NOUN NOUN', '0,invalid', 'root nmod']]
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'b.json'
            bot.write_library(rows, library)
            with self.assertRaises(ValueError):
                bot.attach_library(library)
        self.assertEqual(bot.syntax_model, before)

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

"""G-29: word classes and heads are learned from annotated sentences by counting."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot

TRAIN=[
    (['El','perro','come','carne','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3]),
    (['La','niña','lee','libros','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3]),
    (['Un','gato','bebe','leche','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3]),
    (['El','hombre','compra','pan','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3]),
]


class SyntaxCountTests(unittest.TestCase):
    def test_fresh_bot_does_not_parse(self):
        self.assertIsNone(Bot().parse_words(['El','perro','come']))

    def test_learned_tree_for_new_sentence_survives_restart(self):
        bot=Bot()
        for words,tags,heads in TRAIN:
            bot.observe_parsed_sentence(words,tags,heads)
        parsed=bot.parse_words(['La','vaca','come','hierba','.'])
        self.assertEqual(parsed['tags'],['DET','NOUN','VERB','NOUN','PUNCT'])
        self.assertEqual(parsed['heads'],[2,3,0,3,3])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bot.json'
            bot.save(path); restored=Bot.load(path)
        self.assertEqual(restored.parse_words(['La','vaca','come','hierba','.']),parsed)


if __name__=='__main__':
    unittest.main()

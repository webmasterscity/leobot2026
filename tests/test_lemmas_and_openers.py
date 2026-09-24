"""G-44b: words align by learned dictionary form; an interrogative written
without its accent counts at the opening of a question."""
import unittest

from leobot import Bot

TREES = [
    (['Rosa', 'es', 'la', 'bibliotecaria', '.'], ['PROPN', 'AUX', 'DET', 'NOUN', 'PUNCT'],
     [4, 4, 4, 0, 4], ['nsubj', 'cop', 'det', 'root', 'punct'], ['Rosa', 'ser', 'el', 'bibliotecario', '.']),
    (['La', 'biblioteca', 'abrió', 'en', 'marzo', '.'], ['DET', 'NOUN', 'VERB', 'ADP', 'NOUN', 'PUNCT'],
     [2, 3, 0, 5, 3, 3], ['det', 'nsubj', 'root', 'case', 'obl', 'punct'], ['el', 'biblioteca', 'abrir', 'en', 'marzo', '.']),
    (['¿', 'Quién', 'es', 'la', 'bibliotecaria', '?'], ['PUNCT', 'PRON', 'AUX', 'DET', 'NOUN', 'PUNCT'],
     [5, 5, 5, 5, 0, 5], ['punct', 'nsubj', 'cop', 'det', 'root', 'punct'], ['¿', 'quién', 'ser', 'el', 'bibliotecario', '?']),
    (['Ana', 'tienen', 'dos', 'perros', '.'], ['PROPN', 'VERB', 'NUM', 'NOUN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'nummod', 'obj', 'punct'], ['Ana', 'tener', 'dos', 'perro', '.']),
    (['Ana', 'tiene', 'dos', 'perros', '.'], ['PROPN', 'VERB', 'NUM', 'NOUN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'nummod', 'obj', 'punct'], ['Ana', 'tener', 'dos', 'perro', '.']),
    (['¿', 'Cuántos', 'perros', 'tiene', 'Ana', '?'], ['PUNCT', 'DET', 'NOUN', 'VERB', 'PROPN', 'PUNCT'],
     [4, 3, 4, 0, 4, 4], ['punct', 'det', 'obj', 'root', 'nsubj', 'punct'], ['¿', 'cuánto', 'perro', 'tener', 'Ana', '?']),
]


def taught_bot():
    bot = Bot()
    for _ in range(4):
        for words, tags, heads, labels, lemmas in TREES:
            bot.observe_parsed_sentence(words, tags, heads, labels, lemmas=lemmas)
    bot.consolidate_syntax()
    return bot


class LemmaAndOpenerTests(unittest.TestCase):
    def test_lemmas_are_learned_from_annotated_examples(self):
        bot = taught_bot()
        self.assertEqual(bot.lemma_key('tienen'), bot.lemma_key('tiene'))
        self.assertNotEqual(bot.lemma_key('bibliotecaria'), bot.lemma_key('biblioteca'))

    def test_words_sharing_a_beginning_do_not_align(self):
        bot = taught_bot()
        bot.respond('La biblioteca abrió en marzo.')
        self.assertIsNone(bot.answer_by_structure('¿Quién es la bibliotecaria?'))
        bot.lemma_alignment = False
        self.assertIsNotNone(bot.answer_by_structure('¿Quién es la bibliotecaria?'))

    def test_an_interrogative_without_accent_opens_a_question(self):
        bot = taught_bot()
        self.assertEqual(bot.asking_word(['¿', 'Cuantos', 'perros', 'tiene', 'Ana', '?']), 1)
        bot.folded_openers = False
        self.assertIsNone(bot.asking_word(['¿', 'Cuantos', 'perros', 'tiene', 'Ana', '?']))


if __name__ == '__main__':
    unittest.main()

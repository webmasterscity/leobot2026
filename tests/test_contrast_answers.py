"""G-46: «no» when another value of the same attribute was said; not for what
is had or exists, where one thing does not exclude another."""
import unittest

from leobot import Bot

TREES = [
    (['La', 'farmacia', 'cierra', 'a', 'las', 'nueve', '.'], ['DET', 'NOUN', 'VERB', 'ADP', 'DET', 'NUM', 'PUNCT'],
     [2, 3, 0, 6, 6, 3, 3], ['det', 'nsubj', 'root', 'case', 'det', 'obl', 'punct']),
    (['¿', 'La', 'farmacia', 'cierra', 'a', 'las', 'diez', '?'], ['PUNCT', 'DET', 'NOUN', 'VERB', 'ADP', 'DET', 'NUM', 'PUNCT'],
     [4, 3, 4, 0, 7, 7, 4, 4], ['punct', 'det', 'nsubj', 'root', 'case', 'det', 'obl', 'punct']),
    (['Laura', 'tiene', 'una', 'bicicleta', '.'], ['PROPN', 'VERB', 'DET', 'NOUN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'det', 'obj', 'punct']),
    (['¿', 'Laura', 'tiene', 'una', 'moto', '?'], ['PUNCT', 'PROPN', 'VERB', 'DET', 'NOUN', 'PUNCT'],
     [3, 3, 0, 5, 3, 3], ['punct', 'nsubj', 'root', 'det', 'obj', 'punct']),
    (['¿', 'Dónde', 'vive', 'Laura', '?'], ['PUNCT', 'PRON', 'VERB', 'PROPN', 'PUNCT'],
     [3, 3, 0, 3, 3], ['punct', 'advmod', 'root', 'nsubj', 'punct']),
]


def taught_bot():
    bot = Bot()
    for _ in range(4):
        for words, tags, heads, labels in TREES:
            bot.observe_parsed_sentence(words, tags, heads, labels)
    bot.consolidate_syntax()
    return bot


class ContrastTests(unittest.TestCase):
    def test_another_value_of_an_attribute_means_no(self):
        bot = taught_bot()
        bot.respond('La farmacia cierra a las nueve.')
        answer = bot.respond('¿La farmacia cierra a las diez?')
        self.assertEqual(answer['status'], 'literal_contrast')
        self.assertTrue(answer['text'].startswith('No:'))

    def test_what_is_had_does_not_exclude_other_things(self):
        bot = taught_bot()
        bot.respond('Laura tiene una bicicleta.')
        self.assertEqual(bot.respond('¿Laura tiene una moto?')['status'], 'literal_unknown')

    def test_ablation_switch(self):
        bot = taught_bot()
        bot.contrast_answers = False
        bot.respond('La farmacia cierra a las nueve.')
        self.assertEqual(bot.respond('¿La farmacia cierra a las diez?')['status'], 'literal_unknown')


if __name__ == '__main__':
    unittest.main()

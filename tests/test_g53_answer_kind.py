"""G-53: an answer must be of the kind the question asks for, learned by counting worked questions."""
import unittest

from leobot import Bot

COLOURS = ['rojo', 'azul', 'verde', 'blanco', 'negro']


def taught():
    """Tags and the interrogative learned from demonstrations (no word written into the engine)."""
    bot = Bot()
    for _ in range(3):
        for adjective in COLOURS + ['grande']:
            bot.observe_parsed_sentence(['El', 'color', 'es', adjective, '.'], ['DET', 'NOUN', 'AUX', 'ADJ', 'PUNCT'],
                                        [2, 4, 4, 0, 4], ['det', 'nsubj', 'cop', 'root', 'punct'],
                                        feats=['_'] * 5)
        bot.observe_parsed_sentence(['¿', 'De', 'qué', 'color', 'es', '?'], ['PUNCT', 'ADP', 'DET', 'NOUN', 'AUX', 'PUNCT'],
                                    [4, 4, 4, 0, 4, 4], ['punct', 'case', 'det', 'root', 'cop', 'punct'],
                                    feats=['_', '_', 'PronType=Int', '_', '_', '_'])
    bot.consolidate_syntax()
    return bot


class AnswerKindTests(unittest.TestCase):
    LOW = ['de', 'qué', 'color', 'es', 'la', 'casa']

    def test_a_closed_kind_needs_a_member_seen_in_worked_answers(self):
        bot = taught()
        for colour in COLOURS * 8:
            bot.observe_answer_kind('¿De qué color es la casa?', colour)
        self.assertEqual(bot.reading_model['answer_kinds']['que color']['n'], 40)
        self.assertTrue(bot._kind_fits(self.LOW, 1, 2, 'azul'))
        self.assertFalse(bot._kind_fits(self.LOW, 1, 2, 'grande'))     # same class, never an answer of this kind
        bot.answer_kind = False
        self.assertIsNone(bot._kind_fits(self.LOW, 1, 2, 'grande'))

    def test_an_open_kind_checks_only_the_class(self):
        bot = taught()
        for k in range(40):                                              # every answer a new word (Good-Turing 1.0)
            bot.observe_answer_kind('¿De qué color es la casa?', COLOURS[k % 5] if k < 5 else f'color{k}')
        self.assertTrue(bot._kind_fits(self.LOW, 1, 2, 'grande') is not False)

    def test_too_little_evidence_checks_nothing(self):
        bot = taught()
        for colour in COLOURS * 4:
            bot.observe_answer_kind('¿De qué color es la casa?', colour)
        self.assertIsNone(bot._kind_fits(self.LOW, 1, 2, 'grande'))


if __name__ == '__main__':
    unittest.main()

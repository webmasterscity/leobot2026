"""G-42: a question is a sentence with a gap."""
import unittest

from leobot import Bot
from leobot.core import Atom

TREES = [
    (['Marta', 'tiene', 'tres', 'hijos', '.'], ['PROPN', 'VERB', 'NUM', 'NOUN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'nummod', 'obj', 'punct']),
    (['Luis', 'tiene', 'dos', 'perros', '.'], ['PROPN', 'VERB', 'NUM', 'NOUN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'nummod', 'obj', 'punct']),
    (['Ana', 'vive', 'en', 'Lima', '.'], ['PROPN', 'VERB', 'ADP', 'PROPN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'case', 'obl', 'punct']),
    (['¿', 'Cuántos', 'hijos', 'tiene', 'Marta', '?'], ['PUNCT', 'DET', 'NOUN', 'VERB', 'PROPN', 'PUNCT'],
     [4, 3, 4, 0, 4, 4], ['punct', 'det', 'obj', 'root', 'nsubj', 'punct']),
    (['¿', 'Dónde', 'vive', 'Ana', '?'], ['PUNCT', 'PRON', 'VERB', 'PROPN', 'PUNCT'],
     [3, 3, 0, 3, 3], ['punct', 'advmod', 'root', 'nsubj', 'punct']),
    (['¿', 'En', 'qué', 'año', 'nació', 'Luis', '?'], ['PUNCT', 'ADP', 'DET', 'NOUN', 'VERB', 'PROPN', 'PUNCT'],
     [5, 4, 4, 5, 0, 5, 5], ['punct', 'case', 'det', 'obl', 'root', 'nsubj', 'punct']),
]


def taught_bot():
    """Word classes and trees from demonstrations; no morphological features,
    so interrogatives can only come from how questions open (G-42)."""
    bot = Bot()
    for _ in range(4):
        for words, tags, heads, labels in TREES:
            bot.observe_parsed_sentence(words, tags, heads, labels)
    bot.consolidate_syntax()
    return bot


class StructuralAnswerTests(unittest.TestCase):
    def test_interrogatives_are_learned_from_how_questions_open(self):
        bot = taught_bot()
        # «En» is a preposition in the demonstrations, so «qué» opens that question.
        self.assertEqual(bot.syntax_model['interrogatives'], ['cuántos', 'dónde', 'qué'])

    def test_learning_does_not_depend_on_the_order_of_the_data(self):
        forward, backward = Bot(), Bot()
        for bot, trees in ((forward, TREES), (backward, TREES[::-1])):
            for _ in range(4):
                for words, tags, heads, labels in trees:
                    bot.observe_parsed_sentence(words, tags, heads, labels)
            bot.consolidate_syntax()
        self.assertEqual(forward.syntax_model['interrogatives'], backward.syntax_model['interrogatives'])

    def test_the_gap_is_filled_by_the_part_in_its_place(self):
        bot = taught_bot()
        for text in ('Marta tiene tres hijos.', 'Luis tiene dos perros.', 'Ana vive en Lima.'):
            bot.respond(text)
        answer = bot.respond('¿Cuántos hijos tiene Marta?')
        self.assertEqual(answer['status'], 'literal')
        self.assertTrue(answer['evidence']['structural'])
        self.assertEqual(answer['text'], 'tres')
        self.assertIn('Lima', bot.respond('¿Dónde vive Ana?')['text'])

    def test_a_question_nothing_covers_is_not_answered_structurally(self):
        bot = taught_bot()
        bot.respond('Marta tiene tres hijos.')
        self.assertIsNone(bot.answer_by_structure('¿Dónde vive Ana?'))

    def test_equally_good_answers_are_reported_as_ambiguous(self):
        bot = taught_bot()
        bot.respond('Marta tiene tres hijos.')
        bot.respond('Marta tiene dos perros.')
        answer = bot.answer_by_structure('¿Cuántos gatos tiene Marta?')
        self.assertEqual(answer['status'], 'literal_ambiguous')
        self.assertTrue(answer['text'].startswith('No lo sé'))

    def test_ablation_switch_leaves_the_older_reader(self):
        bot = taught_bot()
        bot.structural_answers = False
        bot.respond('Marta tiene tres hijos.')
        answer = bot.respond('¿Cuántos hijos tiene Marta?')
        self.assertFalse((answer.get('evidence') or {}).get('structural', False))

    def test_formal_unknown_starts_with_no_lo_se(self):
        self.assertTrue(Bot().answer_atom(Atom('p', ('a',)))['text'].startswith('No lo sé'))


if __name__ == '__main__':
    unittest.main()

"""G-43: coordinated elements and yes/no checked in structure (G-43b retired the
learned answer class, which added nothing, together with its tests)."""
import unittest

from leobot import Bot

TREES = [
    (['Carlos', 'es', 'el', 'hermano', 'de', 'Marta', 'y', 'vive', 'en', 'Toledo', '.'],
     ['PROPN', 'AUX', 'DET', 'NOUN', 'ADP', 'PROPN', 'CCONJ', 'VERB', 'ADP', 'PROPN', 'PUNCT'],
     [4, 4, 4, 0, 6, 4, 8, 4, 10, 8, 4],
     ['nsubj', 'cop', 'det', 'root', 'case', 'nmod', 'cc', 'conj', 'case', 'obl', 'punct']),
    (['¿', 'Marta', 'vive', 'en', 'Toledo', '?'], ['PUNCT', 'PROPN', 'VERB', 'ADP', 'PROPN', 'PUNCT'],
     [3, 3, 0, 5, 3, 3], ['punct', 'nsubj', 'root', 'case', 'obl', 'punct']),
    (['¿', 'Carlos', 'vive', 'en', 'Toledo', '?'], ['PUNCT', 'PROPN', 'VERB', 'ADP', 'PROPN', 'PUNCT'],
     [3, 3, 0, 5, 3, 3], ['punct', 'nsubj', 'root', 'case', 'obl', 'punct']),
    (['Marina', 'afirmó', 'que', 'la', 'reunión', 'es', 'el', 'lunes', '.'],
     ['PROPN', 'VERB', 'SCONJ', 'DET', 'NOUN', 'AUX', 'DET', 'NOUN', 'PUNCT'],
     [2, 0, 8, 5, 8, 8, 8, 2, 2], ['nsubj', 'root', 'mark', 'det', 'nsubj', 'cop', 'det', 'ccomp', 'punct']),
    (['¿', 'La', 'reunión', 'es', 'el', 'lunes', '?'], ['PUNCT', 'DET', 'NOUN', 'AUX', 'DET', 'NOUN', 'PUNCT'],
     [6, 3, 6, 6, 6, 0, 6], ['punct', 'det', 'nsubj', 'cop', 'det', 'root', 'punct']),
    (['En', 'la', 'caja', 'hay', 'doce', 'manzanas', 'y', 'cinco', 'naranjas', '.'],
     ['ADP', 'DET', 'NOUN', 'VERB', 'NUM', 'NOUN', 'CCONJ', 'NUM', 'NOUN', 'PUNCT'],
     [3, 3, 4, 0, 6, 4, 9, 9, 6, 4], ['case', 'det', 'obl', 'root', 'nummod', 'obj', 'cc', 'nummod', 'conj', 'punct']),
    (['¿', 'Cuántas', 'manzanas', 'hay', 'en', 'la', 'caja', '?'],
     ['PUNCT', 'DET', 'NOUN', 'VERB', 'ADP', 'DET', 'NOUN', 'PUNCT'],
     [4, 3, 4, 0, 7, 7, 4, 4], ['punct', 'det', 'obj', 'root', 'case', 'det', 'obl', 'punct']),
    (['¿', 'Cuántas', 'naranjas', 'hay', 'en', 'la', 'caja', '?'],
     ['PUNCT', 'DET', 'NOUN', 'VERB', 'ADP', 'DET', 'NOUN', 'PUNCT'],
     [4, 3, 4, 0, 7, 7, 4, 4], ['punct', 'det', 'obj', 'root', 'case', 'det', 'obl', 'punct']),
    # Assertions opening with the same words, as in real text: only
    # «cuántas» opens questions alone and is learned as interrogative.
    (['Marta', 'vive', 'en', 'Toledo', '.'], ['PROPN', 'VERB', 'ADP', 'PROPN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'case', 'obl', 'punct']),
    (['Carlos', 'vive', 'en', 'Toledo', '.'], ['PROPN', 'VERB', 'ADP', 'PROPN', 'PUNCT'],
     [2, 0, 4, 2, 2], ['nsubj', 'root', 'case', 'obl', 'punct']),
    (['La', 'reunión', 'es', 'el', 'lunes', '.'], ['DET', 'NOUN', 'AUX', 'DET', 'NOUN', 'PUNCT'],
     [2, 5, 5, 5, 0, 5], ['det', 'nsubj', 'cop', 'det', 'root', 'punct']),
]
EXAMPLES = [
    ('En la caja hay doce manzanas.', '¿Cuántas manzanas hay en la caja?', 'doce'),
    ('En la caja hay cinco naranjas.', '¿Cuántas naranjas hay en la caja?', 'cinco'),
    ('En la caja hay doce naranjas.', '¿Cuántas naranjas hay en la caja?', 'doce'),
]


def learn_syntax(bot):
    for _ in range(4):
        for words, tags, heads, labels in TREES:
            bot.observe_parsed_sentence(words, tags, heads, labels)
    bot.consolidate_syntax()


def taught_bot():
    bot = Bot()
    learn_syntax(bot)
    for context, question, answer in EXAMPLES:
        bot.observe_reading_example(context, question, answer)
    bot.consolidate_reading()
    return bot


class AnswerClassTests(unittest.TestCase):
    def test_only_the_asking_word_is_learned_as_interrogative(self):
        self.assertEqual(taught_bot().syntax_model['interrogatives'], ['cuántas'])

    def test_a_coordinated_element_is_not_a_modifier(self):
        bot = taught_bot()
        bot.respond('En la caja hay doce manzanas y cinco naranjas.')
        self.assertEqual(bot.respond('¿Cuántas manzanas hay en la caja?')['text'], 'doce')
        self.assertEqual(bot.respond('¿Cuántas naranjas hay en la caja?')['text'], 'cinco')


class StructuralVerificationTests(unittest.TestCase):
    def test_who_does_what_is_checked(self):
        bot = taught_bot()
        bot.respond('Carlos es el hermano de Marta y vive en Toledo.')
        self.assertEqual(bot.respond('¿Carlos vive en Toledo?')['status'], 'literal_yes')
        self.assertEqual(bot.respond('¿Marta vive en Toledo?')['status'], 'literal_unknown')

    def test_what_someone_said_is_not_asserted(self):
        bot = taught_bot()
        bot.respond('Marina afirmó que la reunión es el lunes.')
        answer = bot.respond('¿La reunión es el lunes?')
        self.assertEqual(answer['status'], 'literal_reported')
        self.assertTrue(answer['text'].startswith('No lo sé'))

    def test_ablation_switch_restores_the_bag_of_words(self):
        bot = taught_bot()
        bot.structural_verification = False
        bot.respond('Carlos es el hermano de Marta y vive en Toledo.')
        self.assertEqual(bot.respond('¿Marta vive en Toledo?')['status'], 'literal_yes')


if __name__ == '__main__':
    unittest.main()

"""G-41: what is said is remembered and checked like what is read."""
import unittest

from leobot import Bot


def taught_bot():
    """A bot whose negators and interrogatives come from annotated examples."""
    bot = Bot()
    for _ in range(3):
        bot.observe_parsed_sentence(['Ana', 'no', 'come'], ['PROPN', 'ADV', 'VERB'], [3, 3, 0],
                                    ['nsubj', 'advmod', 'root'], ['_', 'Polarity=Neg', '_'])
        bot.observe_parsed_sentence(['¿', 'Dónde', 'vive', '?'], ['PUNCT', 'PRON', 'VERB', 'PUNCT'], [3, 3, 0, 3],
                                    ['punct', 'advmod', 'root', 'punct'], ['_', 'PronType=Int', '_', '_'])
    bot.consolidate_syntax()
    return bot


class ConversationMemoryTests(unittest.TestCase):
    def test_lexicons_are_learned_from_features(self):
        bot = taught_bot()
        self.assertEqual(bot.syntax_model['negators'], ['no'])
        self.assertEqual(bot.syntax_model['interrogatives'], ['dónde'])

    def test_yes_no_questions_are_checked_against_what_was_said(self):
        bot = taught_bot()
        bot.respond('Ana vive en Lima.')
        bot.respond('Luis no tiene perro.')
        self.assertEqual(bot.respond('¿Ana vive en Lima?')['status'], 'literal_yes')
        self.assertTrue(bot.respond('¿Ana vive en Lima?')['text'].startswith('Sí'))
        self.assertEqual(bot.respond('¿Luis tiene perro?')['status'], 'literal_no')
        self.assertEqual(bot.respond('¿Ana vive en Cusco?')['status'], 'literal_unknown')
        self.assertTrue(bot.respond('¿Pedro tiene gato?')['text'].startswith('No lo sé'))

    def test_contradiction_is_not_resolved_silently(self):
        bot = taught_bot()
        bot.respond('Marta tiene un gato.')
        bot.respond('Marta no tiene un gato.')
        self.assertEqual(bot.respond('¿Marta tiene un gato?')['status'], 'literal_contradiction')

    def test_open_question_without_answer_says_no_lo_se(self):
        bot = taught_bot()
        bot.respond('Ana vive en Lima.')
        self.assertTrue(bot.respond('¿Dónde vive Pedro?')['text'].startswith('No lo sé'))

    def test_untaught_bot_keeps_its_previous_behaviour(self):
        bot = Bot()
        bot.respond('Ana vive en Lima.')
        self.assertEqual(bot.respond('¿Ana vive en Lima?')['status'], 'unrecognized')

    def test_incremental_index_equals_a_rebuilt_one(self):
        bot = taught_bot()
        for text in ('Ana vive en Lima.', 'Luis tiene un perro.', 'El perro es negro.'):
            bot.respond(text)
            bot._reading_index()
        incremental = bot._reading_index_cache[1]
        bot._reading_index_cache = None
        self.assertEqual(bot._reading_index(), incremental)


if __name__ == '__main__':
    unittest.main()

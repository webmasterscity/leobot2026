"""G-55: «no» when another value of the same learned kind was said; G-56: the whole interrogative
phrase, learned optional words and non-core links held within a clause."""
import unittest

from tests.test_g54_conversation import given, P, D, N, V, A, X, NUM

ADV, AUX, C = 'ADV', 'AUX', 'CCONJ'


def kinds(bot, key, members):
    bot.reading_model['answer_kinds'] = {key: {'n': 40, 'classes': {'NOUN': 40},
                                               'members': {f'{m}\x1fNOUN': 5 for m in members}}}


class KindContrastTests(unittest.TestCase):
    def pets(self):
        said = 'Sofía tiene un perro .'
        question = '¿ Sofía tiene un gato ?'
        bot = given({
            said: (said.split(), [P, V, D, N, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'det', 'obj', 'punct']),
            question: (question.split(), [X, P, V, D, N, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'det', 'obj', 'punct'])})
        return bot, question

    def test_another_member_of_a_learned_kind_is_a_no(self):
        bot, question = self.pets()
        kinds(bot, 'que animal', ['perro', 'gato', 'caballo', 'vaca', 'loro'])
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No'))
        self.assertFalse(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))
        bot.kind_contrast = False             # G-46 alone: what is had is not an attribute
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_without_a_common_kind_nothing_is_denied(self):
        bot, question = self.pets()
        kinds(bot, 'que color', ['rojo', 'azul', 'verde', 'blanco', 'negro'])
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_numbers_written_alike_are_one_dimension(self):
        said = 'Participaron veinte estudiantes .'
        question = '¿ Participaron treinta estudiantes ?'
        bot = given({
            said: (said.split(), [V, NUM, N, X], [0, 3, 1, 1], ['root', 'nummod', 'nsubj', 'punct']),
            question: (question.split(), [X, V, NUM, N, X], [2, 0, 4, 2, 2], ['punct', 'root', 'nummod', 'nsubj', 'punct'])})
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No'))


class CoreLinkTests(unittest.TestCase):
    def test_a_modifier_hung_elsewhere_by_the_parser_still_holds(self):
        said = 'El fin de semana fue a visitar a su abuela .'
        question = '¿ Fue a visitar a su abuela el fin de semana ?'
        bot = given({
            said: (said.split(), [D, N, A, N, V, A, V, A, D, N, X], [2, 5, 4, 2, 0, 7, 5, 10, 10, 7, 5],
                   ['det', 'nsubj', 'case', 'nmod', 'root', 'mark', 'xcomp', 'case', 'det', 'obl', 'punct']),
            # The verb first: «Fue» taken as an auxiliary and the time hung from «abuela».
            question: (question.split(), [X, AUX, A, V, A, D, N, D, N, A, N, X],
                       [4, 4, 4, 0, 7, 7, 4, 9, 7, 11, 9, 4],
                       ['punct', 'aux', 'mark', 'root', 'case', 'det', 'obl', 'det', 'appos', 'case', 'nmod', 'punct'])})
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('Sí'))

    def test_who_does_what_stays_strict(self):
        said = 'Juan ama a María .'
        question = '¿ María ama a Juan ?'
        bot = given({
            said: (said.split(), [P, V, A, P, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'case', 'obj', 'punct']),
            question: (question.split(), [X, P, V, A, P, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'case', 'obj', 'punct'])})
        self.assertFalse(bot.verify_from_utterances(question)['text'].startswith('Sí'))

    def test_a_coordinated_clause_does_not_lend_its_place(self):
        said = 'Juan vive en Bogotá y trabaja en Cali .'
        question = '¿ Juan vive en Cali ?'
        bot = given({
            said: (said.split(), [P, V, A, P, C, V, A, P, X], [2, 0, 4, 2, 6, 2, 8, 6, 2],
                   ['nsubj', 'root', 'case', 'obl', 'cc', 'conj', 'case', 'obl', 'punct']),
            question: (question.split(), [X, P, V, A, P, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'case', 'obl', 'punct'])})
        self.assertFalse(bot.verify_from_utterances(question)['text'].startswith('Sí'))


class OptionalWordTests(unittest.TestCase):
    def test_a_learned_optional_modifier_nobody_said_is_not_asked_for(self):
        said = 'Ana tiene un sofá .'
        question = '¿ Ya tiene Ana un sofá ?'
        bot = given({
            said: (said.split(), [P, V, D, N, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'det', 'obj', 'punct']),
            question: (question.split(), [X, ADV, V, P, D, N, X], [3, 3, 0, 3, 6, 3, 3],
                       ['punct', 'advmod', 'root', 'nsubj', 'det', 'obj', 'punct'])})
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))
        for _ in range(40):
            bot.observe_question_presence('¿Ya llegó el tren?', 'El tren llegó a las tres.')
        self.assertIn('ya', bot._optional_words())
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('Sí'))
        bot.optional_words = False
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))


class GapPhraseTests(unittest.TestCase):
    def test_a_common_noun_complement_of_the_interrogative_phrase_is_part_of_the_gap(self):
        said = 'Rosa estudia los jueves .'
        question = '¿ Qué día de la semana estudia Rosa ?'
        bot = given({
            said: (said.split(), [P, V, D, N, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'det', 'obl', 'punct']),
            question: (question.split(), [X, D, N, A, D, N, V, P, X], [7, 3, 7, 6, 6, 3, 0, 7, 7],
                       ['punct', 'det', 'obl', 'case', 'det', 'nmod', 'root', 'nsubj', 'punct'])})
        bot.reading_model['category_nouns'] = ['dia']        # «día» learned as a category, as in the base
        self.assertEqual(bot.answer_by_structure(question)['text'], 'los jueves')
        bot.gap_phrase = False
        self.assertIsNone(bot.answer_by_structure(question))


if __name__ == '__main__':
    unittest.main()

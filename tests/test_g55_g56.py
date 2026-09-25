"""G-55: «no» when another value of the same learned kind was said; the check of core roles
traded between two question words (the part of G-56 kept when the rest was retired by rule 5.9)."""
import unittest

from tests.test_g54_conversation import given, P, D, N, V, A, X, NUM

def kinds(bot, key, members):
    bot.reading_model['answer_kinds'] = {key: {'n': 40, 'classes': {'NOUN': 40},
                                               'members': {f'{m}\x1fNOUN': 5 for m in members}}}


class KindContrastTests(unittest.TestCase):
    def days(self):
        said = 'Camila atiende los martes .'
        question = '¿ Camila atiende los lunes ?'
        bot = given({
            said: (said.split(), [P, V, D, N, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'det', 'obl', 'punct']),
            question: (question.split(), [X, P, V, D, N, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'det', 'obl', 'punct'])})
        return bot, question

    def test_another_member_of_a_learned_kind_is_a_no(self):
        bot, question = self.days()
        kinds(bot, 'que dia', ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'])
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No'))
        self.assertFalse(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))
        bot.kind_contrast = False             # G-46 alone: a bare time is not an attribute place
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_without_a_common_kind_nothing_is_denied(self):
        bot, question = self.days()
        kinds(bot, 'que color', ['rojo', 'azul', 'verde', 'blanco', 'negro'])
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_what_is_had_may_have_other_values(self):
        said = 'Sofía tiene un perro .'
        question = '¿ Sofía tiene un gato ?'
        bot = given({
            said: (said.split(), [P, V, D, N, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'det', 'obj', 'punct']),
            question: (question.split(), [X, P, V, D, N, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'det', 'obj', 'punct'])})
        kinds(bot, 'que animal', ['perro', 'gato', 'caballo', 'vaca', 'loro'])
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_a_kind_whose_noun_takes_a_complement_is_no_dimension(self):
        bot, question = self.days()
        kinds(bot, 'que tipo', ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'])
        self.assertFalse(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))
        bot.reading_model['answer_kinds']['que tipo']['complemented'] = 30     # «qué tipo de…», counted
        bot.__dict__.pop('_kind_members', None)
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_a_member_is_a_word_in_its_class(self):
        bot, question = self.days()
        bot.reading_model['answer_kinds'] = {'que dia': {'n': 40, 'classes': {'NOUN': 40},
                                                         'members': {'lunes\x1fNOUN': 5, 'martes\x1fVERB': 5}}}
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No lo sé'))

    def test_numbers_written_alike_are_one_dimension(self):
        said = 'Participaron veinte estudiantes .'
        question = '¿ Participaron treinta estudiantes ?'
        bot = given({
            said: (said.split(), [V, NUM, N, X], [0, 3, 1, 1], ['root', 'nummod', 'nsubj', 'punct']),
            question: (question.split(), [X, V, NUM, N, X], [2, 0, 4, 2, 2], ['punct', 'root', 'nummod', 'nsubj', 'punct'])})
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No'))


class RoleCheckTests(unittest.TestCase):
    def test_who_does_what_stays_strict(self):
        said = 'Juan ama a María .'
        question = '¿ María ama a Juan ?'
        bot = given({
            said: (said.split(), [P, V, A, P, X], [2, 0, 4, 2, 2], ['nsubj', 'root', 'case', 'obj', 'punct']),
            question: (question.split(), [X, P, V, A, P, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'case', 'obj', 'punct'])})
        self.assertFalse(bot.verify_from_utterances(question)['text'].startswith('Sí'))
        bot.role_check = False              # the check alone decides it
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('Sí'))


if __name__ == '__main__':
    unittest.main()

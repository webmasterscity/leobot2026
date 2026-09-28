"""G-103: prefix matching, value shapes and the usefulness model of the candidates."""
import unittest

from leobot import Bot
from leobot.context import CANDIDATES, DENSE_FEATURES, _shapes

TEXT = '''CLINICA DE PRUEBA

HORARIOS
Lunes a viernes: 8:00 a 18:00
Sábados: 9:00 a 13:00

TARIFAS
Consulta general: $80.000
Formas de pago: efectivo, tarjeta o transferencia.
'''


def model(**pairs):
    return {'dense': list(DENSE_FEATURES), 'mean': [0.0] * len(DENSE_FEATURES), 'scale': [1.0] * len(DENSE_FEATURES),
            'weights': [0.0] * len(DENSE_FEATURES), 'bias': 0.0, 'pairs': dict(pairs), 'pair_scale': 0.5,
            'calibration': [[-1e9, 0.1, 10], [0.0, 0.9, 10]], 'cite_from': 0.4}


class ShapeAndPrefixTests(unittest.TestCase):
    def test_shapes_abstract_characters_not_words(self):
        self.assertEqual(_shapes('Sábados $250.000 8:00 Av. Central'), ['SH:$d.d', 'SH:d:d'])
        self.assertEqual(_shapes('sin cifras ni símbolos'), [])

    def test_words_that_begin_alike_are_related(self):
        bot = Bot()
        bot.load_context(TEXT)
        related = dict(bot._related('pagar'))
        self.assertIn('pago', related)
        self.assertNotIn('pagar', related)
        self.assertEqual(bot._related('a'), [])

    def test_soft_prefix_finds_the_unit_and_can_be_switched_off(self):
        bot = Bot()
        bot.load_context(TEXT)
        terms = ['horar', 'sabado']
        with_soft = bot._rank(['sabad'], 'sabad')
        bot.soft_prefix = False
        without = bot._rank(['sabad'], 'sabad')
        self.assertIsNotNone(with_soft['unit'])
        self.assertEqual(bot.context_units[with_soft['unit']]['text'].split(':')[0], 'Sábados')
        self.assertNotEqual(with_soft['score'], without['score'])
        self.assertTrue(terms)


class CandidateModelTests(unittest.TestCase):
    def setUp(self):
        self.bot = Bot()
        self.bot.load_context(TEXT)

    def test_model_chooses_by_a_learned_pair_and_switch_restores_the_old_path(self):
        q = 'donde se paga'
        terms = self.bot.context_terms(q)
        without = self.bot._rank(terms, q)
        self.bot.context_model['usefulness'] = model(**{'que|SH:$d.d': 5.0})
        learned = self.bot._rank(self.bot.context_terms('que cuesta la consulta'), 'que cuesta la consulta')
        self.assertEqual(self.bot.context_units[learned['unit']]['text'], 'Consulta general: $80.000')
        self.assertLessEqual(learned['candidates'], CANDIDATES)
        self.bot.candidate_model = False
        again = self.bot._rank(terms, q)
        self.assertEqual(again['unit'], without['unit'])
        self.assertEqual(again['score'], without['score'])

    def test_calibrated_probability_sets_the_level_and_headings_are_never_answers(self):
        self.bot.context_model['usefulness'] = model()
        reply = self.bot.answer('a que hora abren los sabados')
        self.assertEqual(reply['status'], 'closest')
        self.assertNotIn(reply['evidence']['unit'], ('HORARIOS', 'TARIFAS'))
        self.assertGreaterEqual(reply['confidence'], 0.4)

    def test_no_word_in_common_gives_no_candidate_and_no_answer(self):
        self.bot.context_model['usefulness'] = model()
        reply = self.bot.answer('¿xyzzy plugh?')
        self.assertEqual(reply['status'], 'unknown')
        self.assertIsNone(reply['candidate'])

    def test_model_survives_saving_and_loading(self):
        import tempfile
        from pathlib import Path
        self.bot.context_model['usefulness'] = model(**{'pago|efectivo': 1.5})
        with tempfile.TemporaryDirectory() as tmp:
            self.bot.save(Path(tmp) / 'b.json')
            other = Bot.load(Path(tmp) / 'b.json')
        self.assertEqual(other.context_model['usefulness']['pairs'], {'pago|efectivo': 1.5})


if __name__ == '__main__':
    unittest.main()

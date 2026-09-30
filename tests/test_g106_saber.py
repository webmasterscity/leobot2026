import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.context import _number, _numbers


class GeneralKnowledgeStore(unittest.TestCase):
    def setUp(self):
        self.bot = Bot()
        self.bot.observe_relation('perro', 'IsA', 'mascota', 'fuente-a')
        self.bot.observe_relation('mascota', 'IsA', 'animal', 'fuente-b')

    def test_relations_both_ways_and_two_steps(self):
        links = set(self.bot.knowledge_related('perro'))
        self.assertIn(('mascota', 'IsA>'), links)
        self.assertIn(('animal', 'IsA>>'), links)
        self.assertIn(('perro', 'IsA<'), set(self.bot.knowledge_related('mascota')))
        self.assertTrue(self.bot.includes('perro', 'mascota'))
        # Nothing is chained without counted closure: two steps are not asserted as inclusion.
        self.assertFalse(self.bot.includes('perro', 'animal'))

    def test_duplicate_is_not_stored_twice(self):
        self.assertFalse(self.bot.observe_relation('perro', 'IsA', 'mascota', 'fuente-c'))
        self.assertEqual(self.bot.knowledge_model['count'], 2)

    def test_switch_and_restart(self):
        self.bot.general_knowledge = False
        self.assertEqual(self.bot.knowledge_related('perro'), [])
        del self.bot.general_knowledge
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bot.json'
            self.bot.save(path)
            again = Bot.load(path)
        self.assertEqual(sorted(again.knowledge_related('perro')), sorted(self.bot.knowledge_related('perro')))

    def test_kiosk_link_needs_a_learned_share(self):
        self.bot.load_context('Normas\nMascota: no se admite.\nHorario: de 9 a 18.')
        terms = self.bot.context_terms('¿Puedo entrar con mi perro?')
        _, gains, how, _ = self.bot._gains(terms, '')
        self.assertFalse(any(kind == 'knowledge' for row in how.values() if isinstance(row, dict) for kind in row.values()))
        self.bot.context_model['knowledge_share'] = {'IsA>': 0.5}
        _, gains, how, _ = self.bot._gains(terms, '')
        linked = [i for i, row in how.items() if i is not None and 'knowledge' in row.values()]
        self.assertEqual([self.bot.context_units[i]['text'] for i in linked], ['Mascota: no se admite.'])


class WrittenQuantities(unittest.TestCase):
    def test_notation(self):
        self.assertEqual(_number('5.000'), 5000.0)
        self.assertEqual(_number('1,5'), 1.5)
        self.assertEqual(_number('6,500.00'), 6500.0)
        self.assertEqual(_number('1.234.567'), 1234567.0)

    def test_times_and_codes_are_not_quantities(self):
        self.assertEqual([v for v, _, _ in _numbers('Abre 8:00, sala B2, hasta 50 personas')], [50.0])


class GeneralKnowledgeNegation(unittest.TestCase):
    def setUp(self):
        self.bot = Bot()
        for _ in range(5):
            self.bot.observe_parsed_sentence(
                ['El', 'perro', 'es', 'un', 'animal', '.'],
                ['DET', 'NOUN', 'AUX', 'DET', 'NOUN', 'PUNCT'],
                [2, 5, 5, 5, 0, 5], ['det', 'nsubj', 'cop', 'det', 'root', 'punct'])
            self.bot.observe_parsed_sentence(
                ['El', 'perro', 'no', 'es', 'un', 'animal', '.'],
                ['DET', 'NOUN', 'ADV', 'AUX', 'DET', 'NOUN', 'PUNCT'],
                [2, 6, 6, 6, 6, 0, 6], ['det', 'nsubj', 'advmod', 'cop', 'det', 'root', 'punct'],
                feats=['_', '_', 'Polarity=Neg', '_', '_', '_', '_'])
        self.bot.consolidate_syntax()
        self.bot.observe_relation('perro', 'IsA', 'animal', 'fuente')
        self.bot.observe_relation_template('IsA', '{0} es un {1}')

    def test_positive_relation_remains_answerable(self):
        self.assertEqual(self.bot.answer_general('¿El perro es un animal?')['status'], 'general_yes')

    def test_negated_relation_is_not_asserted_by_positive_templates(self):
        self.assertIsNone(self.bot.answer_general('¿El perro no es un animal?'))

    def test_enabled_route_does_not_affirm_a_negated_relation(self):
        self.bot.general_route = 'templates'
        reply = self.bot.respond('¿El perro no es un animal?')
        self.assertNotEqual(reply['status'], 'general_yes')
        self.assertFalse(reply['text'].startswith('Sí.'))

    def test_negator_is_learned_instead_of_named_in_the_engine(self):
        self.bot.syntax_model['negators'] = ['jamás']
        self.assertIsNone(self.bot.answer_general('¿El perro jamás es un animal?'))

    def test_first_question_after_teaching_a_new_negator_is_not_affirmed(self):
        for _ in range(5):
            self.bot.observe_parsed_sentence(
                ['El', 'perro', 'jamás', 'es', 'un', 'animal', '.'],
                ['DET', 'NOUN', 'ADV', 'AUX', 'DET', 'NOUN', 'PUNCT'],
                [2, 6, 6, 6, 6, 0, 6], ['det', 'nsubj', 'advmod', 'cop', 'det', 'root', 'punct'],
                feats=['_', '_', 'Polarity=Neg', '_', '_', '_', '_'])
        self.bot.general_route = 'templates'
        reply = self.bot.respond('¿El perro jamás es un animal?')
        self.assertNotEqual(reply['status'], 'general_yes')


if __name__ == '__main__':
    unittest.main()

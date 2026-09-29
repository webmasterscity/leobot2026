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


if __name__ == '__main__':
    unittest.main()

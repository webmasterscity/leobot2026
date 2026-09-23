"""V8.9 routes kept in the unified tree: learned procedures and learned goals in dialogue.

Each check has its control: a fresh bot, an unseen entity, a restart, or the
neighbouring family that a correction must not touch.
"""
import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.scalable import ScalableBot


def teach_procedures(bot):
    for text, b, a in [('triplica 2', (2,), (6,)), ('triplica 3', (3,), (9,)), ('triplica 5', (5,), (15,))]:
        bot.observe_transition(text, b, a)
    for text, b, a in [('suma uno a 2', (2,), (3,)), ('suma uno a 4', (4,), (5,)), ('suma uno a 6', (6,), (7,))]:
        bot.observe_transition(text, b, a)


def teach_world(bot):
    for text, before, after in [
        ('gato va de cocina a sala', [('en', 'gato', 'cocina')], [('en', 'gato', 'sala')]),
        ('gato va de sala a jardin', [('en', 'gato', 'sala')], [('en', 'gato', 'jardin')]),
        ('gato va de jardin a cocina', [('en', 'gato', 'jardin')], [('en', 'gato', 'cocina')]),
        ('gato va de cocina a jardin', [('en', 'gato', 'cocina')], [('en', 'gato', 'jardin')]),
    ]:
        bot.observe_symbolic_transition(text, before, after)
    for text, goal in [('necesito que gato quede en jardin', [('en', 'gato', 'jardin')]),
                       ('necesito que gato quede en sala', [('en', 'gato', 'sala')]),
                       ('necesito que gato quede en cocina', [('en', 'gato', 'cocina')])]:
        bot.observe_symbolic_goal(text, goal)


class LearnedProcedureRouteTest(unittest.TestCase):
    def test_executes_only_taught_procedure_and_reports_plain_number(self):
        bot = Bot(); teach_procedures(bot)
        r = bot.respond('triplica 7')
        self.assertEqual(r['status'], 'procedure_executed')
        self.assertEqual(r['result'], (21,))
        self.assertTrue(r['text'].endswith(': 21'))
        self.assertNotEqual(Bot().respond('triplica 7').get('status'), 'procedure_executed')

    def test_numbers_in_unrelated_sentences_do_not_trigger_a_procedure(self):
        bot = Bot(); teach_procedures(bot)
        for text in ('tengo 3 hermanos y 2 perros', 'el año 2020 fue largo', 'no triplica 4'):
            self.assertNotEqual(bot.respond(text).get('status'), 'procedure_executed', text)

    def test_correction_demotes_one_family_and_forgets_its_examples(self):
        bot = Bot(); teach_procedures(bot)
        report = bot.correct_transition('suma uno a 10', (10,), (99,))
        self.assertEqual(report['status'], 'procedure_demoted')
        self.assertNotEqual(bot.respond('suma uno a 10').get('status'), 'procedure_executed')
        self.assertEqual(bot.respond('triplica 4').get('result'), (12,))
        session = bot.procedures.sessions['suma uno a <n0>']
        self.assertFalse(any(skill in bot.programs.examples for skill in session['output_skills']))
        for text, b, a in [('suma uno a 1', (1,), (2,)), ('suma uno a 3', (3,), (4,)), ('suma uno a 5', (5,), (6,))]:
            bot.observe_transition(text, b, a)
        self.assertEqual(bot.respond('suma uno a 8').get('result'), (9,))
        self.assertEqual(bot.respond('suma uno a 10')['status'], 'procedure_corrected_conflict')

    def test_demoted_procedure_is_not_relearned_as_a_raw_fact(self):
        bot = Bot(); teach_procedures(bot)
        self.assertEqual(bot.correct_transition('suma uno a 10', (10,), (99,))['status'],
                         'procedure_demoted')
        before = len(bot.raw_relation_observations)
        for value in (10, 11, 12):
            self.assertEqual(bot.respond(f'suma uno a {value}')['status'],
                             'procedure_unresolved')
        self.assertEqual(len(bot.raw_relation_observations), before)
        self.assertEqual(bot.respond('triplica 4')['result'], (12,))

    def test_consistent_correction_is_an_ordinary_observation(self):
        bot = Bot(); teach_procedures(bot)
        report = bot.correct_transition('triplica 10', (10,), (30,))
        self.assertNotEqual(report['status'], 'procedure_demoted')
        self.assertEqual(bot.respond('triplica 4').get('result'), (12,))

    def test_conflicting_correction_stays_visible_after_general_relearning(self):
        bot = Bot(); teach_procedures(bot)
        self.assertEqual(bot.correct_transition('suma uno a 10', (10,), (99,))['status'],
                         'procedure_demoted')
        for value in (1, 3, 5):
            bot.observe_transition(f'suma uno a {value}', (value,), (value + 1,))
        self.assertEqual(bot.respond('suma uno a 8')['result'], (9,))
        conflict = bot.respond('suma uno a 10')
        self.assertEqual(conflict['status'], 'procedure_corrected_conflict')
        self.assertEqual(conflict['observed_after'], (99,))
        self.assertEqual(bot.respond('triplica 4')['result'], (12,))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            bot.save(path)
            restored = Bot.load(path)
        self.assertEqual(restored.respond('suma uno a 10')['status'],
                         'procedure_corrected_conflict')

    def test_corrected_conflict_survives_sqlite_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bot = ScalableBot(root / 'facts.db'); teach_procedures(bot)
            bot.correct_transition('suma uno a 10', (10,), (99,))
            for value in (1, 3, 5):
                bot.observe_transition(f'suma uno a {value}', (value,), (value + 1,))
            bot.save(root / 'state.json'); bot.close()
            restored = ScalableBot.load(root / 'state.json', root / 'facts.db')
            try:
                self.assertEqual(restored.respond('suma uno a 10')['status'],
                                 'procedure_corrected_conflict')
                self.assertEqual(restored.respond('triplica 4')['result'], (12,))
            finally:
                restored.close()

    def test_unmarked_spanish_question_does_not_teach_a_raw_fact(self):
        bot = Bot()
        before = len(bot.raw_relation_observations)
        self.assertEqual(bot.respond('hola qué tal el clima hoy')['status'], 'unrecognized')
        self.assertEqual(len(bot.raw_relation_observations), before)
        self.assertEqual(bot.respond('persona que coordina zona norte')['status'],
                         'raw_relation_pending')


class LearnedGoalRouteTest(unittest.TestCase):
    def test_plans_through_learned_goal_with_any_predicate_name(self):
        bot = Bot(); teach_world(bot)
        bot.execute_symbolic_transition('gato va de jardin a cocina', [('en', 'gato', 'jardin')])
        r = bot.respond('necesito que gato quede en sala')
        self.assertEqual(r['status'], 'symbolic_plan')
        self.assertEqual(r['goal_source'], 'learned_schema')
        self.assertIn('gato va de cocina a sala', r['text'])

    def test_goal_route_needs_learned_goal_construction(self):
        bot = Bot()
        for text, before, after in [
            ('gato va de cocina a sala', [('en', 'gato', 'cocina')], [('en', 'gato', 'sala')]),
            ('gato va de sala a jardin', [('en', 'gato', 'sala')], [('en', 'gato', 'jardin')]),
            ('gato va de jardin a cocina', [('en', 'gato', 'jardin')], [('en', 'gato', 'cocina')]),
        ]:
            bot.observe_symbolic_transition(text, before, after)
        self.assertNotEqual(bot.respond('necesito que gato quede en sala').get('status'), 'symbolic_plan')

    def test_unseen_entity_is_refused_not_planned(self):
        bot = Bot(); teach_world(bot)
        r = bot.respond('necesito que gato quede en marte')
        self.assertEqual(r['status'], 'symbolic_goal_unknown_entities')
        self.assertEqual(r['unseen'], ['marte'])

    def test_state_and_known_entities_survive_restart(self):
        bot = Bot(); teach_world(bot)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bot.json'
            bot.save(path)
            again = Bot.load(path)
            self.assertEqual(again.last_symbolic_state, bot.last_symbolic_state)
            self.assertEqual(again.respond('necesito que gato quede en sala')['status'], 'symbolic_plan')
            sbot = ScalableBot(Path(tmp) / 'kb.sqlite3'); teach_world(sbot)
            sbot.save(Path(tmp) / 'state.json')
            sagain = ScalableBot.load(Path(tmp) / 'state.json', Path(tmp) / 'kb.sqlite3')
            self.assertEqual(sagain.symbolic_entities, sbot.symbolic_entities)
            self.assertEqual(sagain.respond('necesito que gato quede en sala')['status'], 'symbolic_plan')
            sbot.close(); sagain.close()


if __name__ == '__main__':
    unittest.main()

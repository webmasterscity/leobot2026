"""A language hypothesis needs an observed answer to a discriminating question."""
import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


def ambiguous_bot(reverse=False, explicit_negative=True):
    kb = KnowledgeBase()
    for left, right in (('ana', 'luis'), ('cora', 'nora')):
        kb.add(Atom('ruta_a', (left, right)))
        kb.add(Atom('ruta_b', (left, right)))
    kb.add(Atom('ruta_a', ('bea', 'mario')))
    if explicit_negative:
        kb.add(Atom('!ruta_b', ('bea', 'mario')))
    bot = Bot(kb, allow_extensional_grounding=True)
    words = [('luis', 'ana'), ('nora', 'cora')] if reverse else [('ana', 'luis'), ('cora', 'nora')]
    for first, second in words:
        report = bot.respond(f'{first} cuida {second}')
        assert report['status'] == 'grounding_pending'
    return bot


class GroundingProbeTests(unittest.TestCase):
    def test_counterevidence_removes_a_fact_created_only_by_the_learned_phrase(self):
        bot = ambiguous_bot()
        proposal = bot.propose_grounding_probe()
        bot.observe_grounding_probe(proposal['probe_id'], True)
        stored = bot.respond('dana cuida ciro')
        self.assertEqual(stored['status'], 'stored')
        self.assertTrue(bot.kb.contains(Atom('ruta_a', ('dana', 'ciro'))))

        corrected = bot.observe_grounding_probe(proposal['probe_id'], False)
        self.assertEqual(corrected['status'], 'grounding_conflict')
        self.assertFalse(bot.kb.contains(Atom('ruta_a', ('dana', 'ciro'))))
        self.assertIsNone(bot.last_fact)

    def test_independent_support_for_the_same_fact_survives_language_rollback(self):
        bot = ambiguous_bot()
        proposal = bot.propose_grounding_probe()
        bot.observe_grounding_probe(proposal['probe_id'], True)
        bot.respond('dana cuida ciro')
        bot.language.teach('ana respalda luis',
                           {'act': 'assert', 'pred': 'ruta_a', 'args': ['ana', 'luis']})
        self.assertEqual(bot.respond('dana respalda ciro')['status'], 'stored')
        bot.kb.add(Atom('ruta_a', ('bea', 'ciro')), 'fuente independiente')

        bot.observe_grounding_probe(proposal['probe_id'], False)
        self.assertTrue(bot.kb.contains(Atom('ruta_a', ('dana', 'ciro'))))
        self.assertTrue(bot.kb.contains(Atom('ruta_a', ('bea', 'ciro'))))

    def test_question_uses_explicit_contrast_and_waits_for_external_answer(self):
        bot = ambiguous_bot()
        proposal = bot.propose_grounding_probe()
        self.assertEqual(proposal['status'], 'epistemic_action')
        self.assertEqual(proposal['probe_text'], 'bea cuida mario')
        self.assertEqual(bot.language.parse('dana cuida ciro')['status'], 'unrecognized')
        self.assertEqual(len(next(iter(bot.grounding_hypotheses.values()))['possible']), 2)

        learned = bot.observe_grounding_probe(proposal['probe_id'], True)
        self.assertEqual(learned['status'], 'grounding_promoted')
        self.assertEqual(bot.language.parse('dana cuida ciro')['frame'],
                         {'act': 'assert', 'pred': 'ruta_a', 'args': ['dana', 'ciro']})

    def test_reversed_roles_survive_restart_and_counterevidence_withdraws_them(self):
        bot = ambiguous_bot(reverse=True)
        proposal = bot.propose_grounding_probe()
        self.assertEqual(proposal['probe_text'], 'mario cuida bea')
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            bot.save(path)
            bot = Bot.load(path)
            self.assertEqual(bot.observe_grounding_probe(proposal['probe_id'], True)['status'],
                             'grounding_promoted')
            self.assertEqual(bot.language.parse('ciro cuida dana')['frame']['args'],
                             ['dana', 'ciro'])
            bot.save(path)
            bot = Bot.load(path)
            self.assertEqual(bot.language.parse('ciro cuida dana')['frame']['pred'], 'ruta_a')
            self.assertEqual(bot.observe_grounding_probe(proposal['probe_id'], False)['status'],
                             'grounding_conflict')
            self.assertEqual(bot.language.parse('ciro cuida dana')['status'], 'unrecognized')

    def test_absence_of_negative_fact_does_not_count_as_a_contrast(self):
        bot = ambiguous_bot(explicit_negative=False)
        proposal = bot.propose_grounding_probe()
        self.assertEqual(proposal['status'], 'no_epistemic_action')
        self.assertEqual(len(next(iter(bot.grounding_hypotheses.values()))['possible']), 2)


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V58ConditionalBootstrapTests(unittest.TestCase):
    CONDITIONS = [
        'si ana frobla caja a luis entonces caja zenda luis',
        'si bea frobla libro a mario entonces libro zenda mario',
        'si cora frobla mapa a nora entonces mapa zenda nora',
    ]

    def _learn(self, bot):
        before = bot.kb.stats()['facts']
        r1 = bot.respond(self.CONDITIONS[0])
        r2 = bot.respond(self.CONDITIONS[1])
        r3 = bot.respond(self.CONDITIONS[2])
        self.assertEqual([r1['status'], r2['status'], r3['status']],
                         ['conditional_unresolved',
                          'conditional_unresolved',
                          'conditional_bootstrap_learned'])
        self.assertEqual(r3['facts_added'], 0)
        self.assertEqual(bot.kb.stats()['facts'], before)
        self.assertEqual(len(bot.raw_relation_observations), 0)
        self.assertEqual(r3['rule']['status'], 'conditional_rule_learned')
        return r3

    def test_empty_ontology_bootstraps_clause_meanings_and_rule_without_asserting_hypotheses(self):
        bot = Bot(allow_extensional_grounding=False)
        learned = self._learn(bot)
        self.assertEqual(len(bot.raw_relation_promotions), 2)
        self.assertEqual(len(bot.kb.rules), 1)
        self.assertTrue(all(e['hypothetical'] for e in learned['body']['evidence']))
        self.assertTrue(all(e['fact_id'] is None for e in learned['head']['evidence']))

        stored = bot.respond('dora frobla carta a raul')
        self.assertEqual(stored['status'], 'stored')
        answer = bot.respond('¿carta zenda raul?')
        self.assertEqual(answer['status'], 'hypothesis')
        self.assertEqual(bot.kb.stats()['facts'], 1)

    def test_two_examples_do_not_promote_language_or_rule(self):
        bot = Bot(allow_extensional_grounding=False)
        self.assertEqual(bot.respond(self.CONDITIONS[0])['status'], 'conditional_unresolved')
        self.assertEqual(bot.respond(self.CONDITIONS[1])['status'], 'conditional_unresolved')
        self.assertEqual(bot.kb.stats()['facts'], 0)
        self.assertEqual(len(bot.kb.rules), 0)
        self.assertEqual(len(bot.raw_relation_promotions), 0)
        # A new assertion is still not semantically grounded by only two hypothetical examples.
        self.assertEqual(bot.respond('dora frobla carta a raul')['status'], 'raw_relation_pending')

    def test_duplicate_conditional_is_not_independent_support(self):
        bot = Bot(allow_extensional_grounding=False)
        first = bot.respond(self.CONDITIONS[0])
        duplicate = bot.respond(self.CONDITIONS[0])
        second = bot.respond(self.CONDITIONS[1])
        self.assertEqual(first['support'], 1)
        self.assertEqual(duplicate['support'], 1)
        self.assertEqual(second['support'], 2)
        self.assertEqual(len(bot.kb.rules), 0)

    def test_bootstrapped_rule_persists_in_memory_bot(self):
        bot = Bot(allow_extensional_grounding=False)
        learned = self._learn(bot)
        rule_id = learned['rule']['rule_id']
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            bot.save(path)
            loaded = Bot.load(path)
            self.assertIn(rule_id, loaded.kb.rules)
            self.assertTrue(loaded.conditional_bootstrap_observations)
            self.assertTrue(loaded.conditional_bootstrap_promotions)
            loaded.respond('dora frobla carta a raul')
            self.assertEqual(loaded.respond('¿carta zenda raul?')['status'], 'hypothesis')

    def test_bootstrapped_rule_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            side = Path(td) / 'state.json'
            bot = ScalableBot(db, allow_extensional_grounding=False)
            learned = self._learn(bot)
            rule_id = learned['rule']['rule_id']
            bot.save(side)
            bot.close()
            loaded = ScalableBot.load(side, db)
            try:
                self.assertIn(rule_id, loaded.kb.rules)
                self.assertTrue(loaded.conditional_bootstrap_promotions)
                loaded.respond('dora frobla carta a raul')
                self.assertEqual(loaded.respond('¿carta zenda raul?')['status'], 'hypothesis')
            finally:
                loaded.close()

    def test_raw_conjunction_is_not_bootstrapped_by_guessing_y_boundary(self):
        bot = Bot(allow_extensional_grounding=False)
        report = bot.respond('si ana frobla caja a luis y luis norga paris entonces caja zenda paris')
        self.assertEqual(report['status'], 'conditional_unresolved')
        self.assertEqual(report['reason'], 'raw_conjunction_bootstrap_not_yet_safe')
        self.assertEqual(bot.kb.stats()['facts'], 0)
        self.assertEqual(len(bot.kb.rules), 0)


if __name__ == '__main__':
    unittest.main()

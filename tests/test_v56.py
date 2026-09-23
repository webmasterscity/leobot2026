import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V56ConditionalRuleLearningTests(unittest.TestCase):
    BODY = [
        'ana entrega caja a luis',
        'bea entrega libro a mario',
        'cora entrega mapa a nora',
    ]
    HEAD = [
        'caja queda con luis',
        'libro queda con mario',
        'mapa queda con nora',
    ]
    CONDS = [
        'si dora entrega carta a raul entonces carta queda con raul',
        'si eva entrega paquete a sara entonces paquete queda con sara',
        'si fede entrega llave a tomas entonces llave queda con tomas',
    ]

    def _ground_surfaces(self, bot):
        for text in self.BODY:
            body = bot.respond(text)
        for text in self.HEAD:
            head = bot.respond(text)
        self.assertEqual(body['status'], 'raw_relation_learned')
        self.assertEqual(head['status'], 'raw_relation_learned')
        return body['predicate'], head['predicate']

    def _learn_rule(self, bot):
        body_pred, head_pred = self._ground_surfaces(bot)
        before = bot.kb.stats()['facts']
        r1 = bot.respond(self.CONDS[0])
        r2 = bot.respond(self.CONDS[1])
        r3 = bot.respond(self.CONDS[2])
        self.assertEqual(r1['status'], 'conditional_rule_pending')
        self.assertEqual(r1['support'], 1)
        self.assertEqual(r2['status'], 'conditional_rule_pending')
        self.assertEqual(r2['support'], 2)
        self.assertEqual(r3['status'], 'conditional_rule_learned')
        self.assertEqual(r3['support'], 3)
        self.assertEqual(bot.kb.stats()['facts'], before)
        return body_pred, head_pred, r3

    def test_three_independent_conditionals_induce_executable_rule(self):
        bot = Bot(allow_extensional_grounding=False)
        body_pred, head_pred, learned = self._learn_rule(bot)
        self.assertEqual(learned['mapping'], [1, 2])
        self.assertIn(learned['rule_id'], bot.kb.rules)
        self.assertEqual(bot.kb.rules[learned['rule_id']].head.pred, head_pred)
        self.assertEqual(bot.kb.rules[learned['rule_id']].body[0].pred, body_pred)

        self.assertEqual(bot.respond('gina entrega cuaderno a hugo')['status'], 'stored')
        answer = bot.respond('¿cuaderno queda con hugo?')
        self.assertEqual(answer['status'], 'hypothesis')
        self.assertTrue(any(p['id'] == learned['rule_id'] for p in answer['proofs']))

    def test_two_conditionals_do_not_generalize(self):
        bot = Bot(allow_extensional_grounding=False)
        self._ground_surfaces(bot)
        self.assertEqual(bot.respond(self.CONDS[0])['status'], 'conditional_rule_pending')
        self.assertEqual(bot.respond(self.CONDS[1])['status'], 'conditional_rule_pending')
        self.assertEqual(bot.respond('gina entrega cuaderno a hugo')['status'], 'stored')
        self.assertEqual(bot.respond('¿cuaderno queda con hugo?')['status'], 'unknown')
        self.assertFalse(any(r.id.startswith('conditional_') for r in bot.kb.rules.values()))

    def test_duplicate_conditional_does_not_count_as_independent_support(self):
        bot = Bot(allow_extensional_grounding=False)
        self._ground_surfaces(bot)
        first = bot.respond(self.CONDS[0])
        again = bot.respond(self.CONDS[0])
        self.assertEqual(first['support'], 1)
        self.assertEqual(again['support'], 1)
        self.assertTrue(again['duplicate'])

    def test_conflicting_role_mapping_blocks_or_withdraws_rule(self):
        bot = Bot(allow_extensional_grounding=False)
        self._learn_rule(bot)
        # Consequent now maps role 0 rather than role 1 of the antecedent.
        conflict = bot.respond('si iris entrega sobre a julio entonces iris queda con julio')
        self.assertEqual(conflict['status'], 'conditional_rule_ambiguous')
        self.assertTrue(conflict['withdrawn'])
        self.assertFalse(any(r.id.startswith('conditional_') for r in bot.kb.rules.values()))
        bot.respond('karen entrega carpeta a lucas')
        self.assertEqual(bot.respond('¿carpeta queda con lucas?')['status'], 'unknown')

    def test_unresolved_conditional_never_falls_through_to_raw_fact_learning(self):
        bot = Bot(allow_extensional_grounding=False)
        before_obs = len(bot.raw_relation_observations)
        before_facts = bot.kb.stats()['facts']
        report = bot.respond('si alfa zumba beta entonces gamma frena delta')
        self.assertEqual(report['status'], 'conditional_unresolved')
        self.assertEqual(len(bot.raw_relation_observations), before_obs)
        self.assertEqual(bot.kb.stats()['facts'], before_facts)

    def test_rule_hypothesis_and_rule_persist_in_memory_bot(self):
        bot = Bot(allow_extensional_grounding=False)
        _, _, learned = self._learn_rule(bot)
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / 'state.json'
            bot.save(state)
            loaded = Bot.load(state)
            self.assertIn(learned['rule_id'], loaded.kb.rules)
            self.assertTrue(loaded.conditional_rule_hypotheses)
            loaded.respond('gina entrega cuaderno a hugo')
            self.assertEqual(loaded.respond('¿cuaderno queda con hugo?')['status'], 'hypothesis')

    def test_rule_hypothesis_and_rule_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            side = Path(td) / 'state.json'
            bot = ScalableBot(db, allow_extensional_grounding=False)
            _, _, learned = self._learn_rule(bot)
            bot.save(side)
            bot.close()
            loaded = ScalableBot.load(side, db)
            try:
                self.assertIn(learned['rule_id'], loaded.kb.rules)
                self.assertTrue(loaded.conditional_rule_hypotheses)
                loaded.respond('gina entrega cuaderno a hugo')
                self.assertEqual(loaded.respond('¿cuaderno queda con hugo?')['status'], 'hypothesis')
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V59RawConjunctiveBootstrapTests(unittest.TestCase):
    CONDITIONS = [
        'si ana frobla caja a luis y luis norga paris entonces caja zenda paris',
        'si bea frobla libro a mario y mario norga roma entonces libro zenda roma',
        'si cora frobla mapa a nora y nora norga lima entonces mapa zenda lima',
    ]

    def _learn(self, bot):
        before = bot.kb.stats()['facts']
        r1 = bot.respond(self.CONDITIONS[0])
        r2 = bot.respond(self.CONDITIONS[1])
        r3 = bot.respond(self.CONDITIONS[2])
        self.assertEqual([r1['status'], r2['status'], r3['status']],
                         ['conditional_unresolved','conditional_unresolved','conditional_bootstrap_learned'])
        self.assertEqual(r1['reason'], 'raw_conjunction_bootstrap_not_yet_safe')
        self.assertEqual(r3['antecedents'], 2)
        self.assertEqual(r3['rule']['antecedents'], 2)
        self.assertEqual(bot.kb.stats()['facts'], before)
        return r3

    def test_empty_ontology_learns_unique_conjunction_boundary_and_rule(self):
        bot = Bot(allow_extensional_grounding=False)
        learned = self._learn(bot)
        self.assertEqual(len(learned['bodies']), 2)
        self.assertEqual(len(bot.raw_relation_promotions), 3)
        bot.respond('dora frobla carta a raul')
        bot.respond('raul norga madrid')
        self.assertEqual(bot.respond('¿carta zenda madrid?')['status'], 'hypothesis')

    def test_missing_join_still_prevents_derivation_after_bootstrap(self):
        bot = Bot(allow_extensional_grounding=False)
        self._learn(bot)
        bot.respond('dora frobla carta a raul')
        bot.respond('tomas norga madrid')
        self.assertEqual(bot.respond('¿carta zenda madrid?')['status'], 'unknown')

    def test_two_raw_conjunctive_examples_do_not_promote(self):
        bot = Bot(allow_extensional_grounding=False)
        for text in self.CONDITIONS[:2]:
            r = bot.respond(text)
            self.assertEqual(r['status'], 'conditional_unresolved')
        self.assertEqual(bot.kb.stats()['facts'], 0)
        self.assertEqual(len(bot.kb.rules), 0)
        self.assertEqual(len(bot.raw_relation_promotions), 0)

    def test_y_inside_variable_span_does_not_force_wrong_boundary(self):
        bot = Bot(allow_extensional_grounding=False)
        examples = [
            'si ana compra y vende caja a luis y luis norga paris entonces caja zenda paris',
            'si bea compra y vende libro a mario y mario norga roma entonces libro zenda roma',
            'si cora compra y vende mapa a nora y nora norga lima entonces mapa zenda lima',
        ]
        reports = [bot.respond(x) for x in examples]
        self.assertEqual(reports[-1]['status'], 'conditional_bootstrap_learned')
        self.assertEqual(reports[-1]['antecedents'], 2)
        self.assertEqual(reports[-1]['bodies'][0]['surface'], '{s0} compra y vende {s1} a {s2}')
        bot.respond('gina compra y vende carta a raul')
        bot.respond('raul norga madrid')
        self.assertEqual(bot.respond('¿carta zenda madrid?')['status'], 'hypothesis')

    def test_conjunctive_bootstrap_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            learned=self._learn(bot); rid=learned['rule']['rule_id']
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertIn(rid,loaded.kb.rules)
                loaded.respond('dora frobla carta a raul')
                loaded.respond('raul norga madrid')
                self.assertEqual(loaded.respond('¿carta zenda madrid?')['status'],'hypothesis')
            finally:
                loaded.close()


if __name__=='__main__': unittest.main()

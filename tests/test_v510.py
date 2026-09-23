import unittest

from leobot import Bot
from leobot.core import Atom


class V510NaturalNegationCompositionTests(unittest.TestCase):
    def _ground_delivery(self, bot):
        last=None
        for text in [
            'ana frobla caja a luis',
            'bea frobla libro a mario',
            'cora frobla mapa a nora',
        ]:
            last=bot.respond(text)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def _ground_blocked(self, bot):
        last=None
        for text in [
            'caja zenda luis',
            'libro zenda mario',
            'mapa zenda nora',
        ]:
            last=bot.respond(text)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def test_no_composes_with_learned_surface_and_stores_explicit_negative(self):
        bot=Bot(allow_extensional_grounding=False)
        pred=self._ground_delivery(bot)
        report=bot.respond('dora no frobla carta a raul')
        self.assertEqual(report['status'],'stored')
        self.assertTrue(bot.kb.contains(Atom('!'+pred,('dora','carta','raul'))))
        self.assertFalse(bot.kb.contains(Atom(pred,('dora no','carta','raul'))))

    def test_positive_query_is_refuted_and_negative_query_is_supported(self):
        bot=Bot(allow_extensional_grounding=False)
        self._ground_delivery(bot)
        bot.respond('dora no frobla carta a raul')
        positive=bot.respond('¿dora frobla carta a raul?')
        negative=bot.respond('¿dora no frobla carta a raul?')
        self.assertEqual(positive['status'],'refuted')
        self.assertEqual(negative['status'],'supported')
        self.assertIn('no (',negative['text'])

    def test_explicit_positive_and_negative_remain_conflict_not_last_write_wins(self):
        bot=Bot(allow_extensional_grounding=False)
        self._ground_delivery(bot)
        bot.respond('dora no frobla carta a raul')
        bot.respond('dora frobla carta a raul')
        answer=bot.respond('¿dora frobla carta a raul?')
        self.assertEqual(answer['status'],'conflict')
        self.assertTrue(answer['proofs'])
        self.assertTrue(answer['negative_proofs'])

    def test_repeated_no_is_rejected_without_mutating_memory(self):
        bot=Bot(allow_extensional_grounding=False)
        self._ground_delivery(bot)
        facts=bot.kb.stats()['facts']; raw=len(bot.raw_relation_observations)
        concepts=len(bot.concepts.sessions); schemas=len(bot.schemas.sessions)
        report=bot.respond('dora no no frobla carta a raul')
        self.assertEqual(report['status'],'unrecognized')
        self.assertEqual(report['reason'],'negation_ambiguous')
        self.assertEqual(bot.kb.stats()['facts'],facts)
        self.assertEqual(len(bot.raw_relation_observations),raw)
        self.assertEqual(len(bot.concepts.sessions),concepts)
        self.assertEqual(len(bot.schemas.sessions),schemas)

    def test_composed_negative_relation_can_be_rule_antecedent(self):
        bot=Bot(allow_extensional_grounding=False)
        body=self._ground_delivery(bot); head=self._ground_blocked(bot)
        conds=[
            'si dora no frobla carta a raul entonces carta zenda raul',
            'si eva no frobla paquete a sara entonces paquete zenda sara',
            'si fede no frobla llave a tomas entonces llave zenda tomas',
        ]
        reports=[bot.respond(x) for x in conds]
        self.assertEqual([r['status'] for r in reports],
                         ['conditional_rule_pending','conditional_rule_pending','conditional_rule_learned'])
        rule=bot.kb.rules[reports[-1]['rule_id']]
        self.assertEqual(rule.body[0].pred,'!'+body)
        self.assertEqual(rule.head.pred,head)
        bot.respond('gina no frobla cuaderno a hugo')
        self.assertEqual(bot.respond('¿cuaderno zenda hugo?')['status'],'hypothesis')


if __name__=='__main__': unittest.main()

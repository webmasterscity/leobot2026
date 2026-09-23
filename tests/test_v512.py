import unittest

from leobot import Bot


class V512HypotheticalPolarityBootstrapTests(unittest.TestCase):
    def test_negative_antecedent_bootstraps_base_surface_without_hypothetical_facts(self):
        bot=Bot(allow_extensional_grounding=False)
        conds=[
            'si ana no frobla caja a luis entonces caja zenda luis',
            'si bea no frobla libro a mario entonces libro zenda mario',
            'si cora no frobla mapa a nora entonces mapa zenda nora',
        ]
        reports=[bot.respond(x) for x in conds]
        self.assertEqual(reports[-1]['status'],'conditional_bootstrap_learned')
        self.assertTrue(reports[-1]['body']['negative'])
        self.assertFalse(reports[-1]['head']['negative'])
        self.assertEqual(bot.kb.stats()['facts'],0)
        rule=bot.kb.rules[reports[-1]['rule']['rule_id']]
        self.assertTrue(rule.body[0].pred.startswith('!'))
        self.assertFalse(rule.head.pred.startswith('!'))
        bot.respond('dora no frobla carta a raul')
        self.assertEqual(bot.respond('¿carta zenda raul?')['status'],'hypothesis')

    def test_negative_consequent_becomes_explicit_negative_rule_head(self):
        bot=Bot(allow_extensional_grounding=False)
        conds=[
            'si ana frobla caja a luis entonces caja no zenda luis',
            'si bea frobla libro a mario entonces libro no zenda mario',
            'si cora frobla mapa a nora entonces mapa no zenda nora',
        ]
        reports=[bot.respond(x) for x in conds]
        self.assertEqual(reports[-1]['status'],'conditional_bootstrap_learned')
        self.assertTrue(reports[-1]['head']['negative'])
        rule=bot.kb.rules[reports[-1]['rule']['rule_id']]
        self.assertTrue(rule.head.pred.startswith('!'))
        bot.respond('dora frobla carta a raul')
        self.assertEqual(bot.respond('¿carta zenda raul?')['status'],'negative_hypothesis')
        self.assertEqual(bot.respond('¿carta no zenda raul?')['status'],'hypothesis')

    def test_mixed_polarity_conjunction_bootstraps_and_preserves_join(self):
        bot=Bot(allow_extensional_grounding=False)
        conds=[
            'si ana no frobla caja a luis y luis norga paris entonces caja zenda paris',
            'si bea no frobla libro a mario y mario norga roma entonces libro zenda roma',
            'si cora no frobla mapa a nora y nora norga lima entonces mapa zenda lima',
        ]
        reports=[bot.respond(x) for x in conds]
        learned=reports[-1]
        self.assertEqual(learned['status'],'conditional_bootstrap_learned')
        self.assertEqual(learned['antecedents'],2)
        self.assertEqual([x['negative'] for x in learned['bodies']],[True,False])
        self.assertEqual(bot.kb.stats()['facts'],0)
        bot.respond('dora no frobla carta a raul')
        bot.respond('raul norga madrid')
        self.assertEqual(bot.respond('¿carta zenda madrid?')['status'],'hypothesis')
        # Wrong join must not derive.
        bot.respond('tomas norga quito')
        self.assertEqual(bot.respond('¿carta zenda quito?')['status'],'unknown')

    def test_polarity_disagreement_does_not_form_one_bootstrap_family(self):
        bot=Bot(allow_extensional_grounding=False)
        reports=[
            bot.respond('si ana no frobla caja a luis entonces caja zenda luis'),
            bot.respond('si bea no frobla libro a mario entonces libro zenda mario'),
            bot.respond('si cora frobla mapa a nora entonces mapa zenda nora'),
        ]
        self.assertNotEqual(reports[-1]['status'],'conditional_bootstrap_learned')
        self.assertEqual(bot.kb.stats()['facts'],0)
        self.assertEqual(len(bot.kb.rules),0)

    def test_two_negative_hypothetical_examples_are_insufficient(self):
        bot=Bot(allow_extensional_grounding=False)
        r1=bot.respond('si ana no frobla caja a luis entonces caja zenda luis')
        r2=bot.respond('si bea no frobla libro a mario entonces libro zenda mario')
        self.assertEqual([r1['status'],r2['status']],['conditional_unresolved','conditional_unresolved'])
        self.assertEqual(len(bot.kb.rules),0)
        self.assertEqual(bot.kb.stats()['facts'],0)


if __name__=='__main__': unittest.main()

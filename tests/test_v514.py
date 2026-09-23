import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V514MultiAntecedentConditionalTests(unittest.TestCase):
    THREE = [
        'si ana frobla caja a luis y luis norga paris y paris kima francia entonces caja zenda francia',
        'si bea frobla libro a mario y mario norga roma y roma kima italia entonces libro zenda italia',
        'si cora frobla mapa a nora y nora norga lima y lima kima peru entonces mapa zenda peru',
    ]

    FOUR = [
        f'si a{i} alfa b{i} y b{i} bravo c{i} y c{i} charlie d{i} y d{i} delta e{i} entonces a{i} omega e{i}'
        for i in range(4)
    ]

    def test_three_raw_antecedents_bootstrap_from_empty_ontology(self):
        bot=Bot(allow_extensional_grounding=False)
        reports=[bot.respond(x) for x in self.THREE]
        self.assertEqual([x['status'] for x in reports],
                         ['conditional_unresolved','conditional_unresolved','conditional_bootstrap_learned'])
        learned=reports[-1]
        self.assertEqual(learned['antecedents'],3)
        self.assertEqual(learned['required'],3)
        self.assertEqual(len(learned['bodies']),3)
        self.assertIsNotNone(learned['rule'])
        self.assertEqual(learned['rule']['status'],'conditional_rule_learned')
        self.assertEqual(bot.kb.stats()['facts'],0)
        bot.respond('dora frobla carta a raul')
        bot.respond('raul norga madrid')
        bot.respond('madrid kima espana')
        self.assertEqual(bot.respond('¿carta zenda espana?')['status'],'hypothesis')

    def test_four_antecedents_wait_for_four_supports_instead_of_promoting_partial_rule(self):
        bot=Bot(allow_extensional_grounding=False)
        first=[bot.respond(x) for x in self.FOUR[:3]]
        self.assertEqual(first[-1]['status'],'conditional_unresolved')
        self.assertEqual(first[-1]['reason'],'richer_connected_segmentation_needs_more_support')
        self.assertEqual(first[-1]['candidate_antecedents'],4)
        self.assertEqual(first[-1]['required'],4)
        self.assertEqual(len(bot.raw_relation_promotions),0)
        self.assertEqual(len(bot.kb.rules),0)
        learned=bot.respond(self.FOUR[3])
        self.assertEqual(learned['status'],'conditional_bootstrap_learned')
        self.assertEqual(learned['antecedents'],4)
        self.assertEqual(learned['required'],4)
        self.assertEqual(len(bot.kb.rules),1)
        bot.respond('ax alfa bx'); bot.respond('bx bravo cx')
        bot.respond('cx charlie dx'); bot.respond('dx delta ex')
        self.assertEqual(bot.respond('¿ax omega ex?')['status'],'hypothesis')

    def test_internal_y_is_not_oversegmented_when_multi_antecedent_learning_is_enabled(self):
        bot=Bot(allow_extensional_grounding=False)
        examples=[
            'si ana compra y vende caja a luis y luis norga paris entonces caja zenda paris',
            'si bea compra y vende libro a mario y mario norga roma entonces libro zenda roma',
            'si cora compra y vende mapa a nora y nora norga lima entonces mapa zenda lima',
        ]
        learned=[bot.respond(x) for x in examples][-1]
        self.assertEqual(learned['status'],'conditional_bootstrap_learned')
        self.assertEqual(learned['antecedents'],2)
        self.assertEqual(learned['bodies'][0]['surface'],'{s0} compra y vende {s1} a {s2}')

    def test_grounded_three_antecedent_rule_is_learned_without_raw_bootstrap(self):
        bot=Bot(allow_extensional_grounding=False)
        for rows in (
            ['ana alfa bob','bea alfa ben','cora alfa cal'],
            ['bob bravo carla','ben bravo dana','cal bravo erin'],
            ['carla charlie roma','dana charlie lima','erin charlie oslo'],
            ['ana omega roma','bea omega lima','cora omega oslo'],
        ):
            for text in rows:
                bot.respond(text)
        conditions=[
            'si dora alfa dan y dan bravo eli y eli charlie paris entonces dora omega paris',
            'si eva alfa ed y ed bravo fay y fay charlie roma entonces eva omega roma',
            'si gina alfa gus y gus bravo hal y hal charlie lima entonces gina omega lima',
        ]
        reports=[bot.respond(x) for x in conditions]
        self.assertEqual([r['status'] for r in reports],
                         ['conditional_rule_pending','conditional_rule_pending','conditional_rule_learned'])
        self.assertEqual(reports[-1]['antecedents'],3)
        bot.respond('iris alfa ian'); bot.respond('ian bravo jill'); bot.respond('jill charlie quito')
        self.assertEqual(bot.respond('¿iris omega quito?')['status'],'hypothesis')

    def test_multi_antecedent_bootstrap_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            learned=None
            for text in self.THREE:
                learned=bot.respond(text)
            rid=learned['rule']['rule_id']
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertIn(rid,loaded.kb.rules)
                loaded.respond('dora frobla carta a raul')
                loaded.respond('raul norga madrid')
                loaded.respond('madrid kima espana')
                self.assertEqual(loaded.respond('¿carta zenda espana?')['status'],'hypothesis')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

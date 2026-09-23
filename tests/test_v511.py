import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V511NegativeOnlyRawInductionTests(unittest.TestCase):
    NEGATIVE = [
        'ana no frobla caja a luis',
        'bea no frobla libro a mario',
        'cora no frobla mapa a nora',
    ]

    def _learn(self, bot):
        reports=[bot.respond(x) for x in self.NEGATIVE]
        self.assertEqual([r['status'] for r in reports],
                         ['raw_negative_relation_pending','raw_negative_relation_pending',
                          'raw_negative_relation_learned'])
        return reports[-1]

    def test_relation_can_be_discovered_from_negative_examples_only(self):
        bot=Bot(allow_extensional_grounding=False)
        learned=self._learn(bot); pred=learned['predicate']
        self.assertEqual(bot.raw_relation_observations,[])
        self.assertEqual(len(bot.raw_negative_relation_observations),3)
        self.assertEqual(bot.kb.stats()['facts'],3)
        for text,args in [
            (self.NEGATIVE[0],('ana','caja','luis')),
            (self.NEGATIVE[1],('bea','libro','mario')),
            (self.NEGATIVE[2],('cora','mapa','nora')),
        ]:
            self.assertTrue(bot.kb.contains(Atom('!'+pred,args)),text)
            self.assertFalse(bot.kb.contains(Atom(pred,args)),text)
        self.assertTrue(learned['construction_added'])
        self.assertTrue(learned['evidence'][0]['positive'] is False)

    def test_learned_affirmative_surface_can_be_used_after_negative_only_learning(self):
        bot=Bot(allow_extensional_grounding=False)
        learned=self._learn(bot); pred=learned['predicate']
        self.assertEqual(bot.respond('¿ana frobla caja a luis?')['status'],'refuted')
        self.assertEqual(bot.respond('¿ana no frobla caja a luis?')['status'],'supported')
        stored=bot.respond('dora frobla carta a raul')
        self.assertEqual(stored['status'],'stored')
        self.assertTrue(bot.kb.contains(Atom(pred,('dora','carta','raul'))))
        self.assertEqual(bot.respond('¿dora frobla carta a raul?')['status'],'supported')

    def test_negative_and_positive_raw_support_pools_do_not_merge(self):
        bot=Bot(allow_extensional_grounding=False)
        self.assertEqual(bot.respond(self.NEGATIVE[0])['status'],'raw_negative_relation_pending')
        self.assertEqual(bot.respond(self.NEGATIVE[1])['status'],'raw_negative_relation_pending')
        self.assertEqual(bot.respond('cora frobla mapa a nora')['status'],'raw_relation_pending')
        self.assertEqual(bot.raw_relation_promotions,{})
        self.assertEqual(len(bot.raw_negative_relation_observations),2)
        self.assertEqual(len(bot.raw_relation_observations),1)
        self.assertEqual(bot.kb.stats()['facts'],0)

    def test_direct_positive_raw_observer_still_rejects_negation(self):
        bot=Bot(allow_extensional_grounding=False)
        before=len(bot.raw_relation_observations)
        report=bot.observe_raw_relation('ana no frobla caja a luis')
        self.assertEqual(report['status'],'raw_relation_ignored')
        self.assertEqual(len(bot.raw_relation_observations),before)
        self.assertEqual(bot.raw_negative_relation_observations,[])

    def test_legacy_extensional_mode_does_not_use_new_negative_raw_inducer(self):
        bot=Bot(allow_extensional_grounding=True)
        report=bot.respond(self.NEGATIVE[0])
        self.assertNotEqual(report['status'],'raw_negative_relation_pending')
        self.assertEqual(bot.raw_negative_relation_observations,[])

    def test_negative_only_promotion_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            learned=self._learn(bot); pred=learned['predicate']
            bot.save(state); bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertEqual(len(loaded.raw_negative_relation_observations),3)
                self.assertTrue(loaded.kb.contains(Atom('!'+pred,('ana','caja','luis'))))
                self.assertEqual(loaded.respond('¿ana frobla caja a luis?')['status'],'refuted')
                self.assertEqual(loaded.respond('dora frobla carta a raul')['status'],'stored')
            finally:
                loaded.close()


if __name__=='__main__': unittest.main()

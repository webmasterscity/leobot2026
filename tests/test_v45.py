import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase
from leobot.scalable import ScalableBot


SUPPORT = [
    'equipo alfa enlaza modulo rojo',
    'grupo beta enlaza pieza azul',
    'unidad gamma enlaza nodo verde',
]


class V45RawPrimitiveInductionTests(unittest.TestCase):
    def test_induces_new_opaque_relation_without_known_entities_or_predicate(self):
        bot=Bot(KnowledgeBase())
        all_entities={'equipo alfa','modulo rojo','grupo beta','pieza azul','unidad gamma','nodo verde'}
        self.assertEqual(bot.kb.known_entities(all_entities),set())
        self.assertEqual(bot.language.parse('sector delta enlaza terminal blanca')['status'],'unrecognized')
        self.assertEqual(bot.respond(SUPPORT[0])['status'],'raw_relation_pending')
        self.assertEqual(bot.respond(SUPPORT[1])['status'],'raw_relation_pending')
        learned=bot.respond(SUPPORT[2])
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['surface'],'{s0} enlaza {s1}')
        pred=learned['predicate']
        self.assertTrue(pred.startswith('primitive_'))
        self.assertEqual(bot.kb.known_entities(all_entities),all_entities)
        held=bot.language.parse('sector delta enlaza terminal blanca')
        self.assertEqual(held['status'],'parsed')
        self.assertEqual(held['frame']['pred'],pred)
        self.assertEqual(held['frame']['args'],['sector delta','terminal blanca'])
        stored=bot.respond('sector delta enlaza terminal blanca')
        self.assertEqual(stored['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('sector delta','terminal blanca')))['status'],'supported')

    def test_function_word_only_anchor_does_not_promote(self):
        bot=Bot(KnowledgeBase())
        for text in ['alfa con beta','gamma con delta','epsilon con zeta']:
            report=bot.observe_raw_relation(text)
        self.assertEqual(report['status'],'raw_relation_pending')
        self.assertEqual(bot.raw_relation_promotions,{})
        self.assertEqual(bot.language.parse('theta con iota')['status'],'unrecognized')

    def test_ambiguous_repeated_anchor_blocks_promotion(self):
        bot=Bot(KnowledgeBase())
        bot.observe_raw_relation('alfa enlaza beta')
        bot.observe_raw_relation('gamma enlaza delta')
        report=bot.observe_raw_relation('epsilon enlaza zeta enlaza eta')
        self.assertEqual(report['status'],'raw_relation_pending')
        self.assertEqual(bot.raw_relation_promotions,{})

    def test_pending_and_promoted_state_persist(self):
        bot=Bot(KnowledgeBase())
        bot.respond(SUPPORT[0]); bot.respond(SUPPORT[1])
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'pending.json'; bot.save(path); loaded=Bot.load(path)
            self.assertEqual(len(loaded.raw_relation_observations),2)
            learned=loaded.respond(SUPPORT[2])
            self.assertEqual(learned['status'],'raw_relation_learned')
            path2=Path(td)/'promoted.json'; loaded.save(path2); loaded2=Bot.load(path2)
            self.assertEqual(len(loaded2.raw_relation_promotions),1)
            self.assertEqual(loaded2.respond('persona omega enlaza artefacto cobre')['status'],'stored')

    def test_scalable_persistence_keeps_raw_induction(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db)
            try:
                for text in SUPPORT:
                    report=bot.respond(text)
                self.assertEqual(report['status'],'raw_relation_learned')
                pred=report['predicate']; bot.save(state)
            finally:
                bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertEqual(loaded.respond('persona persistente enlaza modulo persistente')['status'],'stored')
                self.assertEqual(loaded.answer_atom(Atom(pred,('persona persistente','modulo persistente')))['status'],'supported')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

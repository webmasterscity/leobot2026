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


class V50ReleaseStabilityTests(unittest.TestCase):
    def test_questions_and_negations_never_enter_raw_assertion_learning(self):
        bot=Bot(KnowledgeBase())
        before=len(bot.raw_relation_observations)
        for text in [
            '¿equipo alfa enlaza modulo rojo?',
            '¿que enlaza equipo alfa?',
            'equipo alfa no enlaza modulo rojo',
            '/consulta enlaza equipo alfa modulo rojo',
        ]:
            bot.observe_raw_relation(text)
        self.assertEqual(len(bot.raw_relation_observations), before)
        self.assertEqual(bot.raw_relation_promotions, {})

    def test_safe_default_survives_scalable_restart(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db)
            try:
                self.assertFalse(bot.allow_extensional_grounding)
                for text in SUPPORT:
                    learned=bot.respond(text)
                self.assertEqual(learned['status'],'raw_relation_learned')
                pred=learned['predicate']
                bot.save(state)
            finally:
                bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertFalse(loaded.allow_extensional_grounding)
                out=loaded.respond('sector delta enlaza terminal blanca')
                self.assertEqual(out['status'],'stored')
                self.assertTrue(loaded.kb.contains(Atom(pred,('sector delta','terminal blanca'))))
            finally:
                loaded.close()

    def test_legacy_flag_survives_scalable_restart(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=True)
            try:
                bot.save(state)
            finally:
                bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertTrue(loaded.allow_extensional_grounding)
            finally:
                loaded.close()

    def test_fronted_wh_is_still_conservatively_unsupported_in_v50(self):
        bot=Bot(KnowledgeBase())
        for text in SUPPORT:
            bot.respond(text)
        before=bot.kb.stats()['facts']
        out=bot.respond('¿que enlaza equipo alfa?')
        self.assertEqual(out['status'],'grounding_pending')
        self.assertEqual(bot.kb.stats()['facts'],before)

    def test_safe_default_never_relabels_existing_extensional_predicate(self):
        bot=Bot(KnowledgeBase())
        for pred,args in [
            ('trabaja',('a0','b0')),('trabaja',('a1','b1')),('trabaja',('a2','b2')),
        ]:
            bot.kb.add(Atom(pred,args),'seed')
        reports=[bot.respond(f'a{i} verboinventado b{i}') for i in range(3)]
        self.assertEqual(reports[-1]['status'],'raw_relation_learned')
        invented=reports[-1]['predicate']
        self.assertNotEqual(invented,'trabaja')
        self.assertTrue(bot.kb.contains(Atom(invented,('a2','b2'))))
        self.assertTrue(bot.kb.contains(Atom('trabaja',('a2','b2'))))  # seed only, no relabeling needed
        extra=bot.respond('a3 verboinventado b3')
        self.assertEqual(extra['status'],'stored')
        self.assertFalse(bot.kb.contains(Atom('trabaja',('a3','b3'))))
        self.assertTrue(bot.kb.contains(Atom(invented,('a3','b3'))))


if __name__=='__main__':
    unittest.main()

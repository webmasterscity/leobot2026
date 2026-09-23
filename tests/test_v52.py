import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase
from leobot.scalable import ScalableBot


class V52OpenRawArityTests(unittest.TestCase):
    def test_unary_raw_relation_from_zero_ontology(self):
        bot=Bot(KnowledgeBase())
        rows=['alfa vibra','beta vibra','gamma vibra']
        self.assertEqual(bot.respond(rows[0])['status'],'raw_relation_pending')
        self.assertEqual(bot.respond(rows[1])['status'],'raw_relation_pending')
        learned=bot.respond(rows[2])
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],1)
        self.assertEqual(learned['surface'],'{s0} vibra')
        pred=learned['predicate']
        self.assertEqual(bot.respond('delta vibra')['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('delta',)))['status'],'supported')

    def test_ternary_raw_relation_from_zero_ontology(self):
        bot=Bot(KnowledgeBase())
        rows=['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']
        for row in rows[:-1]: self.assertEqual(bot.respond(row)['status'],'raw_relation_pending')
        learned=bot.respond(rows[-1])
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],3)
        self.assertEqual(learned['surface'],'{s0} entrega {s1} a {s2}')
        pred=learned['predicate']
        parsed=bot.language.parse('dina entrega llave a oscar')
        self.assertEqual(parsed['status'],'parsed')
        self.assertEqual(parsed['frame']['args'],['dina','llave','oscar'])
        self.assertEqual(bot.respond('dina entrega llave a oscar')['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('dina','llave','oscar')))['status'],'supported')

    def test_four_role_surface_is_not_promoted_by_bounded_inducer(self):
        bot=Bot(KnowledgeBase())
        rows=['ana mueve caja de casa a oficina','bea mueve libro de plaza a tienda','cora mueve mapa de cuarto a taller']
        report=None
        for row in rows: report=bot.respond(row)
        self.assertNotEqual(report['status'],'raw_relation_learned')
        self.assertEqual(bot.raw_relation_promotions,{})

    def test_questions_and_negation_do_not_become_raw_support(self):
        bot=Bot(KnowledgeBase())
        for row in ['alfa vibra','beta vibra']:
            bot.respond(row)
        self.assertNotEqual(bot.respond('¿quien vibra?')['status'],'raw_relation_learned')
        self.assertNotEqual(bot.respond('gamma no vibra')['status'],'raw_relation_learned')
        learned=bot.respond('gamma vibra')
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],1)

    def test_ternary_primitive_feeds_later_schema_learning(self):
        bot=Bot(KnowledgeBase())
        for row in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            learned=bot.respond(row)
        pred=learned['predicate']
        reports=[]
        for row in ['ana gestiona caja para luis','bea gestiona libro para mario',
                    'ana no gestiona caja para mario','ana no gestiona libro para luis']:
            reports.append(bot.observe_schema_statement(row))
        self.assertEqual(reports[-1]['status'],'schema_learned')
        self.assertEqual(reports[-1]['learning']['arity'],3)
        self.assertIn(pred,reports[-1]['learning']['selected'])
        self.assertEqual(bot.query_schema('cora gestiona mapa para nora')['status'],'entailed')
        self.assertNotEqual(bot.query_schema('cora gestiona mapa para mario')['status'],'entailed')

    def test_unary_and_ternary_promotions_persist(self):
        bot=Bot(KnowledgeBase())
        for row in ['alfa vibra','beta vibra','gamma vibra']: u=bot.respond(row)
        for row in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']: t=bot.respond(row)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            self.assertEqual(loaded.respond('delta vibra')['status'],'stored')
            self.assertEqual(loaded.respond('dina entrega llave a oscar')['status'],'stored')
            self.assertEqual(loaded.answer_atom(Atom(u['predicate'],('delta',)))['status'],'supported')
            self.assertEqual(loaded.answer_atom(Atom(t['predicate'],('dina','llave','oscar')))['status'],'supported')

    def test_scalable_ternary_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db)
            try:
                for row in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
                    learned=bot.respond(row)
                pred=learned['predicate']; bot.save(state)
            finally:
                bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertEqual(loaded.respond('dina entrega llave a oscar')['status'],'stored')
                self.assertEqual(loaded.answer_atom(Atom(pred,('dina','llave','oscar')))['status'],'supported')
            finally:
                loaded.close()


if __name__=='__main__': unittest.main()

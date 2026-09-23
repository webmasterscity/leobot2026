import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


class V52RawOpenArityTests(unittest.TestCase):
    def test_unary_primitive_is_induced_from_raw_text(self):
        bot=Bot(KnowledgeBase())
        for text in ['alfa florece','beta florece']:
            self.assertEqual(bot.respond(text)['status'],'raw_relation_pending')
        learned=bot.respond('gamma florece')
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],1)
        pred=learned['predicate']
        held=bot.respond('delta florece')
        self.assertEqual(held['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('delta',)))['status'],'supported')

    def test_ternary_primitive_is_induced_without_known_entities(self):
        bot=Bot(KnowledgeBase())
        support=[
            'sujeto alfa coordina modulo rojo en zona norte',
            'sujeto beta coordina modulo azul en zona sur',
            'sujeto gamma coordina modulo verde en zona este',
        ]
        for text in support[:-1]:
            self.assertEqual(bot.respond(text)['status'],'raw_relation_pending')
        learned=bot.respond(support[-1])
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],3)
        self.assertEqual(learned['surface'],'sujeto {s0} coordina modulo {s1} en zona {s2}')
        pred=learned['predicate']
        parsed=bot.language.parse('sujeto delta coordina modulo cobre en zona oeste')
        self.assertEqual(parsed['status'],'parsed')
        self.assertEqual(parsed['frame']['args'],['delta','cobre','oeste'])
        self.assertEqual(bot.respond('sujeto delta coordina modulo cobre en zona oeste')['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('delta','cobre','oeste')))['status'],'supported')

    def test_constant_span_is_not_invented_as_a_role(self):
        bot=Bot(KnowledgeBase())
        support=[
            'sujeto alfa coordina modulo rojo en zona norte',
            'sujeto beta coordina modulo azul en zona norte',
            'sujeto gamma coordina modulo verde en zona norte',
        ]
        for text in support:
            report=bot.respond(text)
        self.assertEqual(report['status'],'raw_relation_learned')
        self.assertEqual(report['arity'],2)
        self.assertIn('zona norte',report['surface'])

    def test_four_role_primitive_is_inferred_without_arity_annotation(self):
        bot=Bot(KnowledgeBase())
        support=[
            'agente alfa asigna objeto rojo desde origen norte hacia destino uno',
            'agente beta asigna objeto azul desde origen sur hacia destino dos',
            'agente gamma asigna objeto verde desde origen este hacia destino tres',
        ]
        for text in support:
            report=bot.respond(text)
        # Unified V6.3 keeps the V5.13 rule: evidence proportional to arity.
        # Three episodes cannot certify four independent roles.
        self.assertEqual(report['status'],'raw_relation_pending')
        report=bot.respond('agente delta asigna objeto cobre desde origen oeste hacia destino cuatro')
        self.assertEqual(report['status'],'raw_relation_learned')
        self.assertEqual(report['arity'],4)
        pred=report['predicate']
        parsed=bot.language.parse('agente epsilon asigna objeto plata desde origen centro hacia destino cinco')
        self.assertEqual(parsed['status'],'parsed')
        self.assertEqual(parsed['frame']['pred'],pred)
        self.assertEqual(parsed['frame']['args'],['epsilon','plata','centro','cinco'])

    def test_ternary_persists_across_restart(self):
        bot=Bot(KnowledgeBase())
        for text in [
            'agente alfa conecta recurso rojo mediante canal norte',
            'agente beta conecta recurso azul mediante canal sur',
            'agente gamma conecta recurso verde mediante canal este',
        ]:
            report=bot.respond(text)
        self.assertEqual(report['arity'],3)
        pred=report['predicate']
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            self.assertEqual(loaded.respond('agente delta conecta recurso cobre mediante canal oeste')['status'],'stored')
            self.assertEqual(loaded.answer_atom(Atom(pred,('delta','cobre','oeste')))['status'],'supported')

    def test_repeated_command_like_surfaces_do_not_become_raw_facts(self):
        bot=Bot(KnowledgeBase())
        for text in ['resume documento alfa','resume documento beta','resume documento gamma']:
            report=bot.observe_raw_relation(text)
        self.assertNotEqual(report['status'],'raw_relation_learned')
        self.assertEqual(bot.raw_relation_promotions,{})
        self.assertEqual(bot.kb.stats()['facts'],0)

    def test_repeated_anchor_ambiguity_still_blocks_promotion(self):
        bot=Bot(KnowledgeBase())
        for text in [
            'alfa enlaza beta',
            'gamma enlaza delta',
            'epsilon enlaza zeta enlaza eta',
        ]:
            report=bot.observe_raw_relation(text)
        self.assertNotEqual(report['status'],'raw_relation_learned')
        self.assertEqual(bot.raw_relation_promotions,{})


if __name__=='__main__':
    unittest.main()

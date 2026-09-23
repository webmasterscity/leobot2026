import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.concepts import ConceptGrounder
from leobot.core import Atom, KnowledgeBase
from leobot.schemas import OpenArityConceptGrounder
from leobot.scalable import ScalableBot


def ternary_world(count=8):
    kb=KnowledgeBase()
    for i in range(count):
        kb.add(Atom('posee',(f'persona{i}',f'objeto{i}')))
        kb.add(Atom('ubicado',(f'objeto{i}',f'lugar{i}')))
    return kb


class V40OpenArityTests(unittest.TestCase):
    def test_ternary_arity_is_forced_by_contrastive_projection_conflicts(self):
        kb=ternary_world()
        learner=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
        examples=[
            'persona0 enlaza objeto0 con lugar0',
            'persona1 enlaza objeto1 con lugar1',
            'persona0 no enlaza objeto0 con lugar1',  # same roles 0,1 as positive
            'persona0 no enlaza objeto1 con lugar0',  # same roles 0,2 as positive
            'persona1 no enlaza objeto0 con lugar0',  # same roles 1,2 as positive
        ]
        report=None
        for text in examples:
            report=learner.observe(text)
        self.assertEqual(report['status'],'schema_learned')
        self.assertEqual(report['learning']['arity'],3)
        self.assertEqual(report['learning']['projection'],[0,1,2])
        self.assertEqual(report['learning']['selected'],'posee(r0,r1) & ubicado(r1,r2)')
        self.assertGreaterEqual(report['learning']['projection_rejections'],6)
        self.assertEqual(learner.resolve('persona6 enlaza objeto6 con lugar6')['status'],'entailed')
        self.assertEqual(learner.resolve('persona6 enlaza objeto6 con lugar7')['status'],'unknown')
        # The old binary concept learner cannot even form this three-mention concept.
        self.assertIsNone(ConceptGrounder(kb).parse('persona6 enlaza objeto6 con lugar6'))

    def test_binary_arity_and_role_subset_are_inferred_with_a_distractor(self):
        kb=KnowledgeBase()
        for a,b in [('ana','eva'),('bruno','fabio'),('carla','gabi')]:
            kb.add(Atom('mentor',(a,b)))
        for city in ('norte','sur'):
            kb.add(Atom('zona',(city,)))
        learner=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
        examples=[
            'ana en norte guia eva',
            'bruno en sur guia fabio',
            'ana en norte no guia fabio',
            'bruno en norte no guia eva',
        ]
        report=None
        for text in examples:
            report=learner.observe(text)
        self.assertEqual(report['status'],'schema_learned')
        self.assertEqual(report['learning']['arity'],2)
        self.assertEqual(report['learning']['projection'],[0,2])
        self.assertEqual(report['learning']['selected'],'mentor(r0,r1)')
        self.assertEqual(learner.resolve('carla en norte guia gabi')['status'],'entailed')

    def test_unary_role_can_be_selected_from_three_surface_mentions(self):
        kb=KnowledgeBase()
        for person in ('ana','bruno','carla'):
            kb.add(Atom('activo',(person,)))
        for person in ('dario','elena'):
            kb.add(Atom('persona',(person,)))
        for city in ('norte','sur'):
            kb.add(Atom('zona',(city,)))
        for obj in ('caja','mesa'):
            kb.add(Atom('objeto',(obj,)))
        learner=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
        examples=[
            'norte ana junto a caja destaca',
            'sur bruno junto a mesa destaca',
            'norte dario junto a mesa no destaca',
            'sur elena junto a caja no destaca',
        ]
        report=None
        for text in examples:
            report=learner.observe(text)
        self.assertEqual(report['status'],'schema_learned')
        self.assertEqual(report['learning']['arity'],1)
        self.assertEqual(report['learning']['projection'],[1])
        self.assertEqual(report['learning']['selected'],'activo(r0)')
        self.assertEqual(learner.resolve('norte carla junto a mesa destaca')['status'],'entailed')

    def test_new_surface_infers_role_reordering_and_persists(self):
        kb=ternary_world()
        bot=Bot(kb)
        root=[
            'persona0 enlaza objeto0 con lugar0',
            'persona1 enlaza objeto1 con lugar1',
            'persona0 no enlaza objeto0 con lugar1',
            'persona0 no enlaza objeto1 con lugar0',
            'persona1 no enlaza objeto0 con lugar0',
        ]
        for text in root:
            bot.observe_schema_statement(text)
        alias=[
            'en lugar0 objeto0 corresponde a persona0',
            'en lugar1 objeto1 corresponde a persona1',
            'en lugar1 objeto0 no corresponde a persona0',
            'en lugar0 objeto1 no corresponde a persona0',
        ]
        report=None
        for text in alias:
            report=bot.observe_schema_statement(text)
        self.assertEqual(report['status'],'schema_alias_learned')
        self.assertEqual(report['alias']['mapping'],[2,1,0])
        self.assertEqual(bot.query_schema('en lugar6 objeto6 corresponde a persona6')['status'],'entailed')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bot.json'
            bot.save(path)
            loaded=Bot.load(path)
            self.assertEqual(loaded.query_schema('en lugar7 objeto7 corresponde a persona7')['status'],'entailed')
            session=loaded.schemas.sessions['en <e0> <e1> corresponde a <e2>']
            self.assertEqual(session['alias_mapping'],[2,1,0])

    def test_hidden_event_node_is_invented_as_one_existential_role(self):
        kb=KnowledgeBase()
        for i in range(8):
            event=f'evento{i}'
            kb.add(Atom('actor',(event,f'persona{i}')))
            kb.add(Atom('tema',(event,f'objeto{i}')))
            kb.add(Atom('sitio',(event,f'lugar{i}')))
        learner=OpenArityConceptGrounder(kb,min_positive=2,min_negative=2)
        examples=[
            'persona0 vincula objeto0 en lugar0',
            'persona1 vincula objeto1 en lugar1',
            'persona0 no vincula objeto0 en lugar1',
            'persona0 no vincula objeto1 en lugar0',
            'persona1 no vincula objeto0 en lugar0',
        ]
        report=None
        for text in examples:
            report=learner.observe(text)
        self.assertEqual(report['status'],'schema_learned')
        self.assertEqual(report['learning']['arity'],3)
        self.assertIn('z',report['learning']['selected'])
        self.assertEqual(report['learning']['selected'],
                         'actor(z,r0) & sitio(z,r2) & tema(z,r1)')
        self.assertEqual(learner.resolve('persona6 vincula objeto6 en lugar6')['status'],'entailed')
        self.assertEqual(learner.resolve('persona6 vincula objeto6 en lugar7')['status'],'unknown')

    def test_scalable_bot_persists_open_arity_schema(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db)
            try:
                for i in range(4):
                    bot.kb.add(Atom('posee',(f'persona{i}',f'objeto{i}')))
                    bot.kb.add(Atom('ubicado',(f'objeto{i}',f'lugar{i}')))
                for text in [
                    'persona0 enlaza objeto0 con lugar0',
                    'persona1 enlaza objeto1 con lugar1',
                    'persona0 no enlaza objeto0 con lugar1',
                    'persona0 no enlaza objeto1 con lugar0',
                    'persona1 no enlaza objeto0 con lugar0',
                ]:
                    bot.observe_schema_statement(text)
                bot.save(state)
            finally:
                bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertEqual(loaded.query_schema('persona3 enlaza objeto3 con lugar3')['status'],'entailed')
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

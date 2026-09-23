import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase
from leobot.schemas import OpenArityConceptGrounder
from leobot.scalable import ScalableBot


def train_two_binary_surfaces(bot, count=8):
    for i in range(count):
        bot.kb.add(Atom('socio',(f'persona{i}',f'objeto{i}')))
        bot.kb.add(Atom('sitio',(f'objeto{i}',f'lugar{i}')))
    for text in [
        'persona0 conecta objeto0',
        'persona1 conecta objeto1',
        'persona0 no conecta objeto1',
        'persona1 no conecta objeto0',
    ]:
        first=bot.observe_schema_statement(text)
    for text in [
        'objeto0 descansa en lugar0',
        'objeto1 descansa en lugar1',
        'objeto0 no descansa en lugar1',
        'objeto1 no descansa en lugar0',
    ]:
        second=bot.observe_schema_statement(text)
    return first,second


class V42OpenEntityAcquisitionTests(unittest.TestCase):
    def test_learned_surface_acquires_unseen_multiword_entities_with_provenance(self):
        bot=Bot(KnowledgeBase())
        first,_=train_two_binary_surfaces(bot)
        self.assertEqual(first['status'],'schema_learned')
        text='equipo alfa conecta modulo azul'
        self.assertIsNone(bot.schemas.parse(text))
        report=bot.acquire_schema_assertion(text,source='prueba')
        self.assertEqual(report['status'],'schema_fact_stored')
        self.assertEqual(report['args'],['equipo alfa','modulo azul'])
        self.assertEqual(report['novel_entities'],['equipo alfa','modulo azul'])
        self.assertEqual(bot.kb.known_entities({'equipo alfa','modulo azul'}),
                         {'equipo alfa','modulo azul'})
        fact=bot.kb.get_fact(report['id'])
        self.assertEqual(fact['atom'],Atom(report['target'],('equipo alfa','modulo azul')))
        self.assertEqual(fact['source'],f'prueba:schema_surface:{report["target"]}')
        self.assertEqual(bot.query_schema(text)['status'],'entailed')
        audit=[x for x in bot.kb.audit if x.get('event')=='schema_surface_assertion']
        self.assertEqual(len(audit),1)
        self.assertEqual(audit[0]['text'],text)
        self.assertEqual(audit[0]['novel_entities'],['equipo alfa','modulo azul'])

    def test_ambiguous_unknown_boundaries_abstain_without_storing(self):
        bot=Bot(KnowledgeBase()); train_two_binary_surfaces(bot)
        before=bot.kb.stats()['facts']
        report=bot.acquire_schema_assertion('equipo conecta modulo conecta extra')
        self.assertEqual(report['status'],'schema_surface_ambiguous')
        self.assertEqual(bot.kb.stats()['facts'],before)
        response=bot.respond('equipo conecta modulo conecta extra')
        self.assertEqual(response['status'],'schema_surface_ambiguous')
        self.assertIn('ambiguos',response['text'])

    def test_acquired_facts_become_primitives_for_a_new_composed_concept(self):
        bot=Bot(KnowledgeBase()); first,second=train_two_binary_surfaces(bot)
        left=first['learning']['target']; right=second['learning']['target']
        for i in range(12):
            r1=bot.acquire_schema_assertion(f'agente nuevo {i} conecta modulo nuevo {i}')
            r2=bot.acquire_schema_assertion(f'modulo nuevo {i} descansa en zona nueva {i}')
            self.assertEqual(r1['status'],'schema_fact_stored')
            self.assertEqual(r2['status'],'schema_fact_stored')
        examples=[
            'agente nuevo 0 coordina modulo nuevo 0 en zona nueva 0',
            'agente nuevo 1 coordina modulo nuevo 1 en zona nueva 1',
            'agente nuevo 0 no coordina modulo nuevo 0 en zona nueva 1',
            'agente nuevo 0 no coordina modulo nuevo 1 en zona nueva 0',
            'agente nuevo 1 no coordina modulo nuevo 0 en zona nueva 0',
        ]
        learned=None
        for text in examples:
            learned=bot.observe_schema_statement(text)
        self.assertEqual(learned['status'],'schema_learned')
        selected=learned['learning']['selected']
        self.assertEqual(set(selected.split(' & ')),
                         {f'{left}(r0,r1)',f'{right}(r1,r2)'})
        self.assertEqual(bot.query_schema('agente nuevo 10 coordina modulo nuevo 10 en zona nueva 10')['status'],
                         'entailed')
        self.assertEqual(bot.query_schema('agente nuevo 10 coordina modulo nuevo 10 en zona nueva 11')['status'],
                         'unknown')

    def test_negative_unknown_assertion_records_explicit_negative(self):
        bot=Bot(KnowledgeBase()); train_two_binary_surfaces(bot)
        report=bot.acquire_schema_assertion('grupo beta no conecta pieza verde')
        self.assertEqual(report['status'],'schema_fact_stored')
        self.assertFalse(report['positive'])
        self.assertTrue(report['predicate'].startswith('!'))
        self.assertEqual(bot.query_schema('grupo beta conecta pieza verde')['status'],'contradicted')

    def test_conversation_path_and_scalable_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            bot=ScalableBot(db)
            try:
                train_two_binary_surfaces(bot)
                response=bot.respond('equipo delta conecta modulo cobre')
                self.assertEqual(response['status'],'schema_fact_stored')
                self.assertEqual(response['novel_entities'],['equipo delta','modulo cobre'])
                bot.save(state)
            finally:
                bot.close()
            loaded=ScalableBot.load(state,db)
            try:
                self.assertEqual(loaded.query_schema('equipo delta conecta modulo cobre')['status'],'entailed')
                events=[x for x in loaded.kb.audit if x.get('event')=='schema_surface_assertion']
                self.assertEqual(len(events),1)
                self.assertEqual(events[0]['args'],['equipo delta','modulo cobre'])
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

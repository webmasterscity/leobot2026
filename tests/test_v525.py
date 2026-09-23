import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V525LatentDocumentEventTests(unittest.TestCase):
    GRAMMAR='''
ana frobla caja.
bruno frobla carta.
cora frobla libro.
ana tulka puerto.
bruno tulka plaza.
cora tulka parque.
uno activa alarma1.
dos activa alarma2.
tres activa alarma3.
'''
    EVENT_ROWS=[
        ('dora','paquete','norte'),
        ('eva','caja azul','sur'),
        ('luis','archivo','centro'),
    ]

    def _trained(self, bot=None, event_docs=3):
        bot=bot or Bot(allow_extensional_grounding=False)
        report=bot.ingest_document_text(self.GRAMMAR,source='event_grammar')
        self.assertEqual(report['relations_promoted'],3)
        by_surface={p['surface']:p['predicate'] for p in bot.raw_relation_promotions.values()}
        for i,(person,obj,place) in enumerate(self.EVENT_ROWS[:event_docs]):
            bot.ingest_document_text(f'{person} frobla {obj}. {person} tulka {place}.',source=f'event_train_{i}')
        return bot,by_surface

    def test_three_independent_documents_promote_schema_without_materializing_event(self):
        bot,_=self._trained()
        promoted=[s for s in bot.document_event_schema_hypotheses.values() if s.get('promoted')]
        self.assertEqual(len(promoted),1)
        self.assertEqual(promoted[0]['support'],3)
        self.assertFalse(any(f['atom'].pred.startswith('_event_') for f in bot.kb.facts.values()))
        self.assertFalse(any(x.get('event')=='document_event_materialized' for x in bot.kb.audit))

    def test_unique_structural_candidate_materializes_event_only_when_reference_needs_it(self):
        bot,by_surface=self._trained()
        report=bot.ingest_document_text(
            'marta frobla paquete rojo. marta tulka deposito. Eso activa sirena.',source='event_target')
        row=report['sentence_results'][2]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(report['document_events_materialized'],1)
        ref=row['references'][0]
        self.assertIn('latent_document_event_v525',ref['criteria'])
        event_id=ref['antecedent']
        self.assertTrue(event_id.startswith('event_'))
        self.assertTrue(bot.kb.contains(Atom(by_surface['{s0} activa {s1}'],(event_id,'sirena'))))
        self.assertTrue(any(bot.kb.contains(Atom('_event_member',(event_id,fid)))
                            for fid in row['provenance']['materialized_events'][0]['member_fact_ids']))
        self.assertTrue(bot.kb.contains(Atom('_event_role',(event_id,'r0','marta'))))
        self.assertTrue(bot.kb.contains(Atom('_event_role',(event_id,'r1','paquete rojo'))))
        self.assertTrue(bot.kb.contains(Atom('_event_role',(event_id,'r2','deposito'))))

    def test_two_equally_compatible_event_partitions_abstain_and_create_no_event(self):
        bot,by_surface=self._trained()
        before=sum(1 for f in bot.kb.facts.values() if f['atom'].pred.startswith('_event_'))
        report=bot.ingest_document_text(
            'marta frobla paquete. marta tulka deposito. '
            'zoe frobla carta. zoe tulka archivo. Eso activa sirena.',source='event_ambiguous')
        row=report['sentence_results'][4]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        self.assertEqual(len(row['candidates']),2)
        self.assertEqual(report['document_events_materialized'],0)
        after=sum(1 for f in bot.kb.facts.values() if f['atom'].pred.startswith('_event_'))
        self.assertEqual(after,before)
        for candidate in row['candidates']:
            self.assertFalse(bot.kb.contains(Atom(by_surface['{s0} activa {s1}'],(candidate,'sirena'))))

    def test_two_independent_documents_are_not_enough_to_invent_event(self):
        bot,_=self._trained(event_docs=2)
        self.assertFalse(any(s.get('promoted') for s in bot.document_event_schema_hypotheses.values()))
        report=bot.ingest_document_text(
            'marta frobla paquete. marta tulka deposito. Eso activa sirena.',source='event_undertrained')
        self.assertEqual(report['sentence_results'][2]['status'],'document_coreference_unresolved')
        self.assertEqual(report['document_events_materialized'],0)
        self.assertFalse(any(f['atom'].pred.startswith('_event_') for f in bot.kb.facts.values()))

    def test_reingesting_same_document_under_new_name_cannot_fake_event_support(self):
        bot,_=self._trained(event_docs=0)
        text='dora frobla paquete. dora tulka norte.'
        for i in range(6):
            bot.ingest_document_text(text,source=f'renamed_event_{i}')
        states=list(bot.document_event_schema_hypotheses.values())
        self.assertEqual(len(states),1)
        self.assertFalse(states[0]['promoted'])
        self.assertEqual(len(states[0]['observations']),1)

    def test_schema_and_materialized_event_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot,by_surface=self._trained(ScalableBot(db,allow_extensional_grounding=False))
            report=bot.ingest_document_text(
                'marta frobla paquete. marta tulka deposito. Eso activa sirena.',source='event_persist')
            event_id=report['sentence_results'][2]['references'][0]['antecedent']
            activa=by_surface['{s0} activa {s1}']
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(s.get('promoted') for s in loaded.document_event_schema_hypotheses.values()))
                self.assertTrue(loaded.kb.contains(Atom('_event_schema',(event_id,next(s['schema_id'] for s in loaded.document_event_schema_hypotheses.values() if s.get('promoted'))))))
                self.assertTrue(loaded.kb.contains(Atom(activa,(event_id,'sirena'))))
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

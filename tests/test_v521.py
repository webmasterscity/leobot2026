import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V521DocumentCoreferenceTests(unittest.TestCase):
    TRAIN = '''
ana frobla caja.
bea frobla libro.
cora frobla mapa.
ana norga lima.
bea norga bogota.
cora norga quito.
'''

    def _trained(self):
        bot = Bot(allow_extensional_grounding=False)
        report = bot.ingest_document_text(self.TRAIN, source='grammar_train')
        self.assertEqual(report['relations_promoted'], 2)
        frobla = next(x['predicate'] for x in bot.raw_relation_promotions.values()
                      if x.get('surface') == '{s0} frobla {s1}')
        return bot, frobla

    def test_same_role_evidence_beats_last_mention(self):
        bot, frobla = self._trained()
        report = bot.ingest_document_text(
            'Dora frobla paquete. Zoe norga ciudad. Eva frobla eso.',
            source='coref_doc')
        row = report['sentence_results'][2]
        self.assertEqual(row['status'], 'document_coreference_resolved')
        self.assertEqual(row['args'], ['eva', 'paquete'])
        self.assertEqual(row['references'][0]['antecedent'], 'paquete')
        self.assertTrue(bot.kb.contains(Atom(frobla, ('eva', 'paquete'))))
        self.assertFalse(bot.kb.contains(Atom(frobla, ('eva', 'ciudad'))))
        fact = bot.kb.get_fact(row['id'])
        self.assertIn('coref_doc:oración:3:document_coreference_v521', fact['source'])

    def test_two_same_role_antecedents_are_ambiguous_instead_of_using_recency(self):
        bot, frobla = self._trained()
        before = bot.kb.stats()['facts']
        report = bot.ingest_document_text(
            'Dora frobla paquete. Luis frobla carta. Eva frobla eso.',
            source='ambiguous_doc')
        row = report['sentence_results'][2]
        self.assertEqual(row['status'], 'document_coreference_ambiguous')
        self.assertEqual(set(row['candidates']), {'paquete', 'carta'})
        self.assertEqual(bot.kb.stats()['facts'], before + 2)
        self.assertFalse(bot.kb.contains(Atom(frobla, ('eva', 'paquete'))))
        self.assertFalse(bot.kb.contains(Atom(frobla, ('eva', 'carta'))))

    def test_unresolved_reference_does_not_seed_raw_relation_learning(self):
        bot = Bot(allow_extensional_grounding=False)
        report = bot.ingest_document_text(
            'Ana zenda eso. Bea zenda esto. Cora zenda aquello.',
            source='unsafe_doc')
        self.assertEqual(report['facts_added'], 0)
        self.assertTrue(all(r['status'] == 'document_coreference_unresolved'
                            for r in report['sentence_results']))
        self.assertEqual(bot.raw_relation_observations, [])
        self.assertEqual(bot.raw_negative_relation_observations, [])

    def test_reference_resolution_does_not_replace_conversation_focus(self):
        bot, _ = self._trained()
        for row in ['proyecto alfa ocurre lunes', 'proyecto beta ocurre martes', 'proyecto gamma ocurre miercoles']:
            bot.respond(row)
        focus = bot.respond('proyecto delta ocurre jueves')['id']
        bot.ingest_document_text('Dora frobla paquete. Eva frobla eso.', source='background_coref')
        self.assertEqual(bot.last_fact, focus)
        self.assertEqual(bot.discourse_facts[-1], focus)

    def test_resolved_fact_and_audit_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            side = Path(td) / 'state.json'
            bot = ScalableBot(db, allow_extensional_grounding=False)
            bot.ingest_document_text(self.TRAIN, source='grammar_train')
            report = bot.ingest_document_text('Dora frobla paquete. Eva frobla eso.', source='persistent_coref')
            row = report['sentence_results'][1]
            self.assertEqual(row['status'], 'document_coreference_resolved')
            pred = row['predicate']
            bot.save(side); bot.close()
            loaded = ScalableBot.load(side, db)
            try:
                self.assertTrue(loaded.kb.contains(Atom(pred, ('eva', 'paquete'))))
                events = [x for x in loaded.kb.audit if x.get('event') == 'document_coreference_resolved']
                self.assertTrue(any(x.get('resolved_args') == ['eva', 'paquete'] for x in events))
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

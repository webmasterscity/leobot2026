import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V520LexicalMetaRelationTests(unittest.TestCase):
    TRAIN = '''
a1 frobla b1.
a2 frobla b2.
a3 frobla b3.
c1 norga d1.
c2 norga d2.
c3 norga d3.
e1 kima f1.
e2 kima f2.
e3 kima f3.
'''

    TWO_FAMILIES = '''
a1 frobla b1.
a2 frobla b2.
a3 frobla b3.
c1 norga d1.
c2 norga d2.
c3 norga d3.
'''

    def test_three_independent_predicates_enable_one_shot_opaque_relation(self):
        bot = Bot(allow_extensional_grounding=False)
        train = bot.ingest_document_text(self.TRAIN, source='meta_train')
        self.assertEqual(train['relations_promoted'], 3)
        frames = bot._raw_lexical_meta_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]['template'], ['{s0}', '{rel}', '{s1}'])
        self.assertEqual(frames[0]['support'], 3)

        one = bot.ingest_document_text('x1 zenda y1.', source='one_shot')
        self.assertEqual(one['facts_added'], 1)
        row = one['sentence_results'][0]
        self.assertEqual(row['status'], 'raw_relation_meta_transferred')
        self.assertEqual(row['meta_support'], 3)
        self.assertEqual(row['relation_lexeme'], 'zenda')
        self.assertEqual(row['args'], ['x1', 'y1'])
        self.assertEqual(bot.respond('¿x1 zenda y1?')['status'], 'supported')

    def test_two_predicates_are_not_enough_to_license_one_shot_transfer(self):
        bot = Bot(allow_extensional_grounding=False)
        bot.ingest_document_text(self.TWO_FAMILIES, source='meta_control')
        self.assertEqual(bot._raw_lexical_meta_frames(), [])
        report = bot.ingest_document_text('x1 zenda y1.', source='one_shot')
        self.assertEqual(report['facts_added'], 0)
        self.assertEqual(report['sentence_results'][0]['status'], 'raw_relation_pending')
        self.assertEqual(bot.respond('¿x1 zenda y1?')['status'], 'unrecognized')

    def test_ambiguous_slot_boundaries_are_not_guessed(self):
        bot = Bot(allow_extensional_grounding=False)
        bot.ingest_document_text(self.TRAIN, source='meta_train')
        before = bot.kb.stats()['facts']
        report = bot.ingest_document_text('equipo alfa torqa modulo azul.', source='ambiguous')
        self.assertEqual(report['facts_added'], 0)
        self.assertEqual(bot.kb.stats()['facts'], before)
        self.assertNotEqual(report['sentence_results'][0]['status'], 'raw_relation_meta_transferred')

    def test_meta_transferred_predicates_do_not_self_amplify_meta_support(self):
        bot = Bot(allow_extensional_grounding=False)
        bot.ingest_document_text(self.TRAIN, source='meta_train')
        bot.ingest_document_text('x1 zenda y1.', source='one_a')
        bot.ingest_document_text('x2 torqa y2.', source='one_b')
        frames = bot._raw_lexical_meta_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]['support'], 3)
        self.assertEqual(set(frames[0]['lexemes']), {'frobla', 'norga', 'kima'})

    def test_one_shot_fact_keeps_document_provenance(self):
        bot = Bot(allow_extensional_grounding=False)
        bot.ingest_document_text(self.TRAIN, source='meta_train')
        report = bot.ingest_document_text('x1 zenda y1.', source='source_doc')
        pred = report['sentence_results'][0]['predicate']
        answer = bot.respond('¿x1 zenda y1?')
        self.assertEqual(answer['status'], 'supported')
        self.assertIn('source_doc:oración:1:meta_raw_relation:' + pred,
                      [p.get('source') for p in answer['proofs']])

    def test_meta_frame_and_transferred_relation_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            side = Path(td) / 'state.json'
            bot = ScalableBot(db, allow_extensional_grounding=False)
            bot.ingest_document_text(self.TRAIN, source='persistent_train')
            bot.save(side)
            bot.close()
            loaded = ScalableBot.load(side, db)
            try:
                self.assertEqual(loaded._raw_lexical_meta_frames()[0]['support'], 3)
                report = loaded.ingest_document_text('x1 zenda y1.', source='later_doc')
                self.assertEqual(report['sentence_results'][0]['status'], 'raw_relation_meta_transferred')
                self.assertEqual(loaded.respond('¿x1 zenda y1?')['status'], 'supported')
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

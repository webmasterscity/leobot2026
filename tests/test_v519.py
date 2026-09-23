import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V519DocumentConditionalLearningTests(unittest.TestCase):
    RULE_DOC = '''
Si ana frobla caja a luis entonces ana glorp luis.
Si bea frobla libro a mario entonces bea glorp mario.
Si cora frobla mapa a nora entonces cora glorp nora.
'''

    def test_opt_in_document_conditionals_learn_rule_without_asserting_hypothetical_facts(self):
        bot = Bot(allow_extensional_grounding=False)
        report = bot.ingest_document_text(self.RULE_DOC, source='doc_rules', learn_conditionals=True)
        self.assertEqual(report['conditionals_processed'], 3)
        self.assertEqual(report['conditionals_skipped'], 0)
        self.assertEqual(report['rules_learned'], 1)
        self.assertEqual(report['facts_added'], 0)
        self.assertEqual(bot.kb.stats()['facts'], 0)
        self.assertEqual(len(bot.kb.rules), 1)
        self.assertEqual([x['source'] for x in bot.conditional_bootstrap_observations], [
            'doc_rules:oración:1', 'doc_rules:oración:2', 'doc_rules:oración:3'])
        self.assertEqual([x['source'] for x in bot.conditional_bootstrap_promotions[0]['episodes']], [
            'doc_rules:oración:1', 'doc_rules:oración:2', 'doc_rules:oración:3'])
        self.assertIsNone(bot.last_fact)
        self.assertEqual(bot.discourse_facts, [])

    def test_rule_learned_from_document_transfers_to_new_document_fact(self):
        bot = Bot(allow_extensional_grounding=False)
        bot.ingest_document_text(self.RULE_DOC, source='doc_rules', learn_conditionals=True)
        fact_report = bot.ingest_document_text('Dora frobla carta a raul.', source='facts_doc')
        self.assertEqual(fact_report['facts_added'], 1)
        answer = bot.respond('¿Dora glorp raul?')
        self.assertEqual(answer['status'], 'hypothesis')
        self.assertEqual(answer['proofs'][0]['children'][0]['source'], 'facts_doc:oración:1')

    def test_default_document_mode_still_skips_conditionals_and_cannot_derive_head(self):
        bot = Bot(allow_extensional_grounding=False)
        report = bot.ingest_document_text(self.RULE_DOC, source='doc_control')
        self.assertEqual(report['conditionals_skipped'], 3)
        self.assertEqual(report['conditionals_processed'], 0)
        self.assertEqual(report['rules_learned'], 0)
        self.assertEqual(len(bot.kb.rules), 0)
        bot.ingest_document_text('Dora frobla carta a raul.', source='facts_control')
        self.assertNotEqual(bot.respond('¿Dora glorp raul?')['status'], 'hypothesis')

    def test_document_conditional_learning_does_not_replace_conversation_focus(self):
        bot = Bot(allow_extensional_grounding=False)
        for row in ['proyecto alfa ocurre lunes', 'proyecto beta ocurre martes', 'proyecto gamma ocurre miercoles']:
            bot.respond(row)
        focus = bot.respond('proyecto delta ocurre jueves')['id']
        bot.ingest_document_text(self.RULE_DOC, source='background_rules', learn_conditionals=True)
        self.assertEqual(bot.last_fact, focus)
        self.assertEqual(bot.discourse_facts[-1], focus)
        corrected = bot.respond('No, ocurre viernes.')
        self.assertEqual(corrected['status'], 'corrected_contextually')
        self.assertEqual(corrected['old_id'], focus)

    def test_document_conditional_grammar_rule_and_provenance_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            side = Path(td) / 'state.json'
            bot = ScalableBot(db, allow_extensional_grounding=False)
            report = bot.ingest_document_text(self.RULE_DOC, source='persistent_rules', learn_conditionals=True)
            rid = report['learned_rule_ids'][0]
            bot.save(side)
            bot.close()
            loaded = ScalableBot.load(side, db)
            try:
                self.assertIn(rid, loaded.kb.rules)
                self.assertEqual([x['source'] for x in loaded.conditional_bootstrap_observations], [
                    'persistent_rules:oración:1', 'persistent_rules:oración:2', 'persistent_rules:oración:3'])
                loaded.ingest_document_text('Dora frobla carta a raul.', source='later_doc')
                answer = loaded.respond('¿Dora glorp raul?')
                self.assertEqual(answer['status'], 'hypothesis')
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

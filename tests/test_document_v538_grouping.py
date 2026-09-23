"""Diagnostic for the unresolved V5.38 bundle/ordinary-entity distinction.

The two continuations below have the same observable fact graph. The
"accidental" label is supplied by the test author, not by the document parser.
An unconditional hypothesis-only gate prevented 100/100 accidental assertions,
but also lost 100/100 V5.38 held-out resolutions and 100/100 same-pattern true
event resolutions. Without another observation, those outcomes cannot be
separated by the current learned policy. The desired safety test remains an
expected failure until that distinction has a principled source of evidence.
"""
import copy
import unittest

import test_v538


class V538GroupingDiagnosisTests(unittest.TestCase):
    def setUp(self):
        helper = test_v538.V538CrossTypeLatentStrategyTests()
        self.base = helper._prepare(True)
        for verb, prefix in (('come', 'nuevoa'), ('cuesta', 'nuevob'),
                             ('arma', 'nuevoc'), ('mueve', 'nuevod')):
            helper._teach_binary(self.base, verb, prefix)

    def ingest(self, text, source):
        bot = copy.deepcopy(self.base)
        report = bot.ingest_document_text(text, source=source)
        return bot, report, report['sentence_results'][-1]

    def test_connected_event_and_accidental_pair_have_identical_policy_evidence(self):
        accidental = self.ingest(
            'juan come pan. pan cuesta euro. Eso activa alarma.', 'accidental')
        event = self.ingest(
            'mara arma motor. motor mueve rueda. Eso activa timbre.', 'event')
        features = []
        for bot, report, row in (accidental, event):
            facts = [bot.kb.get_fact(result['id'])
                     for result in report['sentence_results'][:2]]
            self.assertEqual(facts[0]['atom'].args[1], facts[1]['atom'].args[0])
            candidates = bot._document_latent_bundle_candidates(facts, row['predicate'], 0)
            self.assertEqual(len(candidates), 1)
            features.append(candidates[0]['features'])
        self.assertEqual(features[0], features[1])
        self.assertEqual(features[0], {
            'fact_count': 2, 'connected': True, 'shared_role_count': 1,
            'all_positive': True, 'predicate_count': 2})

    def test_no_shared_entity_does_not_propose_a_bundle(self):
        _, report, row = self.ingest(
            'juan come pan. tienda cuesta euro. Eso activa alarma.', 'disconnected')
        self.assertEqual(row['status'], 'document_coreference_unresolved')
        self.assertEqual(report['document_latent_bundles_materialized'], 0)

    @unittest.expectedFailure
    def test_accidental_pair_requires_evidence_before_asserting_bundle_fact(self):
        bot, report, row = self.ingest(
            'juan come pan. pan cuesta euro. Eso activa alarma.', 'unsafe_pair')
        self.assertEqual(row['status'], 'document_coreference_unresolved')
        self.assertEqual(row['reason'], 'latent_bundle_unconfirmed')
        self.assertEqual(len(row['hypotheses']), 1)
        self.assertEqual(report['document_latent_bundles_materialized'], 0)
        self.assertFalse(any(
            fact['atom'].pred == row['predicate'] and
            fact['atom'].args[-1] == 'alarma'
            for fact in bot.kb.facts.values()))


if __name__ == '__main__':
    unittest.main()

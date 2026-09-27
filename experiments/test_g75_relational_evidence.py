"""Opaque examples check binding and resource semantics, not kiosk quality."""
import importlib.util
import unittest
from unittest.mock import patch


class RelationalEvidenceContract(unittest.TestCase):
    def module(self):
        name = 'experiments.g75_relational_evidence'
        self.assertIsNotNone(importlib.util.find_spec(name), 'Falta el aprendiz relacional')
        from experiments import g75_relational_evidence
        return g75_relational_evidence

    @staticmethod
    def view(words):
        return {'terms': words, 'nodes': {
            '1': {'head': '2', 'deprel': 'x'},
            '2': {'head': '0', 'deprel': 'z'},
            '3': {'head': '2', 'deprel': 'y'},
        }}

    def test_learns_participant_assignment_with_identical_word_sets(self):
        m = self.module()
        vocab = {'p': {'f': {}}, 'r': {'f': {}}}
        q = self.view(['u', 'p', 'v'])
        own, _ = m.pair_features(q, self.view(['u', 'r', 'v']), vocab)
        other, _ = m.pair_features(q, self.view(['v', 'r', 'u']), vocab)
        model = m.learn_weights([(str(i), own, other) for i in range(5)])
        self.assertGreater(m.feature_score(model, own), m.feature_score(model, other))
        self.assertEqual(m.feature_score(model, own, lexical=True),
                         m.feature_score(model, other, lexical=True))

    def test_exhaustion_returns_no_partial_relational_features(self):
        m = self.module()
        vocab = {str(i): {'f': {}} for i in range(20)}
        features, stats = m.pair_features(
            {'terms': [str(i) for i in range(9)], 'nodes': {}},
            {'terms': [str(i) for i in range(9, 18)], 'nodes': {}}, vocab)
        self.assertTrue(stats['exhausted'])
        self.assertEqual(features, set())

    def test_missing_semantic_signal_keeps_the_public_answer_unchanged(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        bot.load_context('X: u. Y: v.', '')
        before = bot.answer('X', [])
        old_rank, old_load = bot._rank, bot.load_context
        ranker = m.RelationalRanker(bot, {}, {}, weight=1.)
        bot.load_context('X: u. Y: v.', '')
        self.assertEqual(before, bot.answer('X', []))
        ranker.restore()
        self.assertEqual(bot._rank, old_rank)
        self.assertEqual(bot.load_context, old_load)

    def test_training_reuse_equals_separate_runs_across_documents_and_models(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        mapping = {'p': {'f': {'v': {'0'}}}, 'r': {'f': {'v': {'0'}}}}
        weights, shuffled = {m.key('R', 'f'): 1.}, {m.key('R', 'f'): -1.}
        turns = [[{'cliente': 'u p v?', 'claves': ['u'], 'tipo': 'directa'},
                  {'cliente': 'v p u?', 'accion': 'abstenerse'}]]
        data = [('a', 'u r v.\nv r u.', '', turns),
                ('b', 'v r u.\nu r v.', '', turns)]
        contexts = [('congelado/'+name, text, instructions, conv)
                    for name, text, instructions, conv in data]
        shared, _ = m.collect_variants(bot, mapping, weights, shuffled, contexts)
        self.assertTrue(shared[('full', .25)])
        self.assertTrue(any(m.RAW[0] in row['f'] for row in shared[('full', .25)]))
        for (mode, weight), actual in shared.items():
            ranker = m.RelationalRanker(bot, mapping, shuffled if mode == 'shuffled' else weights,
                                       mode='lexical' if mode == 'lexical' else 'full', weight=weight)
            try:
                with patch('experiments.g68_confianza.businesses', return_value=data):
                    expected = m.collect(bot, ('congelado',))
            finally:
                ranker.restore()
            self.assertEqual(actual, expected, (mode, weight))


if __name__ == '__main__':
    unittest.main()

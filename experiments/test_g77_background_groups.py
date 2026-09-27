import importlib.util
import json
import unittest
from unittest.mock import patch


class BackgroundGroupsContract(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('experiments.g77_background_groups'))
        from experiments import g77_background_groups
        return g77_background_groups

    def test_learns_alignment_and_domain_names_do_not_matter(self):
        m = self.module()
        rows = [([0], [1]), ([1], [0])]*30
        domains = ['x']*30+['y']*30
        bg = m.backgrounds(rows, domains, 2, 2)
        model, _ = m.train(rows, domains, bg, seed=13, groups=2)
        renamed = ['other' if d == 'x' else 'another' for d in domains]
        other, _ = m.train(rows, renamed, m.backgrounds(rows, renamed, 2, 2), seed=13, groups=2)
        self.assertEqual(model, other)
        q = m.project(model, [0], 'qlog', bg[0])
        own = m.project(model, [1], 'alog', bg[1])
        rival = m.project(model, [0], 'alog', bg[1])
        self.assertGreater(sum(x*y/p for x, y, p in zip(q, own, model['prior'])),
                           sum(x*y/p for x, y, p in zip(q, rival, model['prior'])))
        self.assertEqual(model, json.loads(json.dumps(model)))
        self.assertEqual(set(model), {'prior', 'qlog', 'alog', 'rho'})

    def test_document_replacement_recounts_background_and_keeps_evidence_local(self):
        m = self.module()
        from leobot import Bot
        rows = [([0], [1]), ([1], [0])]*30
        domains = ['x']*30+['y']*30
        bg = m.backgrounds(rows, domains, 2, 2)
        model, _ = m.train(rows, domains, bg, seed=13, groups=2)
        bundle = {'qv': {'u': 0, 'v': 1}, 'av': {'m': 0, 'n': 1}, 'models': [model],
                  'qbackground': bg[0], 'abackground': bg[1], 'local_background': True}
        bot = Bot()
        bot.calibrated, bot.closest = False, False
        ranker = m.BackgroundRanker(bot, bundle)
        try:
            bot.load_context('m: 11.\nn: 22.', '')
            before = list(ranker.document_background)
            self.assertIn('22', bot.answer('u?')['text'])
            bot.load_context('n: 44.\nm: 33.\nm: 55.', '')
            self.assertNotEqual(before, ranker.document_background)
            self.assertIn('44', bot.answer('u?')['text'])
        finally:
            ranker.restore()

    def test_prepared_documents_give_same_training_rows_as_separate_runs(self):
        m = self.module()
        from leobot import Bot
        rows = [([0], [1]), ([1], [0])]*30
        domains = ['x']*30+['y']*30
        bg = m.backgrounds(rows, domains, 2, 2)
        model, _ = m.train(rows, domains, bg, seed=13, groups=2)
        bundle = {'qv': {'u': 0, 'v': 1}, 'av': {'m': 0, 'n': 1}, 'models': [model],
                  'qbackground': bg[0], 'abackground': bg[1], 'local_background': True}
        turns = [[{'cliente': 'u?', 'claves': ['22'], 'tipo': 'directa'},
                  {'cliente': 'v?', 'accion': 'abstenerse'}]]
        data = [('a', 'm: 11.\nn: 22.', '', turns), ('b', 'n: 44.\nm: 33.', '', turns)]
        bot = Bot()
        ranker = m.BackgroundRanker(bot, bundle)
        try:
            shared = m.g76.collect_weights(bot, ranker,
                contexts=[('congelado/'+name, text, ins, conv) for name, text, ins, conv in data])
            self.assertTrue(shared[.25])
            for weight, actual in shared.items():
                ranker.weight = weight
                with patch('experiments.g68_confianza.businesses', return_value=data):
                    expected = m.g76.collect(bot, ('congelado',))
                self.assertEqual(actual, expected)
        finally:
            ranker.restore()


if __name__ == '__main__':
    unittest.main()

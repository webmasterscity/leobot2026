"""Small opaque cases check the learner, never business answers."""
import importlib.util
import json
import unittest


class PairedGroupsContract(unittest.TestCase):
    def module(self):
        name = 'experiments.g76_paired_groups'
        self.assertIsNotNone(importlib.util.find_spec(name), 'Falta el aprendiz G76')
        from experiments import g76_paired_groups
        return g76_paired_groups

    def test_learning_recovers_alignment_without_retaining_examples(self):
        m = self.module()
        rows = [([0], [1])]*30 + [([1], [0])]*30
        model, _ = m.train(rows, 2, 2, seed=13, groups=2)
        self.assertGreater(m.match(model, [0], [1]), m.match(model, [0], [0]))
        self.assertEqual(set(model), {'prior', 'qlog', 'alog'})

    def test_full_question_disambiguates_and_unknown_words_are_neutral(self):
        m = self.module()
        rows = [([0, 1], [0])]*30 + [([0, 2], [1])]*30
        model, _ = m.train(rows, 3, 2, seed=13, groups=2)
        self.assertGreater(m.match(model, [0, 1], [0]), m.match(model, [0, 1], [1]))
        self.assertGreater(m.match(model, [0, 2], [1]), m.match(model, [0, 2], [0]))
        self.assertAlmostEqual(m.match(model, [], [0]), 0.)

    def test_reload_and_vocabulary_permutation_preserve_scores(self):
        m = self.module()
        rows = [([0], [1])]*30 + [([1], [0])]*30
        model, _ = m.train(rows, 2, 2, seed=13, groups=2)
        saved = json.loads(json.dumps(model))
        self.assertEqual(m.match(model, [0], [1]), m.match(saved, [0], [1]))
        saved['qlog'].reverse()
        saved['alog'].reverse()
        self.assertEqual(m.match(model, [0], [1]), m.match(saved, [1], [0]))

    def test_public_answer_uses_only_the_current_document_and_zero_is_exact(self):
        m = self.module()
        from leobot import Bot
        model, _ = m.train([([0], [1])]*30 + [([1], [0])]*30, 2, 2, seed=13, groups=2)
        bundle = {'qv': {'u': 0, 'v': 1}, 'av': {'m': 0, 'n': 1}, 'models': [model]}
        bot = Bot()
        bot.calibrated, bot.closest = False, False
        ranker = m.TopicRanker(bot, bundle)
        try:
            bot.load_context('m: 11.\nn: 22.', '')
            self.assertIn('22', bot.answer('u?')['text'])
            bot.load_context('n: 44.\nm: 33.', '')
            self.assertIn('44', bot.answer('u?')['text'])
        finally:
            ranker.restore()
        expected = bot.answer('u?')
        ranker = m.TopicRanker(bot, bundle, weight=0.)
        try:
            bot.load_context('n: 44.\nm: 33.', '')
            self.assertEqual(expected, bot.answer('u?'))
        finally:
            ranker.restore()


if __name__ == '__main__':
    unittest.main()

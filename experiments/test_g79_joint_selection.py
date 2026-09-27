import importlib.util
import unittest


class JointSelectionContract(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('experiments.g79_joint_selection'))
        from experiments import g79_joint_selection
        return g79_joint_selection

    def test_reference_without_selection_preserves_answer_and_restores_instance(self):
        m = self.module()
        from leobot import Bot
        components = m.Components()
        bot = Bot()
        bot.load_context('u: 11.\nv: 22.', '')
        expected = bot.answer('u v?')
        original = bot._rank
        binding = components.bind(bot)
        self.assertEqual(expected, bot.answer('u v?'))
        binding.restore()
        self.assertEqual(original, bot._rank)
        self.assertFalse(hasattr(bot, 'selection_candidates'))

    def test_selector_changes_with_feedback_without_lexical_features(self):
        m = self.module()
        ns = m.Components().learner
        rows = [{'half': i % 2, 'rows': [({'x': '0'}, 0), ({'x': '1'}, 1)]} for i in range(40)]
        model = ns['fit'](rows, ['x'])
        self.assertGreater(ns['score'](model, {'x': '1'}, ['x']), ns['score'](model, {'x': '0'}, ['x']))
        reverse = [{'half': t['half'], 'rows': [(f, 1-y) for f, y in t['rows']]} for t in rows]
        model = ns['fit'](reverse, ['x'])
        self.assertLess(ns['score'](model, {'x': '1'}, ['x']), ns['score'](model, {'x': '0'}, ['x']))

    def test_equal_scores_get_one_empirical_rate(self):
        m = self.module()
        components = m.Components()
        components.correct_calibration()
        table = components.learner['g60'].isotonic([(0., 0)]*30+[(0., 1)]*30)
        self.assertEqual(table, [[0., .5, 60]])


if __name__ == '__main__':
    unittest.main()

import importlib
import math
import unittest


class ProjectedAlignmentTests(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g96_projected_alignment')

    def test_rank_one_reconstruction_and_orthogonality(self):
        m = self.module()
        columns = [[(0, 2.), (1, 4.), (2, 6.)], [(0, 1.), (1, 2.), (2, 3.)], []]
        model, report = m.project(columns, 3, rank=3)
        self.assertEqual(report['rank'], 1)
        self.assertLess(report['relative_residual'], 1e-9)
        for a, column in enumerate(columns):
            for q in range(3):
                actual = m.dot(model['q'][q], model['a'][a])
                self.assertAlmostEqual(actual, dict(column).get(q, 0.), places=9)
        orthogonal = m.orthonormalize([[1., 2., 0.], [0., 0., 1.], [1., 2., 1.]])
        cols = list(zip(*orthogonal))
        self.assertEqual(len(cols), 2)
        for i, left in enumerate(cols):
            for j, right in enumerate(cols):
                self.assertAlmostEqual(m.dot(left, right), float(i == j), places=10)

    def test_dominant_direction_zero_and_mean_projection(self):
        m = self.module()
        model, report = m.project([[(0, 1000.)], [(1, 10.)], [(2, 1.)]], 3, rank=1)
        self.assertEqual(report['rank'], 1)
        self.assertAlmostEqual(m.dot(model['q'][0], model['a'][0]), 1000., places=6)
        self.assertLess(abs(m.dot(model['q'][1], model['a'][1])), 1e-6)
        for columns, size in (([], 0), ([[], []], 3), ([[(0, 0.)]], 2)):
            empty, summary = m.project(columns, size, rank=2)
            self.assertEqual(summary['rank'], 0)
            self.assertEqual(len(empty['q']), size)
            self.assertTrue(all(not row for row in empty['a']))
        q, a = [0, 2], [0, 1]
        expected = sum(m.dot(model['q'][i], model['a'][j]) for i in q for j in a)/4
        self.assertAlmostEqual(m.dot(m.mean_rows(model['q'], q), m.mean_rows(model['a'], a)), expected)
        self.assertEqual(m.mean_rows(model['q'], []), [0.])
        self.assertTrue(math.isfinite(report['relative_residual']))

    def test_document_replacement_and_removal(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        reference = m.Components().bind(bot)
        one = [[[0, 1.]], [[1, 1.]]]
        bot.context_model['alignment'] = {'questions': ['u', 'v'], 'answers': ['a', 'b'],
                                         'background': [.1, .1], 'one': one, 'two': one}
        alignment = m.DirectBinding(bot)
        bot.load_context('a.', '')
        original = bot.selection_candidates('u?', 6)
        binding = m.ProjectionBinding(bot, alignment)
        self.assertEqual(original, bot.selection_candidates('u?', 6))
        bot.context_model['projection'] = {'mode': 'full'}
        first = bot.selection_candidates('u?', 6)[0][1]
        bot.load_context('b.', '')
        second = bot.selection_candidates('u?', 6)[0][1]
        self.assertGreater(int(first['projection_score']), int(second['projection_score']))
        model, _ = m.project([[(0, math.log(10))], [(1, math.log(10))]], 2, rank=2)
        bot.context_model['projection'] = {'mode': 'learned', **model}
        self.assertEqual(second, bot.selection_candidates('u?', 6)[0][1])
        bot.load_context('a.', '')
        self.assertEqual(first, bot.selection_candidates('u?', 6)[0][1])
        bot.context_model.pop('projection')
        self.assertEqual(original, bot.selection_candidates('u?', 6))
        binding.restore()
        alignment.restore()
        reference.restore()


if __name__ == '__main__':
    unittest.main()

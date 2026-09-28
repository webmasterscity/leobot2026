import importlib
import itertools
import random
import unittest


class CompetingAlignmentTests(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g95_competing_alignments')

    def test_assignment_is_not_greedy_and_can_leave_words_unmatched(self):
        m = self.module()
        self.assertEqual(m.maximum_assignment([[8., 7.], [7., 0.]]), 14.)
        self.assertEqual(m.maximum_assignment([[8.], [8.]]), 8.)
        for matrix in ([], [[]], [[0., 0.]], [[-1., -2.]]):
            self.assertEqual(m.maximum_assignment(matrix), 0.)

    def test_matches_exhaustive_search_and_permuted_nodes(self):
        m = self.module()
        rng = random.Random(95)
        for n, width in itertools.product(range(1, 4), repeat=2):
            for _ in range(10):
                matrix = [[rng.randrange(8)/7 for _ in range(width)] for _ in range(n)]
                best = max(sum(matrix[i][j] for i, j in enumerate(choice) if j >= 0)
                           for choice in itertools.product(range(-1, width), repeat=n)
                           if len([j for j in choice if j >= 0]) == len({j for j in choice if j >= 0}))
                self.assertAlmostEqual(m.maximum_assignment(matrix), best)
                rng.shuffle(matrix)
                permutation = list(range(width)); rng.shuffle(permutation)
                self.assertAlmostEqual(m.maximum_assignment([[row[j] for j in permutation] for row in matrix]), best)

    def test_document_replacement_and_feature_removal(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        reference = m.Components().bind(bot)
        one = [[[0, .5], [1, .5]], []]
        bot.context_model['alignment'] = {'questions': ['u', 'v'], 'answers': ['a', 'b'],
                                          'background': [.1, .1], 'one': one, 'two': one}
        alignment = m.DirectBinding(bot)
        bot.load_context('a.', '')
        original = bot.selection_candidates('u v?', 6)
        binding = m.CompetitionBinding(bot, alignment)
        self.assertEqual(original, bot.selection_candidates('u v?', 6))
        bot.context_model['competition'] = {'mode': 'assignment', 'seed': 1}
        first = bot.selection_candidates('u v?', 6)[0][1]
        self.assertGreater(int(first['assignment_loss']), 0)
        bot.load_context('b.', '')
        second = bot.selection_candidates('u v?', 6)[0][1]
        self.assertEqual(second['assignment_loss'], '0')
        bot.context_model.pop('competition')
        self.assertNotIn('assignment_loss', bot.selection_candidates('u v?', 6)[0][1])
        binding.restore(); alignment.restore(); reference.restore()


if __name__ == '__main__':
    unittest.main()

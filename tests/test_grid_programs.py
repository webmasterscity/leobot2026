"""G-39: grid transformations learned as integer programs with index access."""
import unittest

from leobot.programs import ProgramLearner

MIRROR = [([[1, 2, 3], [4, 5, 6]], [[3, 2, 1], [6, 5, 4]]),
          ([[7, 0], [8, 9], [1, 1]], [[0, 7], [9, 8], [1, 1]]),
          ([[2, 3, 4, 5], [6, 7, 8, 9]], [[5, 4, 3, 2], [9, 8, 7, 6]])]


class GridProgramTests(unittest.TestCase):
    def learner(self, pairs, tests):
        pl = ProgramLearner(max_seconds=6.0)
        for a, b in pairs:
            pl.add_grid_example('t', a, b)
        return pl, pl.fit_grid('t', tests)

    def test_mirror_is_learned_and_survives_restart(self):
        pl, rep = self.learner(MIRROR, [[[1, 2, 3, 4, 5]]])
        self.assertEqual(rep['status'], 'learned_hypothesis')
        self.assertEqual(pl.predict_grid('t', [[1, 2, 3, 4, 5]])['grid'], [[5, 4, 3, 2, 1]])
        again = ProgramLearner.from_dict(pl.as_dict())
        self.assertEqual(again.predict_grid('t', [[1, 2, 3, 4, 5]])['grid'], [[5, 4, 3, 2, 1]])

    def test_ambiguous_evidence_abstains_instead_of_guessing(self):
        pl, _ = self.learner(MIRROR[:2], [[[1, 2, 3, 4]]])
        self.assertEqual(pl.predict_grid('t', [[1, 2, 3, 4]])['status'], 'ambiguous')

    def test_without_index_access_the_mirror_is_not_learned(self):
        pl = ProgramLearner(max_seconds=3.0)
        for a, b in MIRROR:
            pl.add_grid_example('t', a, b)
        self.assertNotEqual(pl.fit_grid('t', [[[1, 2, 3]]], use_context=False)['status'], 'learned_hypothesis')

    def test_renaming_colours_renames_the_answer(self):
        # G-39c: colours are symbols; a consistent renaming gives the renamed answer.
        perm = [0, 7, 3, 9, 2, 8, 1, 5, 4, 6]
        rename = lambda g: [[perm[v] for v in row] for row in g]
        pl, _ = self.learner(MIRROR, [[[1, 2, 3, 4, 5]]])
        qr, _ = self.learner([(rename(a), rename(b)) for a, b in MIRROR], [rename([[1, 2, 3, 4, 5]])])
        self.assertEqual(qr.predict_grid('t', rename([[1, 2, 3, 4, 5]]))['grid'],
                         rename(pl.predict_grid('t', [[1, 2, 3, 4, 5]])['grid']))

    def test_colours_are_not_numbers(self):
        # A colour computed by arithmetic (here: colour = 2 - colour) is not learnable.
        pairs = [([[1, 2]], [[1, 0]]), ([[2, 0]], [[0, 2]]), ([[0, 1]], [[2, 1]])]
        pl, rep = self.learner(pairs, [[[1, 1]]])
        self.assertNotEqual(pl.predict_grid('t', [[1, 1]])['status'], 'hypothesis')

    def test_truncated_search_abstains(self):
        # G-39d (audit case, seed 9): with 1500 candidates a crop is answered from
        # a partial minimal set; the complete search finds disagreeing programs.
        import random
        rng = random.Random(9)
        colours = rng.sample(range(1, 10), 2)
        grid = lambda h, w: [[rng.choice(colours) for _ in range(w)] for _ in range(h)]
        pairs = []
        for _ in range(2):
            a = grid(rng.randrange(3, 6), rng.randrange(3, 6))
            pairs.append((a, [row[1:] for row in a[1:]]))
        test = grid(rng.randrange(3, 6), rng.randrange(3, 6))
        for cap, expected in ((1500, 'incomplete'), (120_000, 'ambiguous')):
            pl = ProgramLearner(max_seconds=600.0, max_candidates=cap)
            for a, b in pairs:
                pl.add_grid_example('t', a, b)
            pl.fit_grid('t', [test])
            self.assertEqual(pl.predict_grid('t', test)['status'], expected)

    def test_fresh_learner_does_not_answer_and_rejects_bad_grids(self):
        pl = ProgramLearner()
        self.assertEqual(pl.predict_grid('t', [[1]])['status'], 'unknown')
        with self.assertRaises(ValueError):
            pl.add_grid_example('t', [[1, 2], [3]], [[1]])
        with self.assertRaises(ValueError):
            pl.add_grid_example('t', [[10]], [[1]])


if __name__ == '__main__':
    unittest.main()

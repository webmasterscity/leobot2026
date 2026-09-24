"""G-40: objects as whole-grid views composed with the cell learner."""
import json
import unittest

from leobot.programs import ProgramLearner, grid_view


def scene(big, small):
    """A 6x6 grid with a large object of colour ``big`` and a small one of ``small``."""
    g = [[0] * 6 for _ in range(6)]
    for r in range(3):
        for c in range(3):
            g[r][c] = big
    g[4][4] = small
    return g


class GridViewTests(unittest.TestCase):
    def test_largest_object_crop_is_learned_and_survives_restart(self):
        pl = ProgramLearner()
        for big, small in ((1, 2), (3, 4), (5, 6)):
            pl.add_grid_example('t', scene(big, small), [[big] * 3 for _ in range(3)])
        test = scene(7, 8)
        rep = pl.fit_grid_views('t', [test], seconds_per_view=2.0)
        self.assertIn('color:mayor', rep['views'])
        pred = pl.predict_grid_views('t', test)
        self.assertEqual((pred['status'], pred['grid']), ('hypothesis', [[7] * 3 for _ in range(3)]))
        again = ProgramLearner.from_dict(json.loads(json.dumps(pl.as_dict())))
        self.assertEqual(again.predict_grid_views('t', test), pred)

    def test_views_do_not_exist_when_the_choice_is_not_unique(self):
        g = [[1, 0, 2]]
        self.assertIsNone(grid_view(g, 'color:mayor'))
        self.assertEqual(grid_view(g, 'dibujo'), ((1, 0, 2),))

    def test_fresh_learner_does_not_answer(self):
        self.assertEqual(ProgramLearner().predict_grid_views('t', [[1]])['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()

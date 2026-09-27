import unittest

from experiments.g87_proposal_coverage import proposed


class PoolTests(unittest.TestCase):
    def test_union_preserves_initials_and_uses_only_eligible_additions(self):
        units = [{'kind': 'line'}, {'kind': 'heading'}, {'kind': 'question'},
                 {'kind': 'line'}, {'kind': 'line'}]
        result = proposed([1, 0], [2., 9., 10., 3., 3.], units)
        self.assertEqual(result, [1, 0, 3, 4])
        self.assertEqual(len(result), len(set(result)))
        self.assertEqual(proposed([], [], []), [])


if __name__ == '__main__':
    unittest.main()

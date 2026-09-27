"""Controles del experimento, no evidencia de comprensión del lenguaje."""
import importlib.util
import inspect
import unittest


class JointConstructionContract(unittest.TestCase):
    def learner(self):
        name = 'experiments.g71_joint_constructions'
        self.assertIsNotNone(importlib.util.find_spec(name),
                             'Falta el aprendiz de construcciones conjuntas')
        from experiments.g71_joint_constructions import JointConstructions
        return JointConstructions

    def test_does_not_combine_slots_from_incompatible_observed_frames(self):
        # An independent decision or a union of partial matches would fail.
        learner = self.learner()
        model = learner.learn([
            [('u', 'a'), ('v', 'b')],
            [('u', 'b'), ('w', 'c')],
        ])
        answer, stats = model.predict(
            ['u', 'v', 'w'],
            [{'a': 5, 'b': 6}, {'b': 4}, {'c': 5}],
        )
        self.assertEqual(answer, ('b', 'NONE', 'c'))
        self.assertFalse(stats['exhausted'])
        incomplete, _ = model.predict(['v'], [{'b': 4}])
        self.assertEqual(incomplete, ('NONE',))

    def test_exhaustion_discards_the_best_partial_search_result(self):
        # Returning the best-so-far candidate after the cap would fail.
        learner = self.learner()
        model = learner.learn([[('u', 'a')]])
        answer, stats = model.predict(
            ['u', 'u'], [{'a': 2}, {'a': 3}], limit=1,
        )
        self.assertTrue(stats['exhausted'])
        self.assertEqual(answer, ('NONE', 'NONE'))

    def test_compatibility_filter_cannot_select_a_disallowed_construction(self):
        # Ignoring a learned compatibility restriction would return b/NONE/c.
        learner = self.learner()
        self.assertIn('allowed', inspect.signature(learner.predict).parameters)
        model = learner.learn([[('u', 'a'), ('v', 'b')],
                               [('u', 'b'), ('w', 'c')]])
        keys = ['u', 'v', 'w']
        margins = [{'a': 5, 'b': 6}, {'b': 4}, {'c': 5}]
        answer, _ = model.predict(keys, margins, allowed={0})
        self.assertEqual(answer, ('a', 'b', 'NONE'))
        answer, _ = model.predict(keys, margins, allowed=set())
        self.assertEqual(answer, ('NONE', 'NONE', 'NONE'))


if __name__ == '__main__':
    unittest.main()

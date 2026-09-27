import math
import unittest

from experiments.g89_semantic_categories import learn
from experiments.g90_observed_transitions import support, ConstrainedTagger


class TransitionTests(unittest.TestCase):
    def test_support_comes_only_from_observed_pairs(self):
        model = {'bigrams': {'a\x1fb': 1, 'b\x1fc': 0}}
        self.assertEqual(support(model), {('a', 'b')})
        tagger = learn([(['foo', 'bar'], ['state-x', 'state-y'])]*4)
        constrained = ConstrainedTagger(tagger.syntax_model, support(tagger.syntax_model))
        self.assertEqual(constrained._transition('ignored', 'state-y', 'state-x'), -math.inf)
        self.assertEqual(constrained.tag_words(['foo', 'bar']), ['state-x', 'state-y'])

    def test_no_path_falls_back_and_disable_is_exact(self):
        tagger = learn([(['foo', 'bar'], ['opaque-1', 'opaque-2'])]*4)
        constrained = ConstrainedTagger(tagger.syntax_model, set())
        expected = tagger.tag_words(['foo', 'bar'])
        self.assertEqual(constrained.tag_words(['foo', 'bar']), expected)
        self.assertEqual(constrained.fallbacks, 1)
        constrained.allowed = None
        self.assertEqual(constrained.tag_words(['foo', 'bar']), expected)
        self.assertEqual(constrained.fallbacks, 1)


if __name__ == '__main__':
    unittest.main()

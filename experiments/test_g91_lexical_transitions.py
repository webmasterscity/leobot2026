import unittest

from experiments.g89_semantic_categories import learn
from experiments.g91_lexical_transitions import count_contexts, LexicalTagger


class LexicalTransitionTests(unittest.TestCase):
    def test_neighbor_is_learned_and_calls_do_not_leak(self):
        rows = [(['one', 'same'], ['a', 'x']), (['two', 'same'], ['a', 'y'])]*10
        base = learn(rows)
        contexts = count_contexts(rows)
        tagger = LexicalTagger(base.syntax_model, contexts, 'lexical')
        self.assertEqual(tagger.tag_words(['one', 'same']), ['a', 'x'])
        self.assertEqual(tagger.tag_words(['two', 'same']), ['a', 'y'])
        self.assertEqual(tagger.tag_words(['one', 'same']), ['a', 'x'])
        self.assertIsNone(tagger.active_words)
        tagger.mode = 'disabled'
        self.assertEqual(tagger.tag_words(['one', 'same']), base.tag_words(['one', 'same']))

    def test_sequence_boundaries_and_opaque_classes(self):
        rows = [(['v'], ['opaque'])]*3
        contexts = count_contexts(rows)
        self.assertEqual(contexts['<s>']['<s>'], {'opaque': 3})
        self.assertEqual(contexts['opaque']['v'], {'</s>': 3})
        base = learn(rows)
        tagger = LexicalTagger(base.syntax_model, contexts, 'lexical')
        self.assertEqual(tagger.tag_words(['v']), ['opaque'])
        self.assertIsNone(tagger.active_words)


if __name__ == '__main__':
    unittest.main()

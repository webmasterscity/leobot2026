import unittest

from leobot.syntax import SyntaxMixin, _empty_syntax
from experiments.g89_semantic_categories import observe_tags, spans, new_tagger


class CategoryTests(unittest.TestCase):
    def test_counting_matches_existing_learner(self):
        original = SyntaxMixin()
        original.syntax_model = _empty_syntax()
        adapted = new_tagger()
        for words, tags in ((['Foo', 'x'], ['B-X', 'O']), (['Bar', 'y'], ['B-Y', 'O'])):
            original.observe_parsed_sentence(words, tags, [0, 1])
            observe_tags(adapted, words, tags)
        for field in ('sentences', 'compiled', 'tags', 'bigrams', 'trigrams', 'lexicon', 'word_counts'):
            self.assertEqual(original.syntax_model[field], adapted.syntax_model[field])
        self.assertEqual(adapted.syntax_model['arcs'], {})

    def test_span_scoring_and_unknown_class_symbols(self):
        self.assertEqual(spans(['B-X', 'I-X', 'O', 'I-Y', 'B-Y']),
                         {(0, 2, 'X'), (3, 4, 'Y'), (4, 5, 'Y')})
        self.assertEqual(spans(['O', 'O']), set())
        first, second = new_tagger(), new_tagger()
        for _ in range(4):
            observe_tags(first, ['Foo', 'bar'], ['B-X', 'O'])
            observe_tags(second, ['Foo', 'bar'], ['B-Q', 'O'])
        first.consolidate_syntax()
        second.consolidate_syntax()
        self.assertEqual(first.tag_words(['Foo', 'bar']), ['B-X', 'O'])
        self.assertEqual(second.tag_words(['Foo', 'bar']), ['B-Q', 'O'])


if __name__ == '__main__':
    unittest.main()

"""G-52: the gap in the predicate, learned negative concord and plural omitted subjects."""
import unittest

from leobot import Bot
from tests.test_g51_entities import taught

P, D, N, V, A, X, AUX, ADJ, ADV = 'PROPN', 'DET', 'NOUN', 'VERB', 'ADP', 'PUNCT', 'AUX', 'ADJ', 'ADV'


def concord_bot(times_after=5, times_before=10):
    """Demonstrations where «nunca» goes with «no» after the verb and alone before it."""
    bot = Bot()
    after = (['No', 'sale', 'nunca', '.'], [ADV, V, ADV, X], [2, 0, 2, 2], ['advmod', 'root', 'advmod', 'punct'],
             ['Polarity=Neg', 'Number=Sing|Person=3', '_', '_'])
    before = (['Nunca', 'sale', '.'], [ADV, V, X], [2, 0, 2], ['advmod', 'root', 'punct'],
              ['_', 'Number=Sing|Person=3', '_'])
    also = (['Siempre', 'sale', '.'], [ADV, V, X], [2, 0, 2], ['advmod', 'root', 'punct'],
            ['_', 'Number=Sing|Person=3', '_'])
    for words, tags, heads, labels, feats in [after] * times_after + [before] * times_before + [also] * 10:
        bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats)
    bot.consolidate_syntax()
    return bot


class ConcordTests(unittest.TestCase):
    def test_negative_concord_is_learned_from_marked_negators(self):
        bot = concord_bot()
        self.assertEqual(bot.syntax_model['negators'], ['no'])
        self.assertEqual(bot.syntax_model['concord_negators'], ['nunca'])
        self.assertIn('nunca', bot.negator_words())
        self.assertEqual(bot.negated(2), 1)            # «no … nunca» is still negative
        bot.negative_concord = False
        self.assertNotIn('nunca', bot.negator_words())
        self.assertEqual(bot.negated(2), 0)            # G-41 parity

    def test_not_enough_evidence_learns_nothing(self):
        self.assertEqual(concord_bot(times_after=4).syntax_model['concord_negators'], [])
        self.assertEqual(concord_bot(times_before=9).syntax_model['concord_negators'], [])


class PredicateTests(unittest.TestCase):
    def test_the_predicate_of_a_placed_subject_is_offered(self):
        tree = (['El', 'coche', 'de', 'Elena', 'es', 'azul', '.'], [D, N, A, P, AUX, ADJ, X],
                [2, 6, 4, 2, 6, 0, 6], ['det', 'nsubj', 'case', 'nmod', 'cop', 'root', 'punct'])
        words, tags, heads, labels = tree
        children = [[k for k in range(len(words)) if heads[k] == i + 1] for i in range(len(words))]
        self.assertEqual(Bot._predicates_of(words, tags, heads, labels, children, {1, 3}), [(5, [5])])
        self.assertEqual(Bot._predicates_of(words, tags, heads, labels, children, {3}), [])

    def test_the_parser_slip_with_an_apposition_is_a_predicate_too(self):
        tree = (['Rocco', 'es', 'un', 'perro', 'pastor', '.'], [P, AUX, D, N, N, X],
                [0, 4, 4, 1, 4, 1], ['root', 'cop', 'det', 'appos', 'compound', 'punct'])
        words, tags, heads, labels = tree
        children = [[k for k in range(len(words)) if heads[k] == i + 1] for i in range(len(words))]
        node, span = Bot._predicates_of(words, tags, heads, labels, children, {0})[0]
        self.assertEqual((node, sorted(span)), (3, [2, 3, 4]))


class PluralSubjectTests(unittest.TestCase):
    def test_coordination_is_plural_and_copied_whole(self):
        bot = taught()
        tree = (['Pedro', 'y', 'Luis', 'armaron', 'un', 'estante', '.'], [P, 'CCONJ', P, V, D, N, X],
                [4, 3, 1, 0, 6, 4, 4], ['nsubj', 'cc', 'conj', 'root', 'det', 'obj', 'punct'])
        self.assertTrue(bot._plural(tree, 0))
        self.assertFalse(bot._plural(tree, 5))
        self.assertEqual([w for w, _, _, _ in Bot._copy(tree, 0, coordination=True)], ['Pedro', 'y', 'Luis'])
        self.assertEqual([w for w, _, _, _ in Bot._copy(tree, 0)], ['Pedro'])


if __name__ == '__main__':
    unittest.main()

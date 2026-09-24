"""G-51: pairs of identity in a sentence and identity frames learned from worked questions."""
import unittest

from tests.test_references_and_same_fact import DEMOS
from leobot import Bot

P, D, N, V, A, X, AUX, ADJ = 'PROPN', 'DET', 'NOUN', 'VERB', 'ADP', 'PUNCT', 'AUX', 'ADJ'
# G-51: a plural noun (its number is learned) and «llama» with its dictionary form.
MORE = [
    (['Los', 'perros', 'duermen', '.'], [D, N, V, X], [2, 3, 0, 3], ['det', 'nsubj', 'root', 'punct'],
     ['Definite=Def|Gender=Masc|Number=Plur|PronType=Art', 'Gender=Masc|Number=Plur', 'Number=Plur|Person=3', '_'],
     ['el', 'perro', 'dormir', '.']),
    (['El', 'perro', 'se', 'llama', 'Rocko', '.'], [D, N, 'PRON', V, P, X], [2, 4, 4, 0, 4, 4],
     ['det', 'nsubj', 'expl', 'root', 'obj', 'punct'],
     ['Definite=Def|Gender=Masc|Number=Sing|PronType=Art', 'Gender=Masc|Number=Sing',
      'Case=Acc|Person=3|PronType=Prs|Reflex=Yes', 'Number=Sing|Person=3', '_', '_'],
     ['el', 'perro', 'él', 'llamar', 'Rocko', '.']),
]


def taught():
    bot = Bot()
    for _ in range(3):
        for words, tags, heads, labels, feats in DEMOS:
            bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats)
        for words, tags, heads, labels, feats, lemmas in MORE:
            bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats, lemmas=lemmas)
    bot.consolidate_syntax()
    return bot


class IdentityPairTests(unittest.TestCase):
    def test_apposition_and_copula_are_identity(self):
        bot = taught()
        appos = (['Vive', 'con', 'su', 'esposo', 'Julián', '.'], [V, A, D, N, P, X],
                 [0, 4, 4, 1, 4, 1], ['root', 'case', 'det', 'obl', 'appos', 'punct'])
        self.assertEqual(bot._identity_pairs(appos), {(3, 4)})
        copula = (['Elena', 'es', 'la', 'hermana', 'de', 'Daniel', '.'], [P, AUX, D, N, A, P, X],
                  [4, 4, 4, 0, 6, 4, 4], ['nsubj', 'cop', 'det', 'root', 'case', 'nmod', 'punct'])
        self.assertEqual(bot._identity_pairs(copula), {(3, 0)})
        # The parser's usual slip: the name as head, the predicate in apposition with its copula.
        slip = (['Elena', 'es', 'la', 'hermana', 'de', 'Daniel', '.'], [P, AUX, D, N, A, P, X],
                [0, 4, 4, 1, 6, 4, 1], ['root', 'cop', 'det', 'appos', 'case', 'nmod', 'punct'])
        self.assertEqual(bot._identity_pairs(slip), {(0, 3)})

    def test_quality_and_disagreeing_number_are_not_identity(self):
        bot = taught()
        quality = (['Bruno', 'es', 'de', 'color', 'negro', '.'], [P, AUX, A, N, ADJ, X],
                   [4, 4, 4, 0, 4, 4], ['nsubj', 'cop', 'case', 'root', 'amod', 'punct'])
        self.assertEqual(bot._identity_pairs(quality), set())
        number = (['Los', 'perros', 'la', 'casa', 'duermen', '.'], [D, N, D, N, V, X],
                  [2, 5, 4, 2, 0, 5], ['det', 'nsubj', 'det', 'appos', 'root', 'punct'])
        self.assertEqual(bot._identity_pairs(number), set())

    def test_identity_frames_are_learned_from_counts_and_give_verbs(self):
        bot = taught()
        bot.reading_model['identity_frames'] = {'como\x1fllamar': [11, 6], 'quien\x1fcop': [14, 8],
                                                'cual\x1fcop': [25, 1], 'que\x1ftener': [17, 0],
                                                'quien\x1ffundar': [3, 3]}
        bot._compile_identity_frames()
        self.assertEqual(bot.reading_model['identity_frames_learned'], ['como\x1fllamar', 'quien\x1fcop'])
        self.assertEqual(bot.reading_model['identity_verbs'], ['llamar'])
        named = (['El', 'equipo', 'se', 'llama', 'Halcones', '.'], [D, N, 'PRON', V, P, X],
                 [2, 4, 4, 0, 4, 4], ['det', 'nsubj', 'expl', 'root', 'obj', 'punct'])
        self.assertEqual(bot._identity_pairs(named), {(1, 4)})
        bot.learned_identity = False
        self.assertEqual(bot._identity_pairs(named), set())

    def test_nothing_is_learned_without_support(self):
        bot = taught()
        bot.reading_model['identity_frames'] = {'como\x1fllamar': [9, 9]}
        bot._compile_identity_frames()
        self.assertEqual(bot.reading_model['identity_verbs'], [])


if __name__ == '__main__':
    unittest.main()

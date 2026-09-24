"""G-47b: search by lemma, alternative lemmas, contractions, and the causes seen in G-47."""
import unittest

from leobot import Bot
from tests.test_references_and_same_fact import DEMOS, P, D, N, V, A, X


def taught(extra=()):
    bot = Bot()
    for _ in range(3):
        for words, tags, heads, labels, feats in list(DEMOS):
            bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats)
        # «llamado» is annotated both as itself and as «llamar»; «dice»/«dijo» as «decir».
        for words, lemmas in (('llamado', 'llamado'), ('llamado', 'llamar'), ('llamado', 'llamado'),
                              ('llama', 'llamar'), ('dice', 'decir'), ('dijo', 'decir')):
            bot.observe_parsed_sentence([words, '.'], [V, X], [0, 1], ['root', 'punct'], lemmas=[lemmas, '.'])
        bot.observe_multiword('del', ['de', 'el'])
    bot.consolidate_syntax()
    return bot


class LemmaTests(unittest.TestCase):
    def test_alternative_lemmas_are_kept(self):
        bot = taught()
        self.assertEqual(bot.lemma_key('llamado'), 'llamado')
        self.assertIn('llamar', bot.lemma_keys('llamado'))
        self.assertEqual(bot.lemma_keys('dice'), {'decir'})

    def test_search_uses_the_dictionary_form(self):
        bot = taught()
        self.assertEqual(bot._search_key('dijo'), bot._search_key('dice'))
        bot.lemma_sets = False
        self.assertNotEqual(bot._search_key('dijo'), bot._search_key('dice'))

    def test_contractions_are_written_as_said(self):
        bot = taught()
        self.assertEqual(bot._surface(['Ríos', 'de', 'el', 'Sur']), 'Ríos del Sur')


class StructureTests(unittest.TestCase):
    def test_possessor_of_a_predicated_noun_is_not_its_subject(self):
        bot = taught()
        before = (['Federico', 'enseña', 'música', '.'], [P, V, N, X], [2, 0, 2, 2], ['nsubj', 'root', 'obj', 'punct'])
        tree = (['Consuelo', 'es', 'su', 'esposa', '.'], [P, 'AUX', D, N, X], [4, 4, 4, 0, 4],
                ['nsubj', 'cop', 'det', 'root', 'punct'])
        self.assertEqual(bot._resolve_tree(tree, [before], {})[1], ['Federico'])
        bot.g47b_structure = False
        self.assertEqual(bot._resolve_tree(tree, [before], {})[1], ['Consuelo'])

    def test_a_name_takes_the_gender_of_the_pronoun_that_took_it_up(self):
        bot = taught()
        first = (['Elena', 'y', 'Marcos', 'fueron', '.'], [P, 'CCONJ', P, V, X], [4, 3, 1, 0, 4],
                 ['nsubj', 'cc', 'conj', 'root', 'punct'])
        her = (['Ella', 'tiene', 'pan', '.'], ['PRON', V, N, X], [2, 0, 2, 2], ['nsubj', 'root', 'obj', 'punct'])
        him = (['Él', 'tiene', 'café', '.'], ['PRON', V, N, X], [2, 0, 2, 2], ['nsubj', 'root', 'obj', 'punct'])
        learned = {}
        self.assertEqual(bot._resolve_tree(her, [first], learned)[1], ['Elena'])
        self.assertEqual(learned, {'elena': 'Fem'})
        self.assertEqual(bot._resolve_tree(him, [first, her], learned)[1], ['Marcos'])


if __name__ == '__main__':
    unittest.main()

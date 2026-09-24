"""G-48: correspondences of paths learned from worked examples answer paraphrases."""
import unittest

from tests.test_references_and_same_fact import P, D, N, V, A, X, taught

SAID = 'Sofía tiene un perro llamado Rocko .'
SAID_TREE = (SAID.split(), [P, V, D, N, 'ADJ', P, X], [2, 0, 4, 2, 4, 4, 2],
             ['nsubj', 'root', 'det', 'obj', 'amod', 'appos', 'punct'])
QUESTION = '¿ Cómo se llama el perro de Sofía ?'
QUESTION_TREE = (QUESTION.split(), [X, 'PRON', 'PRON', V, D, N, A, P, X], [4, 4, 4, 0, 6, 4, 8, 6, 4],
                 ['punct', 'obl', 'expl', 'root', 'det', 'obj', 'case', 'nmod', 'punct'])


def given():
    bot = taught()
    bot.syntax_model['interrogatives'] = ['cómo']
    bot._utterance_trees = {SAID: SAID_TREE, QUESTION: QUESTION_TREE}
    bot.reading_utterances.append({'document': 'conversación:1', 'source': 'c', 'text': SAID, 'tokens': SAID.split()})
    return bot


class PathTests(unittest.TestCase):
    def test_paths_are_sequences_of_functions(self):
        bot = given()
        links = bot._labeled_links(SAID_TREE[2], SAID_TREE[3])
        self.assertEqual(bot._sentence_path(links, 5, 3), '^appos')
        self.assertEqual(bot._sentence_path(links, 5, 0), '^appos ^obj vnsubj')

    def test_question_path_keeps_the_unaligned_words(self):
        bot = given()
        links = bot._labeled_links(QUESTION_TREE[2], QUESTION_TREE[3])
        verb = bot.lemma_key('llama')
        self.assertEqual(bot._question_path(QUESTION_TREE, links, 1, 5, set()), f'^obl {verb} vobj')
        self.assertEqual(bot._question_path(QUESTION_TREE, links, 1, 5, {3}), '^obl vobj')

    def test_a_learned_correspondence_answers_the_paraphrase(self):
        bot = given()
        verb = bot.lemma_key('llama')
        # Nothing aligns «llama» in what was said, so structure alone cannot answer.
        bot.reading_model['learned_paths'] = {}
        self.assertIsNone(bot.answer_by_structure(QUESTION))
        bot.reading_model['learned_paths'] = {f'^obl {verb} vobj': {'^appos': -0.2},
                                              f'^obl {verb} vobj vnmod': {'^appos ^obj vnsubj': -0.3}}
        self.assertEqual(bot.answer_by_structure(QUESTION)['text'], 'Rocko')
        bot.learned_paths = False
        self.assertIsNone(bot.answer_by_structure(QUESTION))

    def test_an_unlearned_path_does_not_answer(self):
        bot = given()
        verb = bot.lemma_key('llama')
        bot.reading_model['learned_paths'] = {f'^obl {verb} vobj': {'^appos': -0.2},
                                              f'^obl {verb} vobj vnmod': {'vnsubj': -0.3}}
        self.assertIsNone(bot.answer_by_structure(QUESTION))


if __name__ == '__main__':
    unittest.main()

"""G-47: references resolved from learned features; one fact about one entity."""
import unittest

from leobot import Bot

P, D, N, V, A, X = 'PROPN', 'DET', 'NOUN', 'VERB', 'ADP', 'PUNCT'
# Demonstrations with the treebank's morphological features (three times each,
# so that the features reach the promotion rule).
DEMOS = [
    (['Él', 'tiene', 'un', 'perro', '.'], ['PRON', V, D, N, X], [2, 0, 4, 2, 2],
     ['nsubj', 'root', 'det', 'obj', 'punct'],
     ['Case=Acc,Nom|Gender=Masc|Number=Sing|Person=3|PronType=Prs', 'Number=Sing|Person=3',
      'Gender=Masc|Number=Sing', 'Gender=Masc|Number=Sing', '_']),
    (['Ella', 'vive', 'con', 'su', 'hija', '.'], ['PRON', V, A, D, N, X], [2, 0, 5, 5, 2, 2],
     ['nsubj', 'root', 'case', 'det', 'obl', 'punct'],
     ['Case=Acc,Nom|Gender=Fem|Number=Sing|Person=3|PronType=Prs', 'Number=Sing|Person=3', '_',
      'Number=Sing|Person=3|Poss=Yes|PronType=Prs', 'Gender=Fem|Number=Sing', '_']),
    (['La', 'reunión', 'la', 'organizó', 'Ana', '.'], [D, N, 'PRON', V, P, X], [2, 4, 4, 0, 4, 4],
     ['det', 'obj', 'obj', 'root', 'nsubj', 'punct'],
     ['Gender=Fem|Number=Sing', 'Gender=Fem|Number=Sing',
      'Case=Acc|Gender=Fem|Number=Sing|Person=3|PronType=Prs', 'Number=Sing|Person=3', '_', '_']),
    (['Compré', 'pan', '.'], [V, N, X], [0, 1, 1], ['root', 'obj', 'punct'],
     ['Number=Sing|Person=1', 'Gender=Masc|Number=Sing', '_']),
    (['Usó', 'pan', '.'], [V, N, X], [0, 1, 1], ['root', 'obj', 'punct'],
     ['Number=Sing|Person=3', 'Gender=Masc|Number=Sing', '_']),
]


def taught():
    bot = Bot()
    for _ in range(3):
        for words, tags, heads, labels, feats in DEMOS:
            bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats)
    bot.consolidate_syntax()
    return bot


class ReferenceTests(unittest.TestCase):
    def test_features_are_learned_per_word_and_class(self):
        bot = taught()
        self.assertIn('Poss=Yes', bot.morphology('su', 'DET'))
        self.assertIn('Gender=Fem', bot.morphology('la', 'PRON'))
        self.assertNotIn('PronType=Prs', bot.morphology('la', 'DET'))

    def test_possessive_takes_the_subject_of_its_clause(self):
        bot = taught()
        tree = (['Pedro', 'viajó', 'con', 'su', 'prima', 'Rosa', '.'], [P, V, A, D, N, P, X],
                [2, 0, 5, 5, 2, 5, 2], ['nsubj', 'root', 'case', 'det', 'obl', 'appos', 'punct'])
        (words, tags, heads, labels, _), added = bot._resolve_tree(tree, [])
        self.assertEqual(added, ['Pedro'])
        de = words.index('de')
        self.assertEqual(words[de + 1], 'Pedro')
        self.assertEqual(heads[de + 1] - 1, words.index('prima'))
        self.assertEqual(labels[de + 1], 'nmod')

    def test_pronoun_agrees_in_gender_and_skips_its_own_clause(self):
        bot = taught()
        before = (['Ana', 'compró', 'una', 'mesa', 'y', 'un', 'perro', '.'], [P, V, D, N, 'CCONJ', D, N, X],
                  [2, 0, 4, 2, 7, 7, 4, 2], ['nsubj', 'root', 'det', 'obj', 'cc', 'det', 'conj', 'punct'])
        tree = (['Él', 'tiene', 'tres', 'años', '.'], ['PRON', V, 'NUM', N, X], [2, 0, 4, 2, 2],
                ['nsubj', 'root', 'nummod', 'obj', 'punct'])
        (words, _, _, _, _), added = bot._resolve_tree(tree, [before])
        # «Ana» has no learned gender (compatible), but she is not masculine-marked;
        # the subject of the previous sentence comes first.
        self.assertEqual(added, ['Ana'])
        clitic = (['Luis', 'la', 'organizó', '.'], [P, 'PRON', V, X], [3, 3, 0, 3],
                  ['nsubj', 'obj', 'root', 'punct'])
        meeting = (['La', 'reunión', 'fue', 'larga', '.'], [D, N, 'AUX', 'ADJ', X], [2, 4, 4, 0, 4],
                   ['det', 'nsubj', 'cop', 'root', 'punct'])
        (words, _, _, _, _), added = bot._resolve_tree(clitic, [meeting])
        self.assertIn('reunión', added)
        self.assertNotIn('Luis', added)

    def test_omitted_subject_of_the_third_person_only(self):
        bot = taught()
        before = (['Rosa', 'preparó', 'sopa', '.'], [P, V, N, X], [2, 0, 2, 2], ['nsubj', 'root', 'obj', 'punct'])
        third = (['Usó', 'pan', '.'], [V, N, X], [0, 1, 1], ['root', 'obj', 'punct'])
        (words, _, heads, labels, _), added = bot._resolve_tree(third, [before])
        self.assertEqual(added, ['Rosa'])
        self.assertEqual(labels[words.index('Rosa')], 'nsubj')
        first = (['Compré', 'pan', '.'], [V, N, X], [0, 1, 1], ['root', 'obj', 'punct'])
        self.assertEqual(bot._resolve_tree(first, [before])[1], [])

    def test_switch_off_leaves_the_sentence_as_said(self):
        bot = taught()
        bot.reference_resolution = False
        row = {'document': 'conversación:1', 'text': 'Usó pan.', 'tokens': ['Usó', 'pan', '.']}
        bot.reading_utterances = [row]
        bot._utterance_trees = {'Usó pan.': (['Usó', 'pan', '.'], [V, N, X], [0, 1, 1], ['root', 'obj', 'punct'])}
        self.assertEqual(bot._row_tree(row)[0], ['Usó', 'pan', '.'])


class SameFactTests(unittest.TestCase):
    def given(self, trees):
        bot = taught()
        bot.syntax_model['interrogatives'] = ['cuántos', 'dónde']
        bot._utterance_trees = dict(trees)
        for text in trees:
            if not text.startswith('¿'):
                bot.reading_utterances.append({'document': 'conversación:%d' % len(bot.reading_utterances),
                                               'source': 'c', 'text': text, 'tokens': text.split()})
        return bot

    def test_each_question_word_takes_one_occurrence(self):
        said = 'Luis tiene ocho años y Elena tiene doce años .'
        question = '¿ Cuántos años tiene Elena ?'
        bot = self.given({
            said: (said.split(), [P, V, 'NUM', N, 'CCONJ', P, V, 'NUM', N, X], [2, 0, 4, 2, 7, 7, 2, 9, 7, 2],
                   ['nsubj', 'root', 'nummod', 'obj', 'cc', 'nsubj', 'advcl', 'nummod', 'obj', 'punct']),
            question: (question.split(), [X, 'PRON', N, V, P, X], [4, 4, 4, 0, 4, 4],
                       ['punct', 'nsubj', 'obl', 'root', 'nsubj', 'punct'])})
        self.assertEqual(bot.answer_by_structure(question)['text'], 'doce')
        bot.same_fact = False
        self.assertEqual(bot.answer_by_structure(question)['text'], 'ocho')

    def test_another_entity_in_between_does_not_answer(self):
        said = 'El hermano de Marta vive en Loja .'
        question = '¿ Dónde vive Marta ?'
        bot = self.given({
            said: (said.split(), [D, N, A, P, V, A, P, X], [2, 5, 4, 2, 0, 7, 5, 5],
                   ['det', 'nsubj', 'case', 'nmod', 'root', 'case', 'obl', 'punct']),
            question: (question.split(), [X, 'PRON', V, P, X], [3, 3, 0, 3, 3],
                       ['punct', 'advmod', 'root', 'nsubj', 'punct'])})
        self.assertIsNone(bot.answer_by_structure(question))

    def test_numbers_split_by_the_parser_answer_together(self):
        said = 'Rosa tiene cuarenta y dos años .'
        question = '¿ Cuántos años tiene Rosa ?'
        bot = self.given({
            said: (said.split(), [P, V, 'NUM', 'CCONJ', 'NUM', N, X], [2, 0, 6, 6, 6, 2, 2],
                   ['nsubj', 'root', 'nummod', 'cc', 'nummod', 'obj', 'punct']),
            question: (question.split(), [X, 'PRON', N, V, P, X], [4, 4, 4, 0, 4, 4],
                       ['punct', 'nsubj', 'obl', 'root', 'nsubj', 'punct'])})
        self.assertEqual(bot.answer_by_structure(question)['text'], 'cuarenta y dos')

    def test_a_negated_statement_does_not_answer(self):
        said = 'Julia no revisó el paquete .'
        question = '¿ Quién revisó el paquete ?'
        bot = self.given({
            said: (said.split(), [P, 'ADV', V, D, N, X], [3, 3, 0, 5, 3, 3],
                   ['nsubj', 'advmod', 'root', 'det', 'obj', 'punct']),
            question: (question.split(), [X, 'PRON', V, D, N, X], [3, 3, 0, 5, 3, 3],
                       ['punct', 'nsubj', 'root', 'det', 'obj', 'punct'])})
        bot.syntax_model['interrogatives'] = ['quién']
        bot.syntax_model['negators'] = ['no']
        self.assertIsNone(bot.answer_by_structure(question))

    def test_verb_first_question_is_verified_through_its_own_words(self):
        said = 'La ferretería no vende cables .'
        question = '¿ Vende la ferretería cables ?'
        bot = self.given({
            said: (said.split(), [D, N, 'ADV', V, N, X], [2, 4, 4, 0, 4, 4],
                   ['det', 'nsubj', 'advmod', 'root', 'obj', 'punct']),
            # The object hung from the subject, as the parser does with this order.
            question: (question.split(), [X, V, D, N, N, X], [2, 0, 4, 2, 4, 2],
                       ['punct', 'root', 'det', 'obj', 'nmod', 'punct'])})
        bot.syntax_model['negators'] = ['no']
        self.assertEqual(bot.verify_from_utterances(question)['status'], 'literal_no')


if __name__ == '__main__':
    unittest.main()

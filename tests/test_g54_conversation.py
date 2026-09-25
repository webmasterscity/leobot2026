"""G-54: the voice of the answer: what was told, said back with learned forms.

The content mechanisms of G-54 were retired by rule 5.9 (no contribution on the held-out); their tests went with them."""
import unittest

from tests.test_references_and_same_fact import DEMOS
from leobot import Bot

P, D, N, V, A, X, AUX, NUM, C = 'PROPN', 'DET', 'NOUN', 'VERB', 'ADP', 'PUNCT', 'AUX', 'NUM', 'CCONJ'
FIN1 = 'Mood=Ind|Number=Sing|Person=1|Tense=Pres|VerbForm=Fin'
FIN2 = 'Mood=Ind|Number=Sing|Person=2|Tense=Pres|VerbForm=Fin'
# Demonstrations of a marked negator and of the first person, with dictionary forms.
MORE = [
    (['No', 'come', 'pan', '.'], ['ADV', V, N, X], [2, 0, 2, 2], ['advmod', 'root', 'obj', 'punct'],
     ['Polarity=Neg', 'Number=Sing|Person=3', 'Gender=Masc|Number=Sing', '_'], ['no', 'comer', 'pan', '.']),
    (['Mi', 'hija', 'come', 'pan', '.'], [D, N, V, N, X], [2, 3, 0, 3, 3], ['det', 'nsubj', 'root', 'obj', 'punct'],
     ['Number=Sing|Number[psor]=Sing|Person=1|Poss=Yes|PronType=Prs', 'Gender=Fem|Number=Sing',
      'Number=Sing|Person=3', 'Gender=Masc|Number=Sing', '_'], ['mi', 'hija', 'comer', 'pan', '.']),
    (['Me', 'llamo', 'Ana', '.'], ['PRON', V, P, X], [2, 0, 2, 2], ['expl', 'root', 'obj', 'punct'],
     ['Case=Acc|Number=Sing|Person=1|PrepCase=Npr|PronType=Prs|Reflex=Yes', FIN1, '_', '_'],
     ['yo', 'llamar', 'Ana', '.']),
    (['Tengo', 'pan', '.'], [V, N, X], [0, 1, 1], ['root', 'obj', 'punct'],
     [FIN1, 'Gender=Masc|Number=Sing', '_'], ['tener', 'pan', '.']),
    (['El', 'perro', 'ladra', '.'], [D, N, V, X], [2, 3, 0, 3], ['det', 'nsubj', 'root', 'punct'],
     ['Definite=Def|Gender=Masc|Number=Sing|PronType=Art', 'Gender=Masc|Number=Sing', 'Number=Sing|Person=3', '_'],
     ['el', 'perro', 'ladrar', '.']),
]
# Second-person forms (a treebank of speech, forms only): two lemmas in -ar give the ending rule.
FORMS = [
    (['Te', 'llevas', 'pan'], ['PRON', V, N], ['tú', 'llevar', 'pan'],
     ['Case=Acc|Number=Sing|Person=2|PrepCase=Npr|PronType=Prs|Reflex=Yes', FIN2, '_']),
    (['Miras', 'tu', 'pan'], [V, D, N], ['mirar', 'tu', 'pan'],
     [FIN2, 'Number=Sing|Number[psor]=Sing|Person=2|Poss=Yes|PronType=Prs', '_']),
    (['Llevo', 'y', 'miro'], [V, C, V], ['llevar', 'y', 'mirar'], [FIN1, '_', FIN1]),
]


def taught():
    bot = Bot()
    for _ in range(3):
        for words, tags, heads, labels, feats in DEMOS:
            bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats)
        for words, tags, heads, labels, feats, lemmas in MORE:
            bot.observe_parsed_sentence(words, tags, heads, labels, feats=feats, lemmas=lemmas)
    for words, tags, lemmas, feats in FORMS:
        bot.observe_forms(words, tags, lemmas, feats)
    bot.consolidate_syntax()
    bot.reading_model['identity_verbs'] = ['llamar']
    return bot


def given(trees):
    bot = taught()
    bot.syntax_model['interrogatives'] = ['cuántos', 'qué', 'cómo']
    bot._utterance_trees = dict(trees)
    for text in trees:
        if not text.startswith('¿'):
            bot.reading_utterances.append({'document': 'conversación:%d' % len(bot.reading_utterances),
                                           'source': 'c', 'text': text, 'tokens': text.split()})
    return bot


class VoiceTests(unittest.TestCase):
    def test_persons_are_swapped_with_learned_forms(self):
        name = 'Me llamo Sofía .'
        mother = 'Mi mamá se llama Luz .'
        bot = given({
            mother: (mother.split(), [D, N, 'PRON', V, P, X], [2, 4, 4, 0, 4, 4],
                     ['det', 'nsubj', 'expl', 'root', 'obj', 'punct']),
            name: (name.split(), ['PRON', V, P, X], [2, 0, 2, 2], ['expl', 'root', 'obj', 'punct'])})
        self.assertEqual(bot._swapped_form('mi', D), 'tu')
        self.assertEqual(bot._swapped_form('Me', 'PRON'), 'Te')
        self.assertEqual(bot._swapped_form('llamo', V), 'llamas')      # never seen: the learned -ar ending
        self.assertIsNone(bot._swapped_form('mamá', N))
        rows = bot.reading_utterances
        self.assertEqual(bot._restated(rows[0]), 'tu mamá se llama Luz')
        self.assertEqual(bot._voiced('yes', [rows[1]]), 'Sí, me contaste que te llamas Sofía.')
        bot.answer_voice = False
        self.assertIsNone(bot._voiced('yes', [rows[1]]))


if __name__ == '__main__':
    unittest.main()

"""G-54: the scope of negation in yes/no, a denied value, who speaks, the last thing said, and the voice."""
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


class ScopeTests(unittest.TestCase):
    def test_a_negator_negates_only_what_it_hangs_from(self):
        said = 'Pedro no come pan y bebe vino .'
        question = '¿ Bebe Pedro vino ?'
        bot = given({
            said: (said.split(), [P, 'ADV', V, N, C, V, N, X], [3, 3, 0, 3, 6, 3, 6, 3],
                   ['nsubj', 'advmod', 'root', 'obj', 'cc', 'conj', 'obj', 'punct']),
            question: (question.split(), [X, V, P, N, X], [2, 0, 2, 2, 2], ['punct', 'root', 'nsubj', 'obj', 'punct'])})
        self.assertIn('no', bot.negator_words())
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('Sí'))
        bot.scoped_polarity = False
        self.assertTrue(bot.verify_from_utterances(question)['text'].startswith('No'))

    def test_a_denied_value_is_not_the_answer(self):
        said = 'Elena tiene doce años , no trece .'
        question = '¿ Cuántos años tiene Elena ?'
        bot = given({
            said: (said.split(), [P, V, NUM, N, X, 'ADV', NUM, X], [2, 0, 4, 2, 7, 7, 3, 2],
                   ['nsubj', 'root', 'nummod', 'obj', 'punct', 'advmod', 'conj', 'punct']),
            question: (question.split(), [X, 'PRON', N, V, P, X], [4, 4, 4, 0, 4, 4],
                       ['punct', 'nsubj', 'obl', 'root', 'nsubj', 'punct'])})
        self.assertEqual(bot.answer_by_structure(question)['text'], 'doce')
        bot.negated_value = False
        self.assertIn('trece', bot.answer_by_structure(question)['text'])


class NameKindTests(unittest.TestCase):
    def test_a_name_passes_only_where_names_are_a_learned_answer_class(self):
        from tests.test_g53_answer_kind import COLOURS, taught as colour_bot
        bot = colour_bot()
        for colour in COLOURS * 8:
            bot.observe_answer_kind('¿De qué color es la casa?', colour)
        low = ['de', 'qué', 'color', 'es', 'la', 'casa']
        row = bot.reading_model['answer_kinds']['que color']
        row['classes'] = {'ADJ': 21, 'NOUN': 19}           # as in SQuAD-es: no class takes 2/3, so no class check
        self.assertFalse(bot._kind_fits(low, 1, 2, 'Ignacio', ('Ignacio', 'PROPN')))
        bot.name_kind = False
        self.assertTrue(bot._kind_fits(low, 1, 2, 'Ignacio', ('Ignacio', 'PROPN')))       # G-53 as frozen
        bot.name_kind = True
        row['classes']['PROPN'] = 10                                                          # names are 20 % of answers
        row['n'] += 10
        self.assertTrue(bot._kind_fits(low, 1, 2, 'Ignacio', ('Ignacio', 'PROPN')))


class ConstituentTests(unittest.TestCase):
    def test_the_parts_of_a_name_answer_together(self):
        said = 'Rosa estudia en el colegio Santa Ana .'
        question = '¿ En qué colegio estudia Rosa ?'
        bot = given({
            said: (said.split(), [P, V, A, D, N, P, P, X], [2, 0, 5, 5, 2, 5, 5, 2],
                   ['nsubj', 'root', 'case', 'det', 'obl', 'appos', 'flat', 'punct']),
            question: (question.split(), [X, A, D, N, V, P, X], [5, 4, 4, 5, 0, 5, 5],
                       ['punct', 'case', 'det', 'obl', 'root', 'nsubj', 'punct'])})
        self.assertEqual(bot.answer_by_structure(question)['text'], 'Santa Ana')
        bot.answer_constituent = False
        self.assertNotEqual(bot.answer_by_structure(question)['text'], 'Santa Ana')


class GapCaseTests(unittest.TestCase):
    def test_the_gap_preposition_outweighs_distances(self):
        said = 'Laura viajó en autobús a Cartagena .'
        question = '¿ A dónde viajó Laura ?'
        bot = given({
            said: (said.split(), [P, V, A, N, A, P, X], [2, 0, 4, 2, 6, 2, 2],
                   ['nsubj', 'root', 'case', 'obl', 'case', 'obl', 'punct']),
            question: (question.split(), [X, A, 'ADV', V, P, X], [4, 3, 4, 0, 4, 4],
                       ['punct', 'case', 'advmod', 'root', 'nsubj', 'punct'])})
        bot.syntax_model['interrogatives'] = ['dónde']
        self.assertEqual(bot.answer_by_structure(question)['text'], 'a Cartagena')


class NameGroupTests(unittest.TestCase):
    def test_a_capitalized_word_before_an_apposed_name_is_part_of_it(self):
        words, heads = ['la', 'escuela', 'San', 'Jorge', 'grande'], [2, 0, 2, 2, 2]
        labels, tags = ['det', 'root', 'amod', 'appos', 'amod'], [D, N, 'ADJ', P, 'ADJ']
        nodes = [(2, [2]), (3, [3])]
        self.assertEqual(Bot._joined_siblings(nodes, heads, labels, tags, words, True), [(3, [2, 3])])
        self.assertEqual(len(Bot._joined_siblings(nodes, heads, labels, tags, words, False)), 2)
        lower = ['la', 'escuela', 'vieja', 'Jorge', 'grande']
        self.assertEqual(len(Bot._joined_siblings(nodes, heads, labels, tags, lower, True)), 2)


class SpeakerTests(unittest.TestCase):
    def conversation(self):
        name = 'Me llamo Sofía .'
        mother = 'Mi mamá se llama Luz .'
        dog = 'Tengo un perro .'
        barks = 'Ladra mucho .'
        return given({
            mother: (mother.split(), [D, N, 'PRON', V, P, X], [2, 4, 4, 0, 4, 4],
                     ['det', 'nsubj', 'expl', 'root', 'obj', 'punct']),
            name: (name.split(), ['PRON', V, P, X], [2, 0, 2, 2], ['expl', 'root', 'obj', 'punct']),
            dog: (dog.split(), [V, D, N, X], [0, 3, 1, 1], ['root', 'det', 'obj', 'punct']),
            barks: (barks.split(), [V, 'ADV', X], [0, 1, 1], ['root', 'advmod', 'punct'])})

    def test_the_first_person_is_who_speaks_once_named(self):
        bot = self.conversation()
        tree, node = bot._speaker()
        self.assertEqual(tree[0][node], 'Sofía')
        bot._resolve_references()
        rows = bot.reading_utterances
        self.assertEqual(rows[0]['resolved'][0], ['mamá', 'de', 'Sofía', 'se', 'llama', 'Luz', '.'])
        self.assertIn('Sofía', rows[2]['resolved'][0])          # «tengo»: Sofía has the dog
        words, _, heads, labels, _ = rows[1]['resolved']
        self.assertEqual(labels[words.index('Sofía')], 'nsubj')       # «llamo»: the subject is who speaks

    def test_a_third_person_never_refers_to_who_speaks(self):
        bot = self.conversation()
        bot._resolve_references()
        barks = bot.reading_utterances[3]['resolved'][0]
        self.assertEqual(barks[:2], ['un', 'perro'])

    def test_without_the_switch_nothing_changes(self):
        bot = self.conversation()
        bot.speaker = False
        self.assertIsNone(bot._speaker())
        bot._resolve_references()
        self.assertNotIn('resolved', bot.reading_utterances[0])


class DativeTests(unittest.TestCase):
    def test_a_dative_clitic_is_resolved_with_its_learned_preposition(self):
        before = 'Valentina cumple años .'
        gift = 'Su papá le regala una bicicleta .'
        bot = given({
            before: (before.split(), [P, V, N, X], [2, 0, 2, 2], ['nsubj', 'root', 'obj', 'punct']),
            gift: (gift.split(), [D, N, 'PRON', V, D, N, X], [2, 4, 4, 0, 6, 4, 4],
                   ['det', 'nsubj', 'iobj', 'root', 'det', 'obj', 'punct'])})
        bot._resolve_references()
        words, _, heads, labels, _ = bot.reading_utterances[1]['resolved']
        self.assertEqual(words, ['papá', 'de', 'Valentina', 'a', 'Valentina', 'regala', 'una', 'bicicleta', '.'])
        self.assertEqual((labels[3], heads[3]), ('case', 5))
        bot = given({before: bot._utterance_trees[before], gift: bot._utterance_trees[gift]})
        bot.dative_copy = False
        bot._resolve_references()
        self.assertNotIn('a', bot.reading_utterances[1]['resolved'][0])


class RecencyTests(unittest.TestCase):
    def meeting(self):
        first = 'La reunión es el martes .'
        then = 'La reunión es el lunes .'
        open_q = '¿ Qué día es la reunión ?'
        yes_no = '¿ La reunión es el martes ?'
        bot = given({
            first: (first.split(), [D, N, AUX, D, N, X], [2, 5, 5, 5, 0, 5], ['det', 'nsubj', 'cop', 'det', 'root', 'punct']),
            then: (then.split(), [D, N, AUX, D, N, X], [2, 5, 5, 5, 0, 5], ['det', 'nsubj', 'cop', 'det', 'root', 'punct']),
            open_q: (open_q.split(), [X, D, N, AUX, D, N, X], [3, 3, 0, 3, 6, 3, 3],
                     ['punct', 'det', 'root', 'cop', 'det', 'nsubj', 'punct']),
            yes_no: (yes_no.split(), [X, D, N, AUX, D, N, X], [6, 3, 6, 6, 6, 0, 6],
                     ['punct', 'det', 'nsubj', 'cop', 'det', 'root', 'punct'])})
        days = {f'{d}\x1fNOUN': 3 for d in ('lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo')}
        bot.reading_model['answer_kinds'] = {'que dia': {'n': 40, 'classes': {'NOUN': 40}, 'members': days},
                                             'que': {'n': 40, 'classes': {'NOUN': 20, 'VERB': 20}, 'members': {}}}
        return bot, open_q, yes_no

    def test_the_last_value_said_replaces_the_earlier_one(self):
        bot, open_q, yes_no = self.meeting()
        self.assertEqual(bot.answer_by_structure(open_q)['text'], 'el lunes')
        self.assertTrue(bot.verify_from_utterances(yes_no)['text'].startswith('No'))
        self.assertTrue(bot._same_kind('martes', 'lunes'))
        self.assertFalse(bot._same_kind('martes', 'nueva'))     # another dimension never replaces
        bot.recency = False
        self.assertEqual(bot.answer_by_structure(open_q)['status'], 'literal_ambiguous')
        self.assertTrue(bot.verify_from_utterances(yes_no)['text'].startswith('Sí'))


class VoiceTests(unittest.TestCase):
    def test_persons_are_swapped_with_learned_forms(self):
        bot = SpeakerTests().conversation()
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

"""Structural checks independent of the business evaluation banks."""
import unittest
from types import SimpleNamespace

from experiments.g86_ordered_fragments import fragments, view, FragmentBinding


class FragmentTests(unittest.TestCase):
    def test_order_and_transport_of_symbols(self):
        q = (('x', 'v', 'y'), ('NOUN', 'VERB', 'NOUN'), ())
        a = (('x', 'v', 'z'), ('NOUN', 'VERB', 'NOUN'), ())
        reverse = (('z', 'v', 'x'), a[1], ())
        self.assertNotEqual(fragments(q, a, {}), fragments(q, reverse, {}))
        self.assertEqual(fragments(q, a, {}, unordered=True),
                         fragments(q, reverse, {}, unordered=True))
        renamed_q = (('r', 's', 't'), q[1], ())
        renamed_a = (('r', 's', 'u'), a[1], ())
        self.assertEqual(fragments(q, a, {}), fragments(renamed_q, renamed_a, {}))

    def test_learned_link_and_punctuation(self):
        q = (('', 'x', ''), ('PUNCT', 'NOUN', 'PUNCT'), ('interrogative',))
        a = (('y', ''), ('NOUN', 'PUNCT'), ())
        linked = fragments(q, a, {'x': [('y', .5)]})
        self.assertNotEqual(linked, fragments(q, a, {}))
        self.assertEqual(linked, fragments((('', 'r', ''), q[1], q[2]),
                                           (('s', ''), a[1], ()), {'r': [('s', .5)]}))
        self.assertFalse(any('PUNCT:1' in f or 'PUNCT:2' in f for group in linked for f in group))

    def test_length_is_checked_before_tagging(self):
        bot = SimpleNamespace(split_words=lambda text: text.split(),
                              tag_words=lambda words: self.fail('Long input was tagged'))
        self.assertIsNone(view(bot, ' '.join(['x']*25), 24))
        self.assertEqual(fragments(None, None, {}), [set(), set(), set()])

    def test_document_replacement_and_disable(self):
        def native(order, how, base, asked, terms, question, k):
            return [{'unchanged': 'yes'} for _ in order[:k]]
        def load(text, instructions=''):
            bot.context_units = [{'text': text}]
            return {'status': 'context_loaded'}
        bot = SimpleNamespace(context_model={'fragments': {'mode': 'ordered', 'weights': {}}},
                              context_units=[], syntax_model={'interrogatives': {}},
                              split_words=lambda text: text.split(), tag_words=lambda words: ['NOUN']*len(words),
                              _term=lambda word: word, _bridge=lambda: {}, _candidates=native, load_context=load)
        binding = FragmentBinding(bot, (-1, 0, 1))
        bot.load_context('first')
        first = binding.prepared
        bot.load_context('second')
        self.assertIsNot(first, binding.prepared)
        self.assertEqual(binding.prepared[0][0], ('second',))
        bot.context_model = {}
        args = ([(0., 0)], {}, 0., None, ['q'], 'q', 6)
        self.assertEqual(bot._candidates(*args), [{'unchanged': 'yes'}])
        binding.restore()
        self.assertIs(bot._candidates, native)
        self.assertIs(bot.load_context, load)


if __name__ == '__main__':
    unittest.main()

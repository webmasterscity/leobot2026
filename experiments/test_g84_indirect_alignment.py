import importlib
import unittest


class IndirectAlignmentContract(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g84_indirect_alignment')

    def packet(self):
        # Only observed edges: a -> b -> c -> d. No identity edges supplied.
        return {'questions': ['a', 'b', 'c', 'd'], 'answers': ['a', 'b', 'c', 'd'],
                'background': [.25]*4, 'one': [[[1, 1.]], [[2, 1.]], [[3, 1.]], []]}

    def test_two_steps_and_counterevidence(self):
        m = self.module()
        packet = self.packet()
        two = m.compose(packet['one'], packet['questions'], packet['answers'])
        self.assertEqual(two, [[[2, 1.]], [[3, 1.]], [], []])
        packet['one'][1] = [[0, 1.]]
        self.assertEqual(m.compose(packet['one'], packet['questions'], packet['answers'])[0], [[0, 1.]])
        rows = [(str(d), (q,), (a,)) for d in range(6) for q, a in [('b', 'a'), ('c', 'b'), ('d', 'c')]]
        learned, _ = m.g65.train(rows, 1)
        packet, _ = m.compile_direct(learned)
        two = m.compose(packet['one'], packet['questions'], packet['answers'])
        a = packet['answers'].index('a')
        self.assertEqual([(packet['questions'][i], p) for i, p in two[a]], [('c', 1.)])

    def test_symbol_renaming_preserves_indirect_distribution(self):
        m = self.module()
        packet = self.packet()
        expected = m.compose(packet['one'], packet['questions'], packet['answers'])
        renaming = dict(zip(packet['questions'], ['zz', 'tt', 'rr', 'pp']))
        self.assertEqual(expected, m.compose(packet['one'], [renaming[w] for w in packet['questions']],
                                            [renaming[w] for w in packet['answers']]))
        self.assertAlmostEqual(m.distance({0: 1.}, {1: 1.}), 1.)
        self.assertAlmostEqual(m.distance({0: .3, 1: .7}, {0: .3, 1: .7}), 0.)

    def test_document_replacement_and_disabled_features(self):
        m = self.module()
        from leobot import Bot
        from experiments.g79_joint_selection import Components
        bot = Bot()
        reference = Components().bind(bot)
        bot.load_context('a: 11.\nb: 22.', '')
        original = bot.selection_candidates('c a b?', 6)
        binding = m.AlignmentBinding(bot)
        self.assertEqual(original, bot.selection_candidates('c a b?', 6))
        packet = self.packet()
        packet['two'] = m.compose(packet['one'], packet['questions'], packet['answers'])
        bot.context_model['alignment'] = packet
        rows = bot.selection_candidates('c a b?', 6)
        by_name = {bot.context_units[i]['text'].split(':')[0]: f for i, f in rows}
        self.assertGreater(int(by_name['a']['alignment2_score']), int(by_name['b']['alignment2_score']))
        bot.load_context('d: 33.', '')
        rows = bot.selection_candidates('c a b?', 6)
        self.assertTrue(all(int(f['alignment2_score']) < int(by_name['a']['alignment2_score']) for _, f in rows))
        binding.restore()
        self.assertFalse(any(k.startswith('alignment') for _, f in bot.selection_candidates('c?', 6) for k in f))
        reference.restore()


if __name__ == '__main__':
    unittest.main()

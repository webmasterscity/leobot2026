import importlib
import unittest


class HumanSelectionContract(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g85_human_selection')

    def test_position_distinguishes_repeated_value_and_ambiguous_unit(self):
        m = self.module()
        context = 'u tiene 11. v tiene 11. w tiene 22.'
        start = context.index('11', context.index('v'))
        self.assertEqual(m.unit_label(context, 'v tiene 11.', '11', start), 1)
        self.assertIsNone(m.unit_label(context, 'u tiene 11.', '11', start))
        self.assertEqual(m.unit_label(context, 'w tiene 22.', '11', start), 0)
        self.assertFalse(m.covers(context, 'v tiene', start, 2))

    def test_repeated_signal_matches_reference_before_and_after_new_context(self):
        m = self.module()
        from leobot import Bot
        from experiments.g79_joint_selection import Components
        from experiments.g84_indirect_alignment import AlignmentBinding
        bot = Bot()
        ref = Components().bind(bot)
        one = [[[1, 1.]], [[2, 1.]], [[0, 1.]]]
        bot.context_model['alignment'] = {'questions': ['a', 'b', 'c'], 'answers': ['a', 'b', 'c'],
                                          'background': [1/3]*3, 'one': one, 'two': one}
        expected = []
        binding = AlignmentBinding(bot)
        for context in ('a: 11.\nb: 22.', 'c: 33.'):
            bot.load_context(context, '')
            expected.append(bot.selection_candidates('c a b?', 6))
        binding.restore()
        binding = m.DirectBinding(bot)
        for context, want in zip(('a: 11.\nb: 22.', 'c: 33.'), expected):
            bot.load_context(context, '')
            self.assertEqual(bot.selection_candidates('c a b?', 6), want)
        binding.restore()
        ref.restore()

    def test_human_rows_train_but_do_not_calibrate(self):
        m = self.module()
        from experiments.g79_joint_selection import Components
        components = Components()
        components.correct_calibration()
        ns = components.learner
        turns = [{'half': i % 2, 'rows': [({'x': '0'}, 0), ({'x': '1'}, 1)]} for i in range(80)]
        human = [{'half': -1, 'rows': [({'x': '2'}, 0), ({'x': '3'}, 1)]} for _ in range(100)]
        fitted, sizes = ns['fit'], []
        def recording(items, names):
            sizes.append(len(items))
            return fitted(items, names)
        ns['fit'] = recording
        model = m.teach(ns, turns, human)
        self.assertEqual(sizes, [140, 140, 180])
        self.assertEqual(sum(n for _, _, n in model['calibration']), 80)
        self.assertIs(ns['fit'], recording)


if __name__ == '__main__':
    unittest.main()

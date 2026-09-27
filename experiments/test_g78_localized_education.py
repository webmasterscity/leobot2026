import importlib.util
import unittest


class LocalizedEducationContract(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('experiments.g78_localized_education'))
        from experiments import g78_localized_education
        return g78_localized_education

    def test_offsets_locate_the_labeled_occurrence_and_reject_bad_annotations(self):
        m = self.module()
        text = 'Alpha abcd. Beta efgh. Alpha ijkl.'
        segments = m.segments(text)
        self.assertEqual(m.locate(text, 'Alpha', text.rindex('Alpha'), segments), 2)
        self.assertIsNone(m.locate(text, 'Alpha', 2, segments))
        self.assertIsNone(m.locate(text, 'abcd. Beta', 6, segments))

    def test_counts_match_existing_excess_support_and_lift_formulas(self):
        m = self.module()
        rows = [(str(i), {'p'}, {'r'}, {'s'}) for i in range(20)]
        rows += [(str(i+20), {'x'}, {'s'}, {'r'}) for i in range(180)]
        table, _ = m.count_table(rows)
        self.assertEqual(table['bridge']['p'], 'r:1.0000')
        literal, _ = m.count_table([(str(i), {'u'}, {'u'}, {'v'}) for i in range(3)])
        self.assertEqual(literal['delta']['u'], .6)

    def test_zero_mixture_keeps_the_original_tables_and_no_answers_are_stored(self):
        m = self.module()
        old = {'delta': {'x': .2}, 'rare_delta': .3, 'bridge': {'x': 'y:0.4'}, 'confidence': {'x': 1}}
        new = {'delta': {'z': .8}, 'rare_delta': .9, 'bridge': {'z': 'w:0.5'}}
        self.assertEqual(m.mix_tables(old, new, 0.), old)
        mixed = m.mix_tables(old, new, .5)
        self.assertEqual(set(mixed), set(old))
        self.assertAlmostEqual(mixed['delta']['x'], .55)
        self.assertAlmostEqual(mixed['delta']['z'], .55)


if __name__ == '__main__':
    unittest.main()

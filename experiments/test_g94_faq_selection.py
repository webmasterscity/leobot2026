import importlib
import unittest


class FAQSelectionTests(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g94_faq_selection')

    def test_rivals_exclude_duplicates_and_whole_word_containment(self):
        m = self.module()
        self.assertEqual(m.rivals('a b', ['a b', 'z a b', 'a b z', 'ab c', 'b a']), ['ab c', 'b a'])
        self.assertEqual(m.rivals('a b c', ['b', 'b c', 'd e']), ['d e'])

    def test_order_is_label_independent_and_label_follows_identity(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        reference = m.Components().bind(bot)
        answers = ['shared alpha.', 'shared bravo value.', 'shared charlie other second.',
                   'shared delta several different fields.', 'shared echo extra.',
                   'shared foxtrot content farther apart.']
        rows1, reason = m.exercise(bot, 'shared?', answers, 'shared alpha')
        self.assertIsNone(reason)
        rows2, reason = m.exercise(bot, 'shared?', list(reversed(answers)), 'shared alpha')
        self.assertIsNone(reason)
        self.assertEqual(rows1, rows2)
        self.assertEqual(sum(label for _, label in rows1['rows']), 1)
        rows3, reason = m.exercise(bot, 'shared?', answers, 'shared bravo value')
        self.assertIsNone(reason)
        self.assertEqual([f for f, _ in rows1['rows']], [f for f, _ in rows3['rows']])
        self.assertNotEqual([y for _, y in rows1['rows']], [y for _, y in rows3['rows']])
        reference.restore()

    def test_multiline_or_split_response_cannot_be_assigned_a_label(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        reference = m.Components().bind(bot)
        answers = ['shared alpha. Second clause.', 'shared bravo value.', 'shared charlie other second.',
                   'shared delta several different fields.', 'shared echo extra.',
                   'shared foxtrot content farther apart.']
        rows, reason = m.exercise(bot, 'shared?', answers, 'shared alpha second clause')
        self.assertIsNone(rows)
        self.assertEqual(reason, 'layout_changed')
        reference.restore()


if __name__ == '__main__':
    unittest.main()

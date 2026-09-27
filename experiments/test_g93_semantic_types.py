import importlib
import unittest


class SemanticTypeTests(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g93_semantic_types')

    def test_ambiguity_unknowns_and_opaque_class_names(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        classes, known = m.distribution(bot, 'aa aa bb zz', {'aa': ['x', 'y'], 'bb': ['y']})
        self.assertEqual(classes, {'x': .25, 'y': .75})
        self.assertEqual(known, 2/3)
        self.assertEqual(m.distribution(bot, 'zz', {'aa': ['x']}), ({}, 0.))
        changed, _ = m.distribution(bot, 'aa aa bb zz', {'aa': ['q', 'r'], 'bb': ['r']})
        self.assertEqual(changed, {'q': .25, 'r': .75})

    def test_counts_require_learned_support_and_clear_missing_question(self):
        m = self.module()
        from leobot import Bot
        from leobot.reading import KIND_SUPPORT
        bot = Bot()
        bot._kind_keys = lambda words: words[:1]
        table = {}
        for _ in range(KIND_SUPPORT-1):
            m.observe(table, ['u'], {'x': .25, 'y': .75})
        self.assertEqual(m.requested(bot, 'u?', table), {})
        m.observe(table, ['u'], {'x': .25, 'y': .75})
        self.assertEqual(m.requested(bot, 'u?', table), {'x': .25, 'y': .75})
        self.assertEqual(m.requested(bot, 'v?', table), {})

    def test_replacing_document_and_disabling_discards_old_information(self):
        m = self.module()
        from leobot import Bot
        from leobot.reading import KIND_SUPPORT
        bot = Bot()
        reference = m.Components().bind(bot)
        bot._kind_keys = lambda words: words[:1]
        bot.load_context('aa u.\nbb v.', '')
        original = bot.selection_candidates('u v?', 6)
        margins = bot._candidates.__func__.__globals__['SELECTION_MARGINS']
        binding = m.TypeBinding(bot, margins)
        self.assertEqual(original, bot.selection_candidates('u v?', 6))
        bot.context_model['semantic_types'] = {
            'mode': 'semantic', 'lexicon': {'aa': ['x']},
            'questions': {'u': {'n': KIND_SUPPORT, 'classes': {'x': KIND_SUPPORT}}}}
        def known():
            return [f['semantic_known'] for _, f in bot.selection_candidates('u v?', 6)]
        self.assertEqual(len(set(known())), 2)
        bot.load_context('zz u.\nyy v.', '')
        self.assertEqual(known(), ['0', '0'])
        bot.context_model.pop('semantic_types')
        self.assertTrue(all('semantic_known' not in f for _, f in bot.selection_candidates('u v?', 6)))
        binding.restore()
        reference.restore()


if __name__ == '__main__':
    unittest.main()

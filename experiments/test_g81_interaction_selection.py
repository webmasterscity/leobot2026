import importlib
from pathlib import Path
import tempfile
import unittest


class InteractionSelectionContract(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g81_interaction_selection')

    def turns(self):
        return [{'half': (i//4) % 2, 'rows': [({'x': str(i % 2), 'y': str((i//2) % 2)},
                                             int(i % 4 == 3))]} for i in range(320)]

    def test_combination_and_counterevidence_are_learned(self):
        m = self.module()
        turns = self.turns()
        model = m.fit_forest(turns, ['x', 'y'])
        values = [m.score_forest(model, {'x': str(i % 2), 'y': str(i//2)}) for i in range(4)]
        self.assertGreater(values[3], .8)
        self.assertTrue(all(p < .2 for p in values[:3]))
        reverse = [{**t, 'rows': [(f, 1-y) for f, y in t['rows']]} for t in turns]
        model = m.fit_forest(reverse, ['x', 'y'])
        self.assertLess(m.score_forest(model, {'x': '1', 'y': '1'}), .2)

    def test_candidate_count_reuses_same_cross_fits(self):
        m = self.module()
        components = m.Components()
        components.correct_calibration()
        ns, calls = components.learner, []
        def fitted(turns, names):
            calls.append(len(turns))
            return m.fit_forest(turns, names)
        ns['fit'], ns['score'] = fitted, m.score_forest
        cache = {}
        first = ns['selection'](self.turns(), ['x', 'y'], 6, cache, 'same')
        second = ns['selection'](self.turns(), ['x', 'y'], 1, cache, 'same')
        self.assertEqual(calls, [160, 160, 320])
        self.assertEqual(first['forest'], second['forest'])
        self.assertEqual(first['calibration'], second['calibration'])

    def test_saved_base_uses_learned_tree_and_restores_previous_scoring(self):
        m = self.module()
        from leobot import Bot
        components = m.Components()
        bot = Bot()
        reference = components.bind(bot)
        original_score = bot._selection_score
        binding = m.ForestBinding(bot)
        # A learned decision structure in serialized form, without lexical keys.
        bot.context_model['selection'] = {'k': 6, 'bias': 0., 'weights': {}, 'cite_from': .4,
            'calibration': [[0., .1, 50], [.5, .9, 50]],
            'forest': [{'rate': .5, 'n': 100, 'test': ['rango', '1'],
                        'yes': {'rate': .1, 'n': 50}, 'no': {'rate': .9, 'n': 50}}]}
        bot.load_context('u: 11.\nv: 22.', '')
        reply = bot.answer('u v?')
        self.assertIn('22', reply['text'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'base.json'
            bot.save(path)
            restored = Bot.load(path)
        reference2 = components.bind(restored)
        binding2 = m.ForestBinding(restored)
        self.assertEqual(reply, restored.answer('u v?'))
        binding2.restore()
        reference2.restore()
        binding.restore()
        self.assertEqual(original_score, bot._selection_score)
        reference.restore()


if __name__ == '__main__':
    unittest.main()

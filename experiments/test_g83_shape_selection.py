import importlib
from pathlib import Path
import tempfile
import unittest


class ShapeSelectionContract(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g83_shape_selection')

    def test_shape_evidence_changes_with_teaching_and_document_not_numeric_value(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        reference = m.Components().bind(bot)
        shapes = m.ShapeBinding(bot, m.shape_source()[0])
        def observed():
            return {bot.context_units[i]['text']: {k: v for k, v in f.items() if k.startswith('shape_')}
                    for i, f in bot.selection_candidates('u v?', 6)}
        bot.context_model['shape_evidence'] = {'u': [['#9:9', .7]]}
        bot.load_context('u: 11:20.\nv: 22.', '')
        first = list(observed().values())
        self.assertEqual([f['shape_explained'] for f in first], ['1', '0'])
        bot.load_context('u: 48:33.\nv: 97.', '')
        self.assertEqual(first, list(observed().values()))
        bot.context_model['shape_evidence'] = {'u': [['#9', .7]]}
        self.assertEqual([f['shape_explained'] for f in observed().values()], ['0', '1'])
        shapes.restore()
        reference.restore()

    def test_selector_persistence_and_feature_removal(self):
        m = self.module()
        from leobot import Bot
        components = m.Components()
        bot = Bot()
        reference = components.bind(bot)
        bot.load_context('u: 22.\nv: 11:20.', '')
        original = bot.selection_candidates('u v?', 6)
        shapes = m.ShapeBinding(bot, m.shape_source()[0])
        self.assertEqual(original, bot.selection_candidates('u v?', 6))
        bot.context_model['shape_evidence'] = {'u': [['#9:9', .7]]}
        bot.context_model['selection'] = {'k': 6, 'bias': -1., 'weights': {'shape_explained=1': 2.},
                                         'calibration': [[-9., .1, 30], [0., .9, 30]], 'cite_from': .4}
        reply = bot.answer('u v?')
        self.assertIn('11:20', reply['text'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'base.json'
            bot.save(path)
            restored = Bot.load(path)
        reference2 = components.bind(restored)
        shapes2 = m.ShapeBinding(restored, m.shape_source()[0])
        self.assertEqual(reply, restored.answer('u v?'))
        shapes2.restore()
        reference2.restore()
        shapes.restore()
        self.assertEqual(original, bot.selection_candidates('u v?', 6))
        reference.restore()


if __name__ == '__main__':
    unittest.main()

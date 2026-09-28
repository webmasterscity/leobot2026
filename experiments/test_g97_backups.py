import unittest
from types import SimpleNamespace


class BackupTests(unittest.TestCase):
    def test_only_abstentions_are_replaced_and_document_changes(self):
        from experiments.g97_backups import BackupBot
        class Original:
            context_units = [{'text': 'Dato primero.', 'heading': ''}]
            def answer(self, q, h=None):
                return {'status': 'unknown' if q == '?' else 'answered', 'text': 'original', 'evidence': None}
            def load_context(self, text, instructions=''):
                self.context_units = [{'text': text, 'heading': ''}]
        route = SimpleNamespace(prepare=lambda: None, propose=lambda q,h: {'index':0,'confidence':None})
        b = BackupBot(Original(), route, 'test')
        self.assertEqual(b.answer('known')['text'], 'original')
        self.assertEqual(b.answer('?')['evidence']['unit'], 'Dato primero.')
        b.load_context('Dato diferente.')
        self.assertEqual(b.answer('?')['evidence']['unit'], 'Dato diferente.')
        b.enabled = False
        self.assertEqual(b.answer('?')['text'], 'original')

    def test_rules_separate_opening_from_delivery_and_missing_services(self):
        from leobot import Bot
        from experiments.g97_backups import ManualRules
        bot = Bot()
        bot.load_context('Horario: lunes a viernes de 8:00 a 18:00.\n'
                         'Entregas: los pedidos se entregan de 10:00 a 12:00.\n'
                         'Dirección: Avenida Bosque 31, junto a la estación central.\n', '')
        r = ManualRules(bot); r.prepare()
        opening = r.propose('¿A qué hora abren?', [])
        self.assertIsNotNone(opening)
        self.assertIn('8:00', bot.context_units[opening['index']]['text'])
        self.assertIsNone(r.propose('¿Tienen estacionamiento?', []))
        self.assertIsNone(r.propose('¿Abren los domingos?', []))
        address = r.propose('¿Dónde quedan?', [])
        self.assertIn('Avenida Bosque', bot.context_units[address['index']]['text'])
        bot.load_context('Entregas: los pedidos se entregan de 10:00 a 12:00.', '')
        r.prepare()
        self.assertIsNone(r.propose('¿A qué hora abren?', []))

    def test_neural_features_keep_adjacent_order_and_safe_artifacts(self):
        from experiments.g97_neural import features, encode_numpy
        import numpy as np
        self.assertNotEqual(features(['a','b']), features(['b','a']))
        weights = {'embedding':np.array([[0.,0.],[1.,0.],[0.,1.]],dtype=np.float32),
                   'q_weight':np.eye(2,dtype=np.float32), 'q_bias':np.zeros(2,dtype=np.float32),
                   'a_weight':np.eye(2,dtype=np.float32), 'a_bias':np.zeros(2,dtype=np.float32)}
        self.assertTrue(np.allclose(encode_numpy([], weights, 'q'), [0.,0.]))
        left=encode_numpy([1,2],weights,'q')
        right=encode_numpy([2,1],weights,'a')
        self.assertTrue(np.allclose(left,right))
        self.assertAlmostEqual(float(np.linalg.norm(left)),1.,places=6)


if __name__ == '__main__': unittest.main()

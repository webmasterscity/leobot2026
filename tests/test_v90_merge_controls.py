"""Controls retained when the language, meta, and dialogue branches are unified."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot, ScalableBot


class MergeControlTests(unittest.TestCase):
    def test_raw_arity_limit_stops_new_high_arity_relation_after_restart(self):
        rows = [
            'ana mueve caja de casa a oficina',
            'bea mueve libro de plaza a tienda',
            'cora mueve mapa de cuarto a taller',
            'dora mueve carta de parque a banco',
        ]
        bot = Bot(raw_relation_max_arity=2)
        for row in rows[:3]:
            self.assertNotEqual(bot.respond(row)['status'], 'raw_relation_learned')
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / 'bot.json'
            bot.save(state)
            loaded = Bot.load(state)
            self.assertEqual(loaded.raw_relation_max_arity, 2)
            self.assertNotEqual(loaded.respond(rows[3])['status'], 'raw_relation_learned')

    def test_raw_arity_limit_also_applies_to_negative_evidence(self):
        bot = Bot(raw_relation_max_arity=2)
        rows = [
            'ana no mueve caja de casa a oficina',
            'bea no mueve libro de plaza a tienda',
            'cora no mueve mapa de cuarto a taller',
            'dora no mueve carta de parque a banco',
        ]
        for row in rows:
            self.assertNotEqual(bot.respond(row)['status'], 'raw_negative_relation_learned')

    def test_discourse_limit_and_raw_arity_survive_both_storage_modes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bot = Bot(raw_relation_max_arity=3)
            bot.discourse_max_referents = 4
            bot.discourse_referents = [{'surface': str(i)} for i in range(6)]
            state = root / 'bot.json'
            bot.save(state)
            loaded = Bot.load(state)
            self.assertEqual((loaded.raw_relation_max_arity, loaded.discourse_max_referents), (3, 4))
            self.assertEqual(len(loaded.discourse_referents), 4)

            disk = ScalableBot(root / 'facts.db', raw_relation_max_arity=3)
            disk.discourse_max_referents = 4
            disk.discourse_referents = [{'surface': str(i)} for i in range(6)]
            sidecar = root / 'sidecar.json'
            disk.save(sidecar)
            disk.close()
            restored = ScalableBot.load(sidecar, root / 'facts.db')
            try:
                self.assertEqual((restored.raw_relation_max_arity, restored.discourse_max_referents), (3, 4))
                self.assertEqual(len(restored.discourse_referents), 4)
            finally:
                restored.close()


if __name__ == '__main__':
    unittest.main()

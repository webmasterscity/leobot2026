import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class SequenceLearnerTests(unittest.TestCase):
    def test_learns_new_unary_and_binary_compositions_from_pairs(self):
        bot = Bot()
        for source, target in [('plum', 'P'), ('oat', 'O'), ('cedar', 'C'), ('mint', 'M'),
                               ('plum echo', 'P P'), ('oat echo', 'O O'),
                               ('mint echo', 'M M'),
                               ('plum then oat', 'P O'), ('oat then mint', 'O M'),
                               ('mint then plum', 'M P')]:
            bot.observe_sequence_example(source, target)
        report = bot.consolidate_sequence_learning()
        self.assertEqual(report['rules'], 2)
        self.assertEqual(bot.respond('cedar echo')['text'], 'C C')
        self.assertEqual(bot.respond('cedar then oat')['text'], 'C O')
        self.assertEqual(bot.respond('cedar echo then oat')['text'], 'C C O')

    def test_ablation_keeps_exact_memory_but_not_composition(self):
        bot = Bot()
        bot.sequence_learner.enable_composition = False
        for source, target in [('plum', 'P'), ('oat', 'O'), ('mint', 'M'),
                               ('plum echo', 'P P'), ('oat echo', 'O O'),
                               ('mint echo', 'M M')]:
            bot.observe_sequence_example(source, target)
        bot.consolidate_sequence_learning()
        self.assertEqual(bot.predict_sequence('plum echo')['status'], 'sequence_memory')
        self.assertEqual(bot.predict_sequence('cedar echo')['status'], 'sequence_unknown')

    def test_conflict_withdraws_rule_and_survives_restart(self):
        bot = Bot()
        for source, target in [('plum', 'P'), ('oat', 'O'), ('cedar', 'C'),
                               ('mint', 'M'), ('plum then oat', 'P O'),
                               ('oat then mint', 'O M'), ('mint then plum', 'M P')]:
            bot.observe_sequence_example(source, target)
        bot.consolidate_sequence_learning()
        self.assertEqual(bot.predict_sequence('cedar then oat')['status'], 'sequence_program')
        bot.observe_sequence_example('plum then oat', 'O P')
        bot.consolidate_sequence_learning()
        self.assertEqual(bot.predict_sequence('cedar then oat')['status'], 'sequence_unknown')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bot.json'
            bot.save(path)
            loaded = Bot.load(path)
            self.assertEqual(loaded.predict_sequence('cedar then oat')['status'], 'sequence_unknown')

    def test_sequence_state_persists_in_disk_backed_bot(self):
        with tempfile.TemporaryDirectory() as directory:
            db, state = Path(directory) / 'kb.sqlite', Path(directory) / 'state.json'
            bot = ScalableBot(db)
            for source, target in [('plum', 'P'), ('oat', 'O'), ('cedar', 'C'),
                                   ('mint', 'M'), ('plum echo', 'P P'),
                                   ('oat echo', 'O O'), ('mint echo', 'M M')]:
                bot.observe_sequence_example(source, target)
            bot.consolidate_sequence_learning()
            bot.save(state)
            bot.close()
            loaded = ScalableBot.load(state, db)
            try:
                self.assertEqual(loaded.predict_sequence('cedar echo')['output'], ['C', 'C'])
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

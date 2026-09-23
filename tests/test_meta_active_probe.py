"""A learned meta-program can request evidence that separates equivalent rules."""

import unittest
import tempfile
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController
from tests.test_meta_confounding import features, winner


def trained_controller():
    controller = MetaController()
    for index in range(64):
        target = winner(index)
        for strategy in ('A', 'B'):
            controller.observe('ambiguous', features(index), strategy,
                               success=strategy == target,
                               cost=1 if strategy == target else 9,
                               failure_budget=2)
    return controller


class MetaActiveProbeTests(unittest.TestCase):
    def test_requests_discriminating_experience_without_recording_an_outcome(self):
        controller = trained_controller()
        self.assertEqual(controller.invented_views['ambiguous']['program_size'], 3)
        candidates = [
            {'features': features(100), 'cost': 1},
            {'features': features(100, reverse_proxy=True), 'cost': 1},
        ]
        before = controller.as_dict()
        proposal = controller.propose_meta_probe('ambiguous', candidates)
        self.assertEqual(proposal['status'], 'epistemic_action')
        self.assertEqual(proposal['chosen_index'], 1)
        self.assertGreater(proposal['ambiguous_hypotheses'], 1)
        self.assertEqual(controller.as_dict(), before)

        restored = MetaController.from_dict(before)
        self.assertEqual(restored.propose_meta_probe('ambiguous', candidates)['chosen_index'], 1)
        self.assertEqual(restored.as_dict(), before)

        with tempfile.TemporaryDirectory() as directory:
            bot = Bot()
            bot.meta_controller = controller
            state = Path(directory) / 'bot.json'
            bot.save(state)
            loaded = Bot.load(state)
            self.assertEqual(loaded.meta_controller.propose_meta_probe(
                'ambiguous', candidates)['chosen_index'], 1)

    def test_reports_when_no_offered_experience_can_separate_rules(self):
        controller = trained_controller()
        proposal = controller.propose_meta_probe(
            'ambiguous', [{'features': features(100), 'cost': 1}])
        self.assertEqual(proposal['status'], 'no_epistemic_action')
        self.assertEqual(proposal['reason'], 'no_discriminating_action')

    def test_one_counterexample_does_not_end_the_request_for_evidence(self):
        controller = trained_controller()
        target = winner(100)
        for strategy in ('A', 'B'):
            controller.observe('ambiguous', features(100, reverse_proxy=True),
                               strategy, success=strategy == target,
                               cost=1 if strategy == target else 9,
                               failure_budget=2)
        proposal = controller.propose_meta_probe('ambiguous', [
            {'features': features(101), 'cost': 1},
            {'features': features(101, reverse_proxy=True), 'cost': 1},
        ])
        self.assertEqual(proposal['status'], 'epistemic_action')
        self.assertEqual(proposal['chosen_index'], 1)

    def test_two_selected_trials_change_transfer_but_passive_trials_do_not(self):
        active = trained_controller()
        passive = MetaController.from_dict(active.as_dict())
        for index in (100, 101):
            options = [
                {'features': features(index), 'cost': 1},
                {'features': features(index, reverse_proxy=True), 'cost': 1},
            ]
            proposal = active.propose_meta_probe('ambiguous', options)
            self.assertEqual(proposal['chosen_index'], 1)
            for controller, vector in ((active, options[1]['features']),
                                       (passive, options[0]['features'])):
                for strategy in ('A', 'B'):
                    controller.observe('ambiguous', vector, strategy,
                                       success=strategy == winner(index),
                                       cost=1 if strategy == winner(index) else 9,
                                       failure_budget=2)
        heldout = range(200, 296)
        active_correct = sum(
            active.rank('ambiguous', features(i, reverse_proxy=True),
                        ('A', 'B'))['order'][0] == winner(i) for i in heldout)
        passive_correct = sum(
            passive.rank('ambiguous', features(i, reverse_proxy=True),
                         ('A', 'B'))['order'][0] == winner(i) for i in heldout)
        self.assertGreaterEqual(active_correct, 90)
        self.assertLessEqual(passive_correct, 6)


if __name__ == '__main__':
    unittest.main()

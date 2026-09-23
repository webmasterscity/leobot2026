"""Feature-order regression for bounded meta-program acquisition."""

import random
import time
import unittest

from experiments.meta_feature_order_probe import make_rows
from leobot.metacontrol import MetaController


def _features(relevant, distractors, order):
    if order == 'last':
        return tuple(distractors + relevant)
    if order == 'reverse':
        return tuple(reversed(relevant + distractors))
    return tuple(relevant + distractors)


def _heldout_score(controller, order):
    rng = random.Random(9461)
    correct = 0
    for i in range(96):
        bits = [(i >> k) & 1 for k in range(3)]
        centers = [-9_000_000.0 + i * 211.0, 7_000_000.0 + i * 307.0,
                   90_000_000.0 + i * 401.0]
        relevant = []
        for bit, center, delta in zip(bits, centers, (2.0, 4.0, 6.0)):
            relevant.extend((center + delta, center - delta) if bit
                            else (center - delta, center + delta))
        distractors = [rng.uniform(-1e9, 1e9) for _ in range(10)]
        winner = 'A' if bits[0] ^ bits[1] ^ bits[2] else 'B'
        route = controller.rank('feature_order',
                                _features(relevant, distractors, order),
                                ('A', 'B'))
        correct += route['order'][0] == winner
    return correct / 96


class MetaFeatureOrderTests(unittest.TestCase):
    def test_same_evidence_learns_in_both_feature_orders(self):
        rows = make_rows()
        metrics = {}
        for order in ('first', 'last', 'reverse'):
            controller = MetaController()
            start = time.perf_counter()
            cpu_start = time.process_time()
            for relevant, distractors, winner in rows:
                features = _features(relevant, distractors, order)
                for strategy in ('A', 'B'):
                    controller.observe('feature_order', features, strategy,
                                       success=strategy == winner,
                                       cost=1 if strategy == winner else 9,
                                       failure_budget=2)
            elapsed = time.perf_counter() - start
            cpu = time.process_time() - cpu_start
            view = controller.invented_views.get('feature_order')
            metrics[order] = {
                'acquisition_s': round(elapsed, 3),
                'cpu_s': round(cpu, 3),
                'program_size': view.get('program_size') if view else None,
                'heldout': _heldout_score(controller, order),
            }
        print('meta feature order:', metrics)
        for result in metrics.values():
            self.assertEqual(result['program_size'], 3)
            self.assertGreaterEqual(result['heldout'], 0.95)

    def test_opposing_temporal_regimes_do_not_promote_a_program(self):
        rows = make_rows()
        tasks = []
        for i, (relevant, distractors, winner) in enumerate(rows):
            if i >= len(rows) // 2:
                winner = 'B' if winner == 'A' else 'A'
            tasks.append({'features': _features(relevant, distractors, 'last'),
                          'winner': winner})
        controller = MetaController()
        report = controller._invent_meta_program_from_tasks(
            'opposing_regimes', tasks, force=True)
        self.assertEqual(report['status'], 'meta_program_rejected')
        self.assertNotIn('opposing_regimes', controller.invented_views)


if __name__ == '__main__':
    unittest.main()

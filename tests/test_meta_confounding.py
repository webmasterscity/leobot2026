"""Known limit: observationally identical signals need discriminating evidence."""

import unittest

from leobot.metacontrol import MetaController


def features(index, reverse_proxy=False):
    bits = [(index >> position) & 1 for position in range(3)]
    relevant = []
    proxy = []
    for position, bit in enumerate(bits):
        center = 10 ** (position + 3) * (1 + index / 10)
        delta = (3.0, 5.0, 7.0)[position]
        relevant.extend((center + delta, center - delta) if bit
                        else (center - delta, center + delta))
        proxy_center = 1e8 * (position + 1) + index * 100000
        proxy_bit = bit ^ int(reverse_proxy)
        proxy.extend((proxy_center + 0.01, proxy_center - 0.01)
                     if proxy_bit else (proxy_center - 0.01, proxy_center + 0.01))
    return relevant + proxy


def winner(index):
    bits = [(index >> position) & 1 for position in range(3)]
    return 'A' if bits[0] ^ bits[1] ^ bits[2] else 'B'


class MetaConfoundingDiagnosis(unittest.TestCase):
    @unittest.expectedFailure
    def test_perfect_proxy_requires_new_evidence_to_transfer(self):
        controller = MetaController()
        for index in range(64):
            target = winner(index)
            for strategy in ('A', 'B'):
                controller.observe('confound', features(index), strategy,
                                   success=strategy == target,
                                   cost=1 if strategy == target else 9,
                                   failure_budget=2)
        self.assertEqual(controller.invented_views['confound']['program_size'], 3)
        correct = sum(
            controller.rank('confound', features(index, reverse_proxy=True),
                            ('A', 'B'))['order'][0] == winner(index)
            for index in range(100, 196)
        )
        # The current method chooses the proxy and obtains 0/96. Passing this
        # test requires an actual experience where proxy and target disagree.
        self.assertGreaterEqual(correct, 90)


if __name__ == '__main__':
    unittest.main()

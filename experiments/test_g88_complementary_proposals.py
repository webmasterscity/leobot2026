import unittest
from types import SimpleNamespace
from unittest.mock import patch

from experiments.g88_complementary_proposals import ProposalBinding, proposal_order


class ProposalTests(unittest.TestCase):
    def test_original_prefix_and_scores_are_preserved(self):
        scored = {'order': [(10.-i, i) for i in range(8)], 'base': -4., 'how': {}, 'asked': None}
        units = [{'kind': 'line'} for _ in range(10)]
        result = proposal_order(scored, list(range(10)), units)
        self.assertEqual(result['order'][:6], scored['order'][:6])
        self.assertEqual(result['order'][6:], [(-4., 9), (-4., 8), (3., 7), (4., 6)])
        self.assertEqual(len(result['order']), len({i for _, i in result['order']}))
        self.assertIs(result['how'], scored['how'])
        self.assertEqual(len(scored['order']), 8)

    def test_replace_context_and_disable(self):
        original = lambda terms, question='': {'order': [(1., 0)], 'base': -2., 'how': {}, 'asked': None}
        bot = SimpleNamespace(context_model={'proposal': {'mode': 'shuffled', 'permutation': [1, 0]}},
                              context_units=[{'kind': 'line'}], _scored=original)
        direct = SimpleNamespace(prepare=lambda: True, decoded=[({'ignored': True}, [])], prepared=[[0]])
        binding = ProposalBinding(bot, direct)
        with patch('experiments.g88_complementary_proposals.g65.alignment_scores', return_value=[0.]) as scorer:
            bot._scored(['q'])
            self.assertEqual(scorer.call_args.args[1], [[1]])
            bot.context_units = [{'kind': 'line'}]
            direct.prepared = [[1]]
            bot._scored(['q'])
            self.assertEqual(scorer.call_args.args[1], [[0]])
        bot.context_model = {}
        self.assertEqual(bot._scored(['q']), original(['q']))
        binding.restore()
        self.assertIs(bot._scored, original)


if __name__ == '__main__':
    unittest.main()

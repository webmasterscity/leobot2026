import unittest
import numpy as np


class ContextTests(unittest.TestCase):
    def setUp(self):
        import torch
        torch.set_num_threads(1)
        torch.manual_seed(1)
        rng = np.random.default_rng(1)
        self.initial = {'embedding': rng.normal(size=(9, 64)).astype('float32')}
        self.initial['embedding'][0] = 0
        for side in ('q', 'a'):
            self.initial[side+'_weight'] = np.eye(64, dtype='float32')
            self.initial[side+'_bias'] = np.zeros(64, dtype='float32')

    def test_numpy_export_and_mask_preserve_padding_and_empty_sequences(self):
        import torch
        from experiments.g102_training import ContextModel
        from experiments.g102_context import encode_numpy
        for width in (1, 3):
            model = ContextModel(self.initial, width)
            ids = torch.tensor([[1, 0, 2, 0], [0, 0, 0, 0]])
            for side in ('q', 'a'):
                expected = model.encode(ids, side).detach().numpy()
                actual = encode_numpy(ids.numpy(), model.export(), side)
                np.testing.assert_allclose(actual, expected, atol=1e-5)
                np.testing.assert_array_equal(actual[ids.numpy() == 0], 0)
                alone = model.encode(ids[:1, :3], side).detach().numpy()
                np.testing.assert_allclose(alone, actual[:1, :3], atol=1e-5)

    def test_context_depends_on_neighbors_and_width1_is_permutation_equivariant(self):
        import torch
        from experiments.g102_training import ContextModel
        ids = torch.tensor([[1, 2, 3]])
        for width in (1, 3):
            model = ContextModel(self.initial, width)
            left = model.encode(ids, 'q').detach().numpy()
            right = model.encode(ids.flip(1), 'q').detach().numpy()[:, ::-1]
            if width == 1:
                np.testing.assert_allclose(left, right, atol=1e-6)
            else:
                self.assertGreater(float(np.max(np.abs(left-right))), 1e-3)

    def test_scores_export_with_unknown_tokens_and_backward_is_finite(self):
        import torch
        from experiments.g102_training import ContextModel
        from experiments.g102_context import score_numpy
        from experiments.g99_training import decision_loss
        model = ContextModel(self.initial, 3)
        q = torch.tensor([[1, 0, 2], [0, 0, 0]])
        a = torch.tensor([[[3, 4, 0], [0, 0, 0]], [[1, 0, 0], [0, 0, 0]]])
        lexical = torch.zeros((2, 2, 13))
        result = model(q, a, lexical)
        w = model.export()
        for i in range(2):
            actual = score_numpy(q[i].numpy(), a[i].numpy(), lexical[i].numpy(), w)
            np.testing.assert_allclose(actual, result[i].detach().numpy(), atol=1e-5)
        loss = decision_loss(result, torch.tensor([[True, False, False], [False, False, True]]),
                             torch.ones((2, 2), dtype=torch.bool))
        loss.backward()
        for parameter in model.parameters():
            self.assertIsNotNone(parameter.grad)
            self.assertTrue(torch.isfinite(parameter.grad).all())
        self.assertGreater(float(model.embedding.weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.layers[0].weight.grad.abs().sum()), 0)


if __name__ == '__main__':
    unittest.main()

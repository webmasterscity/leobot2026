import unittest
import numpy as np


class TrainingTests(unittest.TestCase):
    def test_document_split_does_not_depend_on_question(self):
        from experiments.g98_training import partition
        groups = [f'document-{i}' for i in range(100)]
        a = {g for g in groups if partition(g) == 'train'}
        b = {g for g in groups if partition(g) == 'validation'}
        c = {g for g in groups if partition(g) == 'calibration'}
        self.assertFalse(a & b or a & c or b & c)
        self.assertEqual(a | b | c, set(groups))

    def test_training_learns_evidence_and_missing_answer_and_exports(self):
        import torch
        from experiments.g98_training import Encoder, tensor, selection_loss
        from experiments.g97_neural import encode_numpy
        torch.set_num_threads(1)
        torch.manual_seed(8)
        model = Encoder(7)
        opt = torch.optim.AdamW(model.parameters(), lr=.02)
        # One question has two valid units; another has no answer in those units.
        queries = tensor([[1], [2]])
        answers = tensor([[3], [4], [3], [4]])
        valid = torch.ones((2, 2), dtype=torch.bool)
        targets = torch.tensor([[True, True, False], [False, False, True]])
        for _ in range(45):
            q, a = model(queries, 'q'), model(answers, 'a').reshape(2, 2, 64)
            logits = torch.cat(((a*q[:, None]).sum(2)/.1, model.null(q)), 1)
            loss = selection_loss(logits, targets, valid)
            opt.zero_grad(); loss.backward(); opt.step()
        self.assertLess(float(loss.detach()), .02)
        choices = logits.detach().argmax(1).tolist()
        self.assertIn(choices[0], [0, 1]); self.assertEqual(choices[1], 2)
        weights = model.export()
        self.assertTrue(np.allclose(encode_numpy([1], weights, 'q'), q[0].detach().numpy(), atol=.02))
        with torch.no_grad(): latest = model(queries, 'q').numpy()
        self.assertTrue(np.allclose(encode_numpy([1], weights, 'q'), latest[0], atol=1e-5))

    def test_padding_cannot_be_chosen_and_multiple_positives_share_loss(self):
        import torch
        from experiments.g98_training import selection_loss
        logits = torch.tensor([[2., 2., 99., -2.]], requires_grad=True)
        positives = torch.tensor([[True, True, False, False]])
        valid = torch.tensor([[True, True, False]])
        loss = selection_loss(logits, positives, valid)
        self.assertLess(float(loss.detach()), .02)
        loss.backward()
        self.assertEqual(float(logits.grad[0, 2]), 0.)


if __name__ == '__main__': unittest.main()

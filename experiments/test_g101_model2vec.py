import unittest
import numpy as np


class Model2VecTests(unittest.TestCase):
    def test_relative_features_are_equivariant_to_candidate_order(self):
        from experiments.g101_model2vec import combine
        lexical=np.arange(39,dtype=np.float32).reshape(3,13);scores=np.array([.2,.8,.1])
        a=combine(lexical,scores);order=[2,0,1]
        b=combine(lexical[order],scores[order])
        self.assertTrue(np.allclose(a[order],b))
        self.assertTrue(np.allclose(a[:,14],[-.6,.6,-.7]))
        self.assertEqual(combine(np.zeros((0,13)),np.zeros(0)).shape,(0,16))

    def test_similarity_is_not_reported_as_confidence(self):
        from experiments.g101_model2vec import admit
        raw={'index':2,'score':.97}
        self.assertIsNone(admit(raw,[[1.,.2,40]],.4))
        result=admit(raw,[[1.,.91,40]],.9)
        self.assertEqual(result,{'index':2,'confidence':.91})
        self.assertIsNone(admit({'index':2,'score':-.1},[[1.,.99,40]],.9))


if __name__=='__main__':unittest.main()

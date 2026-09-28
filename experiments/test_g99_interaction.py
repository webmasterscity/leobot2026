import unittest
import numpy as np


class InteractionTests(unittest.TestCase):
    def test_unknown_words_keep_exact_identity_and_history_is_separate(self):
        from leobot import Bot
        from experiments.g99_interaction import PairFeatures, LEXICAL
        rng = np.random.default_rng(1)
        w = {'embedding':rng.normal(size=(3,64)).astype('float32')}
        for side in ('q','a'):
            w[side+'_weight']=np.eye(64,dtype='float32');w[side+'_bias']=np.zeros(64,dtype='float32')
        f=PairFeatures(Bot(),{'uno':1,'dos':2},w)
        units=f.prepare(['nefro42 uno','xeno77 dos'])
        a=f.matrix('nefro42','',units);b=f.matrix('nefro42','dos',units)
        self.assertGreater(a[0,2],a[1,2])
        self.assertTrue(np.array_equal(a[:,:f.width],b[:,:f.width]))
        self.assertFalse(np.array_equal(a[:,f.width:],b[:,f.width:]))
        self.assertGreater(f.width,LEXICAL)
        self.assertTrue(np.isfinite(a).all())

    def test_small_decision_network_learns_choice_and_absence(self):
        import torch
        from experiments.g99_training import Decision, decision_loss
        torch.set_num_threads(1);torch.manual_seed(1)
        model=Decision(2);opt=torch.optim.AdamW(model.parameters(),lr=.02)
        x=torch.tensor([[[1.,0.],[0.,1.]],[[0.,-1.],[-1.,0.]]])
        valid=torch.ones((2,2),dtype=torch.bool)
        target=torch.tensor([[True,False,False],[False,False,True]])
        for _ in range(70):
            logits=model(x);loss=decision_loss(logits,target,valid)
            opt.zero_grad();loss.backward();opt.step()
        chosen=torch.cat((model(x),torch.zeros((2,1))),1).argmax(1).tolist()
        self.assertEqual(chosen,[0,2])
        weights=model.export()
        y=np.tanh(x.numpy()@weights['w1']+weights['b1'])@weights['w2']+weights['b2']
        self.assertTrue(np.allclose(y[...,0],model(x).detach().numpy(),atol=1e-5))

    def test_empty_vectors_and_replacing_prepared_units(self):
        from leobot import Bot
        from experiments.g99_interaction import PairFeatures
        w={'embedding':np.zeros((1,64),dtype='float32')}
        for s in ('q','a'):
            w[s+'_weight']=np.eye(64,dtype='float32');w[s+'_bias']=np.zeros(64,dtype='float32')
        f=PairFeatures(Bot(),{},w)
        first=f.prepare(['antiguo']);second=f.prepare(['nuevo','distinto'])
        self.assertEqual(f.matrix('nuevo','',first).shape[0],1)
        self.assertEqual(f.matrix('nuevo','',second).shape[0],2)
        self.assertEqual(f.matrix('nuevo','',[]).shape,(0,2*f.width))
        self.assertTrue(np.isfinite(f.matrix('','',second)).all())


if __name__=='__main__':unittest.main()

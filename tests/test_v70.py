import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


class V70VariableDepthMetaProgramTests(unittest.TestCase):
    @staticmethod
    def train_parity3(controller: MetaController, family='parity3', reverse=False, n=64):
        for i in range(n):
            bits=[(i>>k)&1 for k in range(3)]
            centers=[10_000.0+i*17.0,1_000_000.0+i*31.0,100_000_000.0+i*43.0]
            features=[]
            for bit,center,delta in zip(bits,centers,(3.0,5.0,7.0)):
                features.extend((center+delta,center-delta) if bit else (center-delta,center+delta))
            winner='A' if (bits[0]^bits[1]^bits[2]) else 'B'
            if reverse:
                winner='B' if winner=='A' else 'A'
            for strategy in ('A','B'):
                controller.observe(family,features,strategy,success=(strategy==winner),
                                   cost=(1 if strategy==winner else 9),failure_budget=2)

    @staticmethod
    def heldout(controller: MetaController, family='parity3', count=200):
        correct=0
        for i in range(count):
            bits=[(i>>k)&1 for k in range(3)]
            centers=[-9_000_000.0+i*211.0,7_000_000.0+i*307.0,90_000_000.0+i*401.0]
            features=[]
            for bit,center,delta in zip(bits,centers,(2.0,4.0,6.0)):
                features.extend((center+delta,center-delta) if bit else (center-delta,center+delta))
            expected='A' if (bits[0]^bits[1]^bits[2]) else 'B'
            route=controller.rank(family,features,['A','B'])
            correct+=int(route['order'][0]==expected)
        return correct

    def test_three_predicate_program_solves_family_that_two_cannot(self):
        m=MetaController(); self.train_parity3(m)
        view=m.invented_views.get('parity3')
        self.assertIsNotNone(view)
        self.assertEqual(view['kind'],'feature_program')
        self.assertEqual(view['program_size'],3)
        self.assertEqual(view['accuracy'],1.0)
        self.assertEqual(self.heldout(m),200)
        tasks=m._meta_tasks('parity3')
        m.invented_views.pop('parity3',None)
        bounded=m._invent_meta_program_from_tasks('parity3',tasks,max_program_size=2,force=True)
        self.assertEqual(bounded['status'],'meta_program_rejected')

    def test_minimal_program_is_preferred_when_two_predicates_are_enough(self):
        m=MetaController()
        for i in range(40):
            left=i%2; right=(i//2)%2
            c1=1000.0+i*11; c2=100_000.0+i*13
            f=(c1+2,c1-2,c2+3,c2-3) if left and right else None
            f0,f1=((c1+2,c1-2) if left else (c1-2,c1+2))
            f2,f3=((c2+3,c2-3) if right else (c2-3,c2+3))
            winner='A' if bool(left)^bool(right) else 'B'
            for strategy in ('A','B'):
                m.observe('parity2_min',(f0,f1,f2,f3),strategy,success=(strategy==winner),
                          cost=(1 if strategy==winner else 9),failure_budget=2)
        self.assertEqual(m.invented_views['parity2_min']['program_size'],2)

    def test_three_predicate_program_persists(self):
        bot=Bot(); self.train_parity3(bot.meta_controller)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
        self.assertEqual(loaded.meta_controller.invented_views['parity3']['program_size'],3)
        self.assertEqual(self.heldout(loaded.meta_controller,count=80),80)

    def test_size_limit_does_not_return_an_already_learned_larger_program(self):
        m=MetaController(); self.train_parity3(m)
        self.assertEqual(m.invented_views['parity3']['program_size'],3)
        limited=m._invent_meta_program_from_tasks(
            'parity3',m._meta_tasks('parity3'),max_program_size=2,force=True)
        self.assertNotEqual(limited.get('status'),'meta_program_invented')
        self.assertLessEqual(limited.get('program_size',2),2)

    def test_contradictory_regime_withdraws_depth_three_program(self):
        m=MetaController(); self.train_parity3(m,'shift3')
        self.assertEqual(m.invented_views['shift3']['program_size'],3)
        self.train_parity3(m,'shift3',reverse=True)
        self.assertIsNone(m.invented_views.get('shift3'))

    def test_noise_does_not_require_inventing_a_depth_three_program(self):
        m=MetaController()
        for i in range(64):
            features=(float(i*17+1),float(i*23+2),float(i*31+3),
                      float(i*43+4),float(i*53+5),float(i*61+6))
            winner='A' if ((i*1664525+1013904223)>>7)&1 else 'B'
            for strategy in ('A','B'):
                m.observe('noise70',features,strategy,success=(strategy==winner),
                          cost=(1 if strategy==winner else 8),failure_budget=2)
        view=m.invented_views.get('noise70')
        if view is not None:
            self.assertGreaterEqual(view.get('accuracy',0.0),0.85)
            self.assertGreaterEqual(view.get('coverage',0.0),0.60)
            self.assertGreaterEqual(view.get('gain_over_majority',0.0),0.10)


if __name__=='__main__':
    unittest.main()

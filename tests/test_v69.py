import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


class V69MetaProgramTests(unittest.TestCase):
    @staticmethod
    def train_parity(controller: MetaController, family='parity', reverse=False):
        # No single observable predicts the winner.  The reusable rule depends on
        # the joint truth of two independent ordering relations.  Absolute values
        # are unique and cross-pair orderings are constant, so V6.8 single-atom
        # transforms cannot solve the family.
        for i in range(32):
            left=(i >> 0) & 1
            right=(i >> 1) & 1
            c1=10_000.0 + i*101.0
            c2=1_000_000.0 + i*137.0
            f0,f1=((c1+4,c1-4) if left else (c1-4,c1+4))
            f2,f3=((c2+7,c2-7) if right else (c2-7,c2+7))
            features=(f0,f1,f2,f3)
            winner='A' if bool(left) ^ bool(right) else 'B'
            if reverse:
                winner='B' if winner=='A' else 'A'
            for strategy in ('A','B'):
                controller.observe(family,features,strategy,
                                   success=(strategy==winner),
                                   cost=(1 if strategy==winner else 9),
                                   failure_budget=2)

    def test_synthesizes_composed_meta_program_when_single_atoms_fail(self):
        m=MetaController(); self.train_parity(m)
        view=m.invented_views.get('parity')
        self.assertIsNotNone(view)
        self.assertEqual(view['kind'],'feature_program')
        self.assertEqual(view['program_size'],2)
        self.assertEqual(view['accuracy'],1.0)
        self.assertEqual(view['coverage'],1.0)
        self.assertGreaterEqual(len(view['buckets']),4)

    def test_composed_program_generalizes_to_unseen_magnitudes(self):
        m=MetaController(); self.train_parity(m)
        for i in range(40):
            left=i%2; right=(i//2)%2
            c1=-9_000_000.0+i*211.0; c2=7_000_000.0+i*307.0
            f0,f1=((c1+3,c1-3) if left else (c1-3,c1+3))
            f2,f3=((c2+5,c2-5) if right else (c2-5,c2+5))
            expected='A' if bool(left)^bool(right) else 'B'
            route=m.rank('parity',(f0,f1,f2,f3),['A','B'])
            self.assertEqual(route['mode'],'invented_view')
            self.assertEqual(route['view']['kind'],'feature_program')
            self.assertEqual(route['order'][0],expected)

    def test_composed_program_persists(self):
        bot=Bot(); self.train_parity(bot.meta_controller)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
        self.assertEqual(loaded.meta_controller.invented_views['parity']['kind'],'feature_program')
        route=loaded.meta_controller.rank('parity',(-5,5,20,10),['A','B'])
        self.assertEqual(route['order'][0],'A')

    def test_contradictory_regime_withdraws_program(self):
        m=MetaController(); self.train_parity(m,'shift')
        self.assertEqual(m.invented_views['shift']['kind'],'feature_program')
        self.train_parity(m,'shift',reverse=True)
        self.assertIsNone(m.invented_views.get('shift'))

    def test_random_labels_do_not_force_program(self):
        m=MetaController()
        for i in range(36):
            features=(float(i*17+1),float(i*23+2),float(i*31+3),float(i*43+4))
            # Pseudorandom-looking deterministic labels unrelated to bounded DSL.
            winner='A' if ((i*1103515245+12345) >> 5) & 1 else 'B'
            for strategy in ('A','B'):
                m.observe('noise69',features,strategy,success=(strategy==winner),
                          cost=(1 if strategy==winner else 8),failure_budget=2)
        view=m.invented_views.get('noise69')
        if view is not None:
            self.assertGreaterEqual(view['accuracy'],0.85)
            self.assertGreaterEqual(view['coverage'],0.60)
            self.assertGreaterEqual(view['gain_over_majority'],0.10)


if __name__=='__main__':
    unittest.main()

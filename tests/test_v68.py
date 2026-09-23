import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


class V68MetaDSLTests(unittest.TestCase):
    @staticmethod
    def train_order_relation(controller: MetaController, family='representation', reverse=False):
        # Absolute values and nuisance dimensions are unique per task, so V6.7
        # raw projections cannot obtain leave-one-task-out neighbors.  Only the
        # relation between feature 0 and feature 1 is reusable.
        for i in range(24):
            if i % 2 == 0:
                a,b=10*i+1,10*i+8
            else:
                a,b=10*i+9,10*i+2
            features=(float(a),float(b),1000.0+i*7.0,2000.0+i*11.0)
            winner='LOW' if a<b else 'HIGH'
            if reverse:
                winner='HIGH' if winner=='LOW' else 'LOW'
            for strategy in ('LOW','HIGH'):
                controller.observe(family,features,strategy,
                                   success=(strategy==winner),
                                   cost=(1 if strategy==winner else 9),
                                   failure_budget=2)

    def test_invents_relational_observable_after_raw_projection_fails(self):
        m=MetaController(); self.train_order_relation(m)
        view=m.invented_views.get('representation')
        self.assertIsNotNone(view)
        self.assertEqual(view['kind'],'feature_transform')
        self.assertEqual(view['atoms'],[{'op':'cmp','a':0,'b':1}])
        self.assertEqual(view['accuracy'],1.0)
        self.assertEqual(view['coverage'],1.0)

    def test_relational_observable_generalizes_to_unseen_magnitudes_and_shifts(self):
        m=MetaController(); self.train_order_relation(m)
        cases=[
            ((100.0,999.0,3333.3,4444.4),'LOW'),
            ((900.0,12.0,7777.7,8888.8),'HIGH'),
            ((-50.0,-2.0,0.11,0.22),'LOW'),
            ((500000.0,499999.0,0.33,0.44),'HIGH'),
        ]
        for features,winner in cases:
            route=m.rank('representation',features,['LOW','HIGH'])
            self.assertEqual(route['mode'],'invented_view')
            self.assertEqual(route['order'][0],winner)
            self.assertEqual(route['view']['kind'],'feature_transform')

    def test_relational_observable_persists_at_bot_level(self):
        bot=Bot(); self.train_order_relation(bot.meta_controller)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
        view=loaded.meta_controller.invented_views['representation']
        self.assertEqual(view['kind'],'feature_transform')
        route=loaded.meta_controller.rank('representation',(2.0,9.0,.123,.987),['LOW','HIGH'])
        self.assertEqual(route['order'][0],'LOW')

    def test_regime_reversal_withdraws_relational_observable(self):
        m=MetaController(); self.train_order_relation(m,'x')
        self.assertEqual(m.invented_views['x']['kind'],'feature_transform')
        self.train_order_relation(m,'x',reverse=True)
        self.assertIsNone(m.invented_views.get('x'))

    @staticmethod
    def train_delta_threshold(controller: MetaController, family='delta'):
        # Every center contains all outcome classes, defeating raw-value thresholds.
        # The reusable invariant is the learned signed difference boundary.
        for i in range(8):
            center=100.0 + i*37.0
            for j,delta in enumerate((-0.4,0.1,0.4)):
                a=center + delta/2.0; b=center-delta/2.0
                features=(a,b,5000.0+i*13+j,9000.0+i*17+j)
                winner='A' if delta>0.25 else 'B'
                for strategy in ('A','B'):
                    controller.observe(family,features,strategy,success=(strategy==winner),
                                       cost=(1 if strategy==winner else 11),failure_budget=2)

    def test_invents_fitted_difference_boundary_not_raw_value_rule(self):
        m=MetaController(); self.train_delta_threshold(m)
        view=m.invented_views.get('delta')
        self.assertIsNotNone(view)
        self.assertEqual(view['kind'],'feature_transform')
        atom=view['atoms'][0]
        self.assertEqual(atom['op'],'delta_gt')
        self.assertEqual((atom['a'],atom['b']),(0,1))
        self.assertAlmostEqual(atom['threshold'],0.25,places=9)
        for center,delta,winner in ((-10000.0,.7,'A'),(123456.0,.02,'B'),(77.0,-3.0,'B')):
            f=(center+delta/2,center-delta/2,.345,.678)
            route=m.rank('delta',f,['A','B'])
            self.assertEqual(route['mode'],'invented_view')
            self.assertEqual(route['order'][0],winner)

    def test_noise_does_not_force_transform_invention(self):
        m=MetaController()
        for i in range(24):
            features=(float(i*3+1),float(i*5+2),float(i*7+3),float(i*11+4))
            # Deterministic but intentionally unrelated to any pair ordering.
            winner='A' if (i % 4) in (0,1) else 'B'
            for strategy in ('A','B'):
                m.observe('noise',features,strategy,success=(strategy==winner),
                          cost=(1 if strategy==winner else 7),failure_budget=2)
        view=m.invented_views.get('noise')
        if view is not None:
            # A promoted view must have met the same strict validation; this
            # guard prevents silently accepting a low-quality accidental rule.
            self.assertGreaterEqual(view['accuracy'],0.85)
            self.assertGreaterEqual(view['coverage'],0.60)
            self.assertGreaterEqual(view['gain_over_majority'],0.10)


if __name__=='__main__':
    unittest.main()

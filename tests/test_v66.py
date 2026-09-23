import json
import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController
from experiments.v65_meta_controller_experiment import train_pair_cardinality_prior


class V66AIKRActiveInferenceTests(unittest.TestCase):
    def test_aikr_budget_adapts_to_regime_shift_before_lifetime_average(self):
        m=MetaController(); features=(0.5,0.5)
        for _ in range(20):
            m.observe('scheduler',features,'A',success=True,cost=1)
            m.observe('scheduler',features,'B',success=False,cost=1)
        self.assertEqual(m.rank('scheduler',features,['A','B'])['order'][0],'A')
        for _ in range(3):
            m.observe('scheduler',features,'A',success=False,cost=1)
            m.observe('scheduler',features,'B',success=True,cost=1)
        route=m.rank('scheduler',features,['A','B'])
        self.assertEqual(route['mode'],'aikr_budget')
        self.assertEqual(route['order'][0],'B')
        # A lifetime average is still dominated by the old regime at this point.
        sig=m.signature(features)
        legacy=m._exact_order(m.exact['scheduler'][sig],['A','B'])
        self.assertEqual(legacy[0],'A')
        snap=m.budget_snapshot('scheduler',features)
        self.assertGreater(snap['B']['priority'],snap['A']['priority'])

    def test_expected_information_per_cost_avoids_expensive_unneeded_probe(self):
        actual_cost={0:10.0,1:1.0,2:1.0,3:1.0}
        fn=lambda x:x[1]+x[2]
        base=[(2,3,5,7),(4,6,10,14),(6,9,15,21)]
        treatment=Bot(); control=Bot()
        for b in (treatment,control):
            train_pair_cardinality_prior(b); b.programs.max_candidates=1
            for row in base:
                b.observe_transition('Explora cuatro.',row,(fn(row),))
            b.programs.max_candidates=150

        tp=treatment.suggest_transition_probe('Explora cuatro.',role_costs=actual_cost)
        cp=control.suggest_transition_probe('Explora cuatro.')
        self.assertEqual(tp['status'],'evidence_probe'); self.assertEqual(cp['status'],'evidence_probe')
        self.assertEqual(tp['vary_role'],1)
        self.assertEqual(cp['vary_role'],0)
        tr=treatment.observe_transition('Explora cuatro.',tuple(tp['before']),(fn(tuple(tp['before'])),))
        cr=control.observe_transition('Explora cuatro.',tuple(cp['before']),(fn(tuple(cp['before'])),))
        self.assertEqual(tr['status'],'procedure_learned'); self.assertEqual(cr['status'],'procedure_learned')
        self.assertEqual(actual_cost[tp['vary_role']],1.0)
        self.assertEqual(actual_cost[cp['vary_role']],10.0)
        for i in range(100):
            row=(i+1,3*i+2,7*i+4,11*i+8)
            self.assertEqual(treatment.execute_transition('Explora cuatro.',row)['result'],(fn(row),))
            self.assertEqual(control.execute_transition('Explora cuatro.',row)['result'],(fn(row),))

    def test_equal_costs_preserve_conservative_probe_order(self):
        b=Bot(); train_pair_cardinality_prior(b); b.programs.max_candidates=1
        fn=lambda x:x[0]*x[3]+1
        for row in ((2,3,5,7),(4,6,10,14),(6,9,15,21)):
            b.observe_transition('Explora cuatro.',row,(fn(row),))
        seen=[]
        for _ in range(4):
            probe=b.suggest_transition_probe('Explora cuatro.')
            self.assertEqual(probe['status'],'evidence_probe')
            seen.append(probe['vary_role'])
            row=tuple(probe['before']); b.observe_transition('Explora cuatro.',row,(fn(row),))
        self.assertEqual(seen,[0,1,2,3])

    def test_v2_budget_state_persists_and_v1_state_migrates(self):
        m=MetaController(); f=(0.2,0.8)
        for _ in range(4):
            m.observe('x',f,'fast',success=True,cost=2)
            m.observe('x',f,'slow',success=False,cost=8)
        restored=MetaController.from_dict(m.as_dict())
        self.assertEqual(restored.rank('x',f,['slow','fast'])['order'][0],'fast')
        self.assertEqual(restored.budget_snapshot('x',f),m.budget_snapshot('x',f))
        v1=m.as_dict(); v1['version']=1; v1.pop('budgets',None); v1.pop('clock',None)
        migrated=MetaController.from_dict(v1)
        self.assertTrue(migrated.budget_snapshot('x',f))
        self.assertIn(migrated.rank('x',f,['slow','fast'])['order'][0],('fast','slow'))


if __name__=='__main__':
    unittest.main()

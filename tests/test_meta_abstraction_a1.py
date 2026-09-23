"""Development-only test for reuse of a learned meta subrule."""

import unittest
import random

from leobot.metacontrol import MetaController


def vector(index, comparisons, scale=1, *, new_centers=False):
    bits=[(index >> k) & 1 for k in range(comparisons)]
    values=[]
    for k,bit in enumerate(bits):
        center=scale*((10 ** (k+3) if not new_centers else 10 ** (k+4))
                      + index*(17+11*k))
        delta=scale*(2+k)
        values.extend((center+delta,center-delta) if bit
                      else (center-delta,center+delta))
    return tuple(values),bits


def teach(controller, family, comparisons, count, labels, scale=1, *, reverse=False):
    for index in range(count):
        features,bits=vector(index,comparisons,scale)
        target=labels[0] if sum(bits)%2 else labels[1]
        if reverse:
            target=labels[1] if target==labels[0] else labels[0]
        for strategy in labels:
            controller.observe(family,features,strategy,success=strategy==target,
                               cost=1 if strategy==target else 9,failure_budget=2)


class MetaAbstractionA1Tests(unittest.TestCase):
    def test_repeated_piece_survives_order_induced_redundant_predicate(self):
        controller=MetaController()
        for k,(family,labels) in enumerate((('first',('A','B')),
                                            ('second',('X','Y')))):
            indices=list(range(32));random.Random(17+101*k).shuffle(indices)
            for index in indices:
                features,bits=vector(index,2,scale=1 if k==0 else 7)
                target=labels[0] if sum(bits)%2 else labels[1]
                for strategy in labels:
                    controller.observe(family,features,strategy,
                                       success=strategy==target,
                                       cost=1 if strategy==target else 9,
                                       failure_budget=2)
        self.assertTrue(controller.meta_primitives)

    def test_later_evidence_fills_missing_branch_of_early_program(self):
        controller=MetaController()
        for k,(family,labels) in enumerate((('first',('A','B')),
                                            ('second',('X','Y')))):
            indices=list(range(32));random.Random(53+101*k).shuffle(indices)
            for index in indices:
                features,bits=vector(index,2,scale=1 if k==0 else 7)
                target=labels[0] if sum(bits)%2 else labels[1]
                for strategy in labels:
                    controller.observe(family,features,strategy,
                                       success=strategy==target,
                                       cost=1 if strategy==target else 9,
                                       failure_budget=2)
        self.assertTrue(controller.meta_primitives)

    def test_two_independent_sources_compile_a_reusable_subrule(self):
        controller=MetaController()
        teach(controller,'source_one',2,32,('A','B'))
        teach(controller,'source_two',2,32,('X','Y'),scale=7)
        self.assertTrue(controller.meta_primitives)
        self.assertTrue(any(len(row['sources'])>=2 for row in controller.meta_primitives.values()))

        teach(controller,'target',4,64,('left','right'))
        view=controller.invented_views.get('target')
        self.assertIsNotNone(view)
        self.assertEqual(view['kind'],'macro_program')
        self.assertLessEqual(view['candidates_evaluated'],32)
        correct=0
        for index in range(64,96):
            features,bits=vector(index,4,new_centers=True)
            expected='left' if sum(bits)%2 else 'right'
            correct+=controller.rank('target',features,('left','right'))['order'][0]==expected
        self.assertGreaterEqual(correct,30)

        restored=MetaController.from_dict(controller.as_dict())
        self.assertEqual(restored.invented_views['target']['kind'],'macro_program')
        teach(restored,'source_one',2,32,('A','B'),reverse=True)
        self.assertNotIn('target',restored.invented_views)


if __name__=='__main__':
    unittest.main()

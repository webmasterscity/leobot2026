"""Development tests for a learned, reusable aggregate operator."""

import random
import unittest

from leobot.metacontrol import MetaController
from leobot import meta_operators


def pair_task(index, *, heldout=False):
    bits=[(index>>k)&1 for k in range(6)]
    values=[]
    for k,bit in enumerate(bits):
        center=(10**(k%4+2) if not heldout else -10**(k%4+3))+37*index+101*k
        delta=3+(k if heldout else 0)
        values.extend((center+delta,center-delta) if bit
                      else (center-delta,center+delta))
    return tuple(values),'A' if sum(bits)>=4 else 'B'


def raw_task(index, *, heldout=False):
    bits=[(index>>k)&1 for k in range(8)]
    values=tuple((1 if bit else -1)*(3+k+(index*7+k*11)%9)
                 * (3 if heldout else 1) for k,bit in enumerate(bits))
    return values,'north' if sum(bits)>=5 else 'south'


def teach(controller,family,rows,labels):
    for features,target in rows:
        for strategy in labels:
            controller.observe(family,features,strategy,success=strategy==target,
                               cost=1 if strategy==target else 9,failure_budget=2)


def score(controller,family,rows,labels):
    return sum(controller.rank(family,features,labels)['order'][0]==target
               for features,target in rows)


class MetaOperatorB1Tests(unittest.TestCase):
    def test_rival_representation_requests_real_discriminating_observation(self):
        controller=MetaController()
        teach(controller,'source',[pair_task(i) for i in range(64)],('A','B'))
        configs=random.Random(17).sample(range(256),128)
        rows=[]
        for index in configs:
            features,target=raw_task(index)
            factor=4 if target=='north' else 1
            rows.append((tuple(value*factor for value in features),target))
        teach(controller,'ambiguous',rows,('north','south'))
        self.assertTrue(controller.meta_rivals.get('ambiguous'))
        pool=[]
        for features,_ in rows:
            changed=tuple(abs(value) for value in features[:7])+(features[7],)
            pool.append({'features':changed,'cost':1})
            if len(pool)>=16:
                break
        proposal=controller.propose_meta_probe('ambiguous',pool)
        self.assertEqual(proposal['status'],'epistemic_action')
        chosen=pool[proposal['chosen_index']]['features']
        truth='north' if sum(value>0 for value in chosen)>=5 else 'south'
        for strategy in ('north','south'):
            controller.observe('ambiguous',chosen,strategy,
                               success=strategy==truth,cost=1 if strategy==truth else 9)
        self.assertFalse(controller.meta_rivals.get('ambiguous'))

    def test_persisted_operator_cannot_expand_mapper_grammar(self):
        spec=meta_operators.candidate_specs(8)[0]
        spec['map_expr']={'op':'call','value':'hidden','children':[]}
        self.assertIsNone(meta_operators.evaluate((1,)*8,spec))

    def test_counterevidence_withdraws_operator_and_dependent_view(self):
        controller=MetaController()
        teach(controller,'source',[pair_task(i) for i in range(64)],('A','B'))
        configs=random.Random(17).sample(range(256),128)
        teach(controller,'new_layout',[raw_task(i) for i in configs],
              ('north','south'))
        self.assertEqual(controller.invented_views['new_layout']['kind'],
                         'aggregate_program')
        for index in range(64,96):
            features,_=pair_task(index)
            target='A' if index&1 else 'B'
            for strategy in ('A','B'):
                controller.observe('source',features,strategy,
                                   success=strategy==target,
                                   cost=1 if strategy==target else 9,
                                   failure_budget=2)
        restored=MetaController.from_dict(controller.as_dict())
        self.assertNotIn('new_layout',restored.invented_views)
        self.assertFalse(restored.meta_operators)

    def test_invented_aggregate_transfers_to_different_input_layout(self):
        source=[pair_task(index) for index in range(64)]
        source_heldout=[pair_task(index,heldout=True) for index in range(64,128)]
        configs=random.Random(17).sample(range(256),128)
        target=[raw_task(index) for index in configs]
        remaining=sorted(set(range(256))-set(configs))
        target_heldout=[raw_task(index,heldout=True) for index in remaining]

        educated=MetaController()
        teach(educated,'source',source,('A','B'))
        self.assertTrue(educated.meta_operators)
        self.assertGreaterEqual(score(educated,'source',source_heldout,('A','B')),58)
        teach(educated,'new_layout',target,('north','south'))
        self.assertGreaterEqual(score(educated,'new_layout',target_heldout,
                                      ('north','south')),115)
        self.assertEqual(educated.invented_views['new_layout']['kind'],
                         'aggregate_program')

        fresh=MetaController()
        teach(fresh,'new_layout',target,('north','south'))
        self.assertGreaterEqual(score(fresh,'new_layout',target_heldout,
                                      ('north','south')),115)
        self.assertLess(educated.aggregate_candidates_evaluated['new_layout'],
                        fresh.aggregate_candidates_evaluated['new_layout'])

        ablated=MetaController()
        ablated.enable_meta_operator_invention=False
        teach(ablated,'source',source,('A','B'))
        self.assertLessEqual(score(ablated,'source',source_heldout,('A','B')),48)


if __name__=='__main__':
    unittest.main()

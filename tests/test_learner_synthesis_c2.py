"""Development checks for safe, acquired learner composition."""
import random
import unittest

from leobot.metacontrol import MetaController
from leobot import learner_dsl


def first(index, salt=0):
    bits=[(index>>k)&1 for k in range(9)]
    context=2*bits[0]-1
    values=(context*(1+((index*37+salt)%23)),
            *((1 if bit else -1)*(2+((index*11+k*13+salt)%31))
              for k,bit in enumerate(bits[1:])))
    return values,sum(bits[1:])>=(6 if context>0 else 3)


def second(index, salt=0):
    bits=[(index>>k)&1 for k in range(9)]
    context=bits[0]
    center=(1 if (index*19+salt)%3 else -1)*(1000+13*index+salt)
    delta=2+((index+salt)%7)
    pair=((center+delta,center-delta) if context else
          (center-delta,center+delta))
    values=pair+tuple((1 if bit else -1)*(3+((index*7+k*17+salt)%37))
                      for k,bit in enumerate(bits[1:]))
    return values,sum(bits[1:])>=(6 if context else 4)


def teach(controller,family,indices,generate,reverse=False):
    for index in indices:
        features,positive=generate(index)
        if reverse:
            positive=not positive
        for strategy in ('north','south'):
            success=(strategy=='north')==positive
            controller.observe(family,features,strategy,success=success,
                               cost=1 if success else 9)


def score(controller,family,indices,generate):
    return sum((controller.rank(family,generate(index,179)[0],
                                ('north','south'))['order'][0]=='north')==
               generate(index,179)[1] for index in indices)


class LearnerSynthesisTests(unittest.TestCase):
    def test_acquired_program_transfers_then_withdraws_with_dependents(self):
        source=random.Random(17).sample(range(512),128)
        target=random.Random(53).sample(range(512),128)
        reserve=sorted(set(range(512))-set(target))[:128]
        educated=MetaController()
        teach(educated,'f1',source,first)
        self.assertEqual(educated.invented_views['f1']['kind'],
                         'learner_product')
        teach(educated,'f2',target,second)
        self.assertGreaterEqual(score(educated,'f2',reserve,second),115)
        self.assertTrue(educated.invented_views['f2']['learner_dependency'])
        program=educated.invented_views['f1']['learner_program']
        self.assertNotIn('f1',str(program))
        self.assertNotIn('north',str(program))

        fresh=MetaController()
        teach(fresh,'f2',target,second)
        self.assertGreaterEqual(score(fresh,'f2',reserve,second),115)
        self.assertLess(educated.learner_synthesis_counts['f2']['hypotheses'],
                        fresh.learner_synthesis_counts['f2']['hypotheses'])

        restored=MetaController.from_dict(educated.as_dict())
        self.assertEqual(score(restored,'f2',reserve,second),
                         score(educated,'f2',reserve,second))
        teach(restored,'f1',range(512,544),first,reverse=True)
        again=MetaController.from_dict(restored.as_dict())
        self.assertNotIn('f2',again.invented_views)
        self.assertFalse(again.meta_learners)

    def test_bad_composition_cannot_execute_code(self):
        self.assertIsNone(learner_dsl.evaluate_components(
            (1,2,3,4),[{'kind':'python','code':'1+1'},
                        {'kind':'binary_index','index':0}]))


if __name__=='__main__':
    unittest.main()

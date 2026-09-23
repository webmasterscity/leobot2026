"""Safety and budget boundaries for declarative meta-learners."""
import json
from copy import deepcopy
import unittest

from leobot import learner_dsl


class DeclarativeLearnerTests(unittest.TestCase):
    def test_specs_are_complete_serializable_data(self):
        required={'input_representation','hypothesis_generator','operators',
                  'constraints','search','verifier','cost','promotion','rollback','budget'}
        for spec in (learner_dsl.PROJECTION_LEARNER,
                     learner_dsl.AGGREGATE_LEARNER):
            self.assertEqual(set(spec),required)
            learner_dsl.validate(json.loads(json.dumps(spec)))

    def test_rejects_executable_or_unbounded_descriptions(self):
        bad=[]
        for field,value in (('hypothesis_generator','python'),
                            ('operators',['index','shell']),
                            ('operators',['index',{'call':'os.system'}])):
            spec=deepcopy(learner_dsl.PROJECTION_LEARNER)
            spec[field]=value;bad.append(spec)
        oversized=deepcopy(learner_dsl.PROJECTION_LEARNER)
        oversized['budget']['max_candidates']=1_000_000;bad.append(oversized)
        hidden=deepcopy(learner_dsl.PROJECTION_LEARNER)
        hidden['verifier']['expected_answers']=['p'];bad.append(hidden)
        for spec in bad:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    learner_dsl.validate(spec)

    def test_candidate_budget_stops_without_promotion(self):
        spec=deepcopy(learner_dsl.PROJECTION_LEARNER)
        spec['budget']['max_candidates']=1
        tasks=[{'features':(float(index%2),float(index)),
                'winner':'p' if index%2 else 'q'} for index in range(16)]
        result=learner_dsl.fit(spec,tasks)
        self.assertEqual(result['status'],'budget_exceeded')
        self.assertNotIn('view',result)


if __name__=='__main__':
    unittest.main()

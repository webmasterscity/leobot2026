import tempfile
import unittest
from pathlib import Path
from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set


def train_pair_cardinality_prior(bot: Bot):
    for idx,roles in enumerate(((0,1),(0,2),(1,2))):
        rep=teach_role_set(bot,idx+3,roles)
        if rep.get('status')!='schema_learned':
            raise AssertionError(rep)


def target_rows_4():
    return [(2,3,5,7),(2,10,5,7),(2,3,12,7),(4,3,5,7),(2,3,5,9)]


class V61RoleCardinalityMetaLearningTests(unittest.TestCase):
    def test_learned_cardinality_prior_transfers_to_unseen_arity(self):
        treatment=Bot(); control=Bot(); train_pair_cardinality_prior(treatment)
        treatment.programs.max_candidates=control.programs.max_candidates=150
        tr=cr=None
        for row in target_rows_4():
            y=(row[0]*row[3]+1,)
            tr=treatment.observe_transition('Calcula cuatro roles.',row,y)
            cr=control.observe_transition('Calcula cuatro roles.',row,y)
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(cr['status'],'procedure_unresolved')
        detail=tr['reports'][0]
        self.assertEqual(detail['meta_dependency_schema'],'card:2->roles:4:0,3')
        self.assertEqual(detail['allowed_vars'],[0,3])
        self.assertEqual(treatment.execute_transition('Calcula cuatro roles.',(11,200,-9,13))['result'],(144,))

    def test_cardinality_prior_requires_independent_sources(self):
        bot=Bot(); teach_role_set(bot,4,(0,2)); bot.programs.max_candidates=150
        rep=None
        for row in target_rows_4():
            rep=bot.observe_transition('Una fuente no basta.',row,(row[0]*row[3]+1,))
        self.assertEqual(rep['status'],'procedure_unresolved')
        self.assertIsNone(rep['reports'][0].get('meta_dependency_schema'))

    def test_cardinality_prior_does_not_force_wrong_sparsity(self):
        bot=Bot(); train_pair_cardinality_prior(bot); bot.programs.max_candidates=5000
        rows=[(2,3,5,7),(4,3,5,7),(2,6,5,7),(2,3,9,7),(2,3,5,11),(5,8,4,9)]
        rep=None
        for row in rows:
            # Three genuinely relevant roles: 0,1,3. No size-2 subset has all
            # required invariance/sensitivity witnesses.
            rep=bot.observe_transition('Tres roles reales.',row,(row[0]+row[1]*row[3],))
        self.assertEqual(rep['status'],'procedure_learned')
        detail=rep['reports'][0]
        self.assertEqual(detail['allowed_vars'],[0,1,2,3])
        self.assertIsNone(detail.get('meta_dependency_schema'))
        self.assertEqual(bot.execute_transition('Tres roles reales.',(7,4,999,5))['result'],(27,))

    def test_cardinality_and_search_policy_persist(self):
        bot=Bot(); train_pair_cardinality_prior(bot)
        # Seed a successful 4:2 policy as well.
        bot.programs.max_candidates=150
        for row in target_rows_4():
            rep=bot.observe_transition('Primera aridad cuatro.',row,(row[0]*row[3]+1,))
        self.assertEqual(rep['status'],'procedure_learned')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
            self.assertIn('card:2',loaded.procedures.external_role_cardinalities)
            self.assertIn('4:2',loaded.procedures.dependency_search_stats)
            loaded.programs.max_candidates=150
            out=None
            for row in [(3,4,8,2),(3,99,8,2),(3,4,42,2),(5,4,8,2),(3,4,8,7)]:
                out=loaded.observe_transition('Segunda aridad cuatro.',row,(row[0]*row[3]-1,))
            self.assertEqual(out['status'],'procedure_learned')
            self.assertEqual(out['reports'][0]['meta_dependency_roles'],[0,3])

if __name__=='__main__': unittest.main()

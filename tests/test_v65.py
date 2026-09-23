import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set
from test_v63 import train_chain_prior, chain_transition

F=lambda *x: tuple(x)


def train_pair_cardinality_prior(bot: Bot):
    for idx,roles in enumerate(((0,1),(0,2),(1,2))):
        rep=teach_role_set(bot,idx+3,roles)
        if rep.get('status')!='schema_learned':
            raise AssertionError(rep)


def numeric_seed(bot: Bot):
    bot.programs.max_candidates=150
    rows=[(2,3,5,7),(2,10,5,7),(2,3,12,7),(4,3,5,7),(2,3,5,9)]
    rep=None
    for row in rows:
        rep=bot.observe_transition('Semilla numerica transversal.',row,(row[0]*row[3]+1,))
    if rep.get('status')!='procedure_learned':
        raise AssertionError(rep)
    return rep


def transport_episode(bot: Bot,i:int,success=True,missing=None):
    p,t,s,d=f'persona{i}',f'token{i}',f'origen{i}',f'destino{i}'
    before={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),
            F('person',p),F('place',s),F('place',d)}
    if missing=='road': before.discard(F('road',s,d))
    after=set(before)
    if success:
        after.discard(F('at',p,s)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',before,after)


class V65MetaControllerTests(unittest.TestCase):
    def test_cross_learner_history_reduces_representation_attempts(self):
        treatment=Bot(); control=Bot()
        for b in (treatment,control):
            train_pair_cardinality_prior(b); numeric_seed(b)
        # Preserve all learned priors/history but disable meta-control only at the
        # symbolic consumer in the ablation.
        control.symbolic.meta_controller=None
        for b in (treatment,control):
            transport_episode(b,1); transport_episode(b,2)
        tr=transport_episode(treatment,3,False,'road')
        cr=transport_episode(control,3,False,'road')
        self.assertEqual(tr['status'],'operator_learned')
        self.assertEqual(cr['status'],'operator_learned')
        self.assertEqual(tr['precondition_mode'],'meta_role_cardinality_transfer')
        self.assertEqual(cr['precondition_mode'],'meta_role_set_transfer')
        self.assertEqual(len(tr['meta_controller_representation_attempts']),1)
        self.assertEqual(len(cr['meta_controller_representation_attempts']),4)
        self.assertEqual(tr['meta_controller_representation_attempts'][0]['strategy'],'role_cardinality')
        self.assertTrue(tr['meta_controller_route']['used'])

    def test_meta_preference_never_suppresses_topology_fallback(self):
        bot=Bot(); train_pair_cardinality_prior(bot); numeric_seed(bot); train_chain_prior(bot)
        chain_transition(bot,1)
        rep=chain_transition(bot,2)
        self.assertEqual(rep['status'],'operator_learned')
        self.assertEqual(rep['precondition_mode'],'meta_role_topology_transfer')
        attempts=rep['meta_controller_representation_attempts']
        self.assertEqual(attempts[0]['strategy'],'role_cardinality')
        self.assertFalse(attempts[0]['learned'])
        self.assertEqual(next(x['strategy'] for x in attempts if x['learned']),'role_topology')

    def test_representation_gap_requests_discriminating_evidence(self):
        bot=Bot()
        p,o,d='personauno','origenuno','destinouno'
        before={F('at',p,o),F('road',o,d),F('person',p),F('place',o),F('place',d)}
        after=set(before); after.remove(F('at',p,o)); after.add(F('at',p,d))
        rep=bot.observe_symbolic_transition(f'Mueve {p} de {o} a {d}.',before,after)
        self.assertEqual(rep['status'],'pending_support')
        self.assertEqual(rep['meta_controller_gap']['status'],'meta_representation_gap')
        self.assertEqual(rep['meta_controller_gap']['evidence_request']['kind'],'independent_success')

    def test_active_probe_shrinks_role_version_space_without_labels(self):
        bot=Bot(); train_pair_cardinality_prior(bot); bot.programs.max_candidates=1
        fn=lambda x:x[0]*x[3]+1
        for row in ((2,3,5,7),(4,6,10,14),(6,9,15,21)):
            rep=bot.observe_transition('Explora cuatro.',row,(fn(row),))
        self.assertEqual(rep['status'],'procedure_unresolved')
        initial=bot.suggest_transition_probe('Explora cuatro.')
        self.assertEqual(initial['status'],'evidence_probe')
        self.assertEqual(len(initial['candidate_role_sets']),6)
        seen=[]
        for _ in range(8):
            probe=bot.suggest_transition_probe('Explora cuatro.')
            if probe.get('status')!='evidence_probe':
                break
            seen.append(probe['vary_role'])
            row=tuple(probe['before'])
            bot.observe_transition('Explora cuatro.',row,(fn(row),))
        end=bot.suggest_transition_probe('Explora cuatro.')
        self.assertEqual(end['status'],'no_probe')
        self.assertEqual(end['candidate_role_sets'],[[0,3]])
        self.assertEqual(seen[:4],[0,1,2,3])
        # Once evidence has identified the roles, ordinary synthesis can use a
        # normal budget and learn the executable rule; the probe never supplied y.
        bot.programs.max_candidates=150
        last=bot.procedures.sessions['explora cuatro']['supports'][-1]
        final=bot.observe_transition('Explora cuatro.',tuple(last['before']),tuple(last['after']))
        self.assertEqual(final['status'],'procedure_learned')
        self.assertEqual(final['reports'][0]['meta_dependency_roles'],[0,3])

    def test_meta_controller_persists_once_at_bot_level(self):
        bot=Bot(); train_pair_cardinality_prior(bot); numeric_seed(bot)
        observations=bot.meta_controller.observations
        self.assertGreater(observations,0)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
        self.assertEqual(loaded.meta_controller.observations,observations)
        self.assertIs(loaded.procedures.meta_controller,loaded.meta_controller)
        self.assertIs(loaded.symbolic.meta_controller,loaded.meta_controller)


if __name__=='__main__':
    unittest.main()

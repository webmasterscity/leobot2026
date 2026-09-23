import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set

F=lambda *x: tuple(x)


def train_pair_cardinality_prior(bot: Bot):
    for idx,roles in enumerate(((0,1),(0,2),(1,2))):
        rep=teach_role_set(bot,idx+3,roles)
        if rep.get('status')!='schema_learned':
            raise AssertionError(rep)


def train_singleton_cardinality_prior(bot: Bot):
    for idx,roles in enumerate(((0,),(1,),(2,))):
        rep=teach_role_set(bot,idx,roles)
        if rep.get('status')!='schema_learned':
            raise AssertionError(rep)


def transport_episode(bot: Bot,p,t,s,d,success=True,missing=None):
    before={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),
            F('person',p),F('place',s),F('place',d)}
    if missing=='road': before.discard(F('road',s,d))
    after=set(before)
    if success:
        after.discard(F('at',p,s)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(
        f'Transporta a {p} con {t} de {s} a {d}.',before,after)


class V62CrossLearnerCardinalityTests(unittest.TestCase):
    def test_cardinality_learned_at_arity3_accelerates_symbolic_action_at_arity4(self):
        treatment=Bot(); control=Bot(); train_pair_cardinality_prior(treatment)
        for vals in [('personauno','tokenuno','origenuno','destinouno'),
                     ('personados','tokendos','origendos','destinodos')]:
            tr=transport_episode(treatment,*vals); cr=transport_episode(control,*vals)
        self.assertEqual(tr['status'],'pending_support')
        tr=transport_episode(treatment,'personatres','tokentres','origentres','destinotres',False,'road')
        cr=transport_episode(control,'personatres','tokentres','origentres','destinotres',False,'road')
        self.assertEqual(tr['status'],'operator_learned')
        self.assertEqual(tr['precondition_mode'],'meta_role_cardinality_transfer')
        self.assertEqual(tr['cross_modal_schema'],'card:2')
        self.assertEqual(tr['target_role_mapping'],[0,3])
        self.assertEqual(cr['status'],'pending_support')
        for i in range(100):
            p,t,s,d=f'persona{i}',f'token{i}',f'origen{i}',f'destino{i}'
            state={F('at',p,s),F('road',s,d),F('authorized',p,t),F('token',t),
                   F('person',p),F('place',s),F('place',d)}
            out=treatment.execute_symbolic_transition(f'Transporta a {p} con {t} de {s} a {d}.',state)
            self.assertEqual(out['status'],'executed_symbolic_action')
            self.assertIn(F('at',p,d),set(out['result']))

    def test_cardinality_requires_multiple_independent_sources(self):
        bot=Bot(); teach_role_set(bot,0,(0,2))
        transport_episode(bot,'personaa','tokena','origena','destinoa')
        transport_episode(bot,'personab','tokenb','origenb','destinob')
        rep=transport_episode(bot,'personac','tokenc','origenc','destinoc',False,'road')
        self.assertEqual(rep['status'],'pending_support')

    def test_wrong_cardinality_does_not_force_target_operator(self):
        bot=Bot(); train_singleton_cardinality_prior(bot)
        transport_episode(bot,'personad','tokend','origend','destinod')
        transport_episode(bot,'personae','tokene','origene','destinoe')
        rep=transport_episode(bot,'personaf','tokenf','origenf','destinof',False,'road')
        self.assertEqual(rep['status'],'pending_support')
        self.assertNotEqual(rep.get('precondition_mode'),'meta_role_cardinality_transfer')

    def test_symbolic_cardinality_prior_persists_and_rehydrates(self):
        bot=Bot(); train_pair_cardinality_prior(bot)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
        self.assertIn('card:2',loaded.symbolic.external_role_cardinalities)
        transport_episode(loaded,'personag','tokeng','origeng','destinog')
        transport_episode(loaded,'personah','tokenh','origenh','destinoh')
        rep=transport_episode(loaded,'personai','tokeni','origeni','destinoi',False,'road')
        self.assertEqual(rep['status'],'operator_learned')
        self.assertEqual(rep['precondition_mode'],'meta_role_cardinality_transfer')


if __name__=='__main__': unittest.main()

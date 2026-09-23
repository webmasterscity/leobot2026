import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom

F=lambda *x: tuple(x)


def teach_chain_schema(bot: Bot, p: str, q: str, prefix: str, word: str):
    facts=[
        (p,f'{prefix}a1',f'{prefix}b1'),(q,f'{prefix}b1',f'{prefix}c1'),
        (p,f'{prefix}a2',f'{prefix}b2'),(q,f'{prefix}b2',f'{prefix}c2'),
    ]
    for fact in facts:
        bot.kb.add(Atom(fact[0],tuple(fact[1:])), 'v63-seed')
    a1,b1,c1=f'{prefix}a1',f'{prefix}b1',f'{prefix}c1'
    a2,b2,c2=f'{prefix}a2',f'{prefix}b2',f'{prefix}c2'
    reports=[]
    for text in (
        f'{word} {a1} conecta {b1} con {c1}',
        f'{word} {a2} conecta {b2} con {c2}',
        f'{word} {a1} no conecta {b1} con {c2}',
        f'{word} {a1} no conecta {b2} con {c1}',
        f'{word} {a2} no conecta {b1} con {c1}',
    ):
        reports.append(bot.observe_schema_statement(text))
    return reports[-1]


def train_chain_prior(bot: Bot):
    a=teach_chain_schema(bot,'p1','q1','x','alpha')
    b=teach_chain_schema(bot,'p2','q2','y','beta')
    if a.get('status')!='schema_learned' or b.get('status')!='schema_learned':
        raise AssertionError((a,b))


def chain_transition(bot: Bot, i: int):
    p,o,d=f'persona{i}',f'origen{i}',f'destino{i}'
    before={F('at',p,o),F('road',o,d),F('auth',p,d),F('person',p),F('place',o),F('place',d)}
    after=set(before); after.remove(F('at',p,o)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Mueve {p} de {o} a {d}.',before,after)


class V63RoleTopologyTests(unittest.TestCase):
    def test_chain_topology_transfers_across_language_to_symbolic(self):
        treatment=Bot(); control=Bot(); train_chain_prior(treatment)
        r1=chain_transition(treatment,1); c1=chain_transition(control,1)
        r2=chain_transition(treatment,2); c2=chain_transition(control,2)
        self.assertEqual(r1['status'],'pending_support')
        self.assertEqual(r2['status'],'operator_learned')
        self.assertEqual(r2['precondition_mode'],'meta_role_topology_transfer')
        self.assertEqual(r2['cross_modal_schema'],'topo:3:0,1;1,2')
        self.assertEqual(c1['status'],'pending_support')
        self.assertEqual(c2['status'],'pending_support')
        for i in range(30,80):
            p,o,d=f'persona{i}',f'origen{i}',f'destino{i}'
            state={F('at',p,o),F('road',o,d),F('auth',p,d),F('person',p),F('place',o),F('place',d)}
            out=treatment.execute_symbolic_transition(f'Mueve {p} de {o} a {d}.',state)
            self.assertEqual(out['status'],'executed_symbolic_action')
            self.assertIn(F('at',p,d),set(out['result']))

    def test_chain_prior_does_not_force_star_topology_with_same_three_roles(self):
        bot=Bot(); train_chain_prior(bot)
        final=None
        for i in (1,2):
            p,o,d=f'sujeto{i}',f'inicio{i}',f'fin{i}'
            before={F('at',p,o),F('permit',p,d),F('person',p),F('place',o),F('place',d)}
            after=set(before); after.remove(F('at',p,o)); after.add(F('at',p,d))
            final=bot.observe_symbolic_transition(f'Salta {p} de {o} a {d}.',before,after)
        self.assertEqual(final['status'],'pending_support')
        self.assertNotEqual(final.get('precondition_mode'),'meta_role_topology_transfer')

    def test_topology_requires_two_independent_sources(self):
        bot=Bot(); teach_chain_schema(bot,'p1','q1','x','alpha')
        chain_transition(bot,1)
        rep=chain_transition(bot,2)
        self.assertEqual(rep['status'],'pending_support')

    def test_topology_persists_and_rehydrates_symbolic_consumer(self):
        bot=Bot(); train_chain_prior(bot)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
        self.assertIn('topo:3:0,1;1,2',loaded.symbolic.external_role_topologies)
        chain_transition(loaded,1)
        rep=chain_transition(loaded,2)
        self.assertEqual(rep['status'],'operator_learned')
        self.assertEqual(rep['precondition_mode'],'meta_role_topology_transfer')

    def test_failure_with_all_topology_preconditions_vetoes_transfer(self):
        bot=Bot(); train_chain_prior(bot)
        chain_transition(bot,1); chain_transition(bot,2)
        # A no-change observation in which both proposed chain preconditions are
        # present refutes this topology for the target action.
        p,o,d='personax','origenx','destinox'
        before={F('at',p,o),F('road',o,d),F('auth',p,d),F('person',p),F('place',o),F('place',d)}
        rep=bot.observe_symbolic_transition(f'Mueve {p} de {o} a {d}.',before,before)
        self.assertNotEqual(rep.get('status'),'operator_learned')
        self.assertFalse(bot.symbolic.sessions['mueve <e0> de <e1> a <e2>'].get('promoted'))


if __name__=='__main__':
    unittest.main()

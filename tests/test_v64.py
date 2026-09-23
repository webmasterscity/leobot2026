import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.rbf import RBFStrategyRouter
from experiments.v59_architecture_freeze import teach_role_set
from experiments.v60_meta_dependency_experiment import ROLE_SETS, LABELS, diagnostic_rows, target


def educate_search_history(bot: Bot):
    for i, roles in enumerate(ROLE_SETS):
        teach_role_set(bot, i, roles)
    bot.programs.max_candidates = 150
    for label, roles in zip(LABELS, ROLE_SETS):
        for state in diagnostic_rows(roles):
            bot.observe_transition(f'Formula {label}.', state, (target(state, roles),))


def pollute_four_arity_library(bot: Bot):
    rows=[(2,3,5,7),(4,6,8,10),(3,5,7,9),(6,2,4,8),(9,3,2,5),(1,4,6,8)]
    funcs=[]
    for a in range(4):
        for c in (-1,1):
            funcs.append((f'junk{len(funcs)}', lambda x,a=a,c=c: x[a]+c))
    for a,c in [(0,1),(1,2),(2,3),(0,2),(1,3),(0,3)]:
        funcs.append((f'junk{len(funcs)}', lambda x,a=a,c=c: x[a]+x[c]))
    for name,fn in funcs:
        for row in rows:
            bot.programs.add_example(name,row,fn(row),concepts={'cruce','cuatro'})
        rep=bot.programs.fit(name,library=[])
        assert rep['status']=='learned_hypothesis'


def rows4(pair):
    base=[2,3,5,7]; out=[tuple(base)]
    for k in range(4):
        if k not in pair:
            q=base.copy(); q[k]+=11; out.append(tuple(q))
    for k in pair:
        q=base.copy(); q[k]+=2; out.append(tuple(q))
    return out


class V64RBFTests(unittest.TestCase):
    def test_router_exact_and_distilled_duplicates(self):
        r=RBFStrategyRouter()
        x=(.5,1.0,.5,.5)
        r.observe(x,'a',success=True,candidates=10,failure_budget=100)
        r.observe(x,'a',success=True,candidates=14,failure_budget=100)
        p=r.predict(x,'a')
        self.assertEqual(p['mode'],'exact')
        self.assertEqual(p['support'],2)
        self.assertAlmostEqual(p['cost'],12.0)
        self.assertEqual(len(r.nodes['a']),1)
        self.assertGreaterEqual(r.distilled,1)

    def test_cross_arity_rbf_saves_failed_search(self):
        treatment=Bot(); control=Bot(); control.procedures.rbf_strategy_enabled=False
        for b in (treatment,control):
            educate_search_history(b); pollute_four_arity_library(b); b.programs.max_candidates=150
        tr=cr=None
        for state in rows4((0,3)):
            y=(state[0]*state[3]+1,)
            tr=treatment.observe_transition('Cruce cuatro.',state,y)
            cr=control.observe_transition('Cruce cuatro.',state,y)
        td=tr['reports'][0]; cd=cr['reports'][0]
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(cr['status'],'procedure_learned')
        self.assertEqual(td['meta_dependency_strategy_order'][0],'no_library')
        self.assertTrue(td['meta_dependency_rbf_route']['used'])
        tcost=sum(int(x.get('candidates') or 0) for x in td['meta_dependency_attempts'])
        ccost=sum(int(x.get('candidates') or 0) for x in cd['meta_dependency_attempts'])
        self.assertLess(tcost,ccost)
        self.assertEqual(tcost,137)
        self.assertEqual(ccost,288)
        self.assertEqual(treatment.execute_transition('Cruce cuatro.',(11,99,-4,13))['result'],(144,))

    def test_rbf_does_not_overrule_nearby_one_role_success(self):
        bot=Bot(); educate_search_history(bot); bot.programs.max_candidates=150
        base=[2,3,5,7]; rows=[tuple(base)]
        for k in (1,2,3):
            q=base.copy(); q[k]+=11; rows.append(tuple(q))
        q=base.copy();q[0]+=2;rows.append(tuple(q))
        rep=None
        for state in rows:
            rep=bot.observe_transition('Cuadrado nuevo.',state,(state[0]*state[0]+1,))
        d=rep['reports'][0]
        self.assertEqual(d['meta_dependency_strategy_order'][0],'auto_library')
        self.assertTrue(d['meta_dependency_rbf_route']['used'])
        self.assertEqual(rep['status'],'procedure_learned')

    def test_rbf_meta_router_persists(self):
        bot=Bot(); educate_search_history(bot)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
            self.assertTrue(loaded.procedures.rbf_strategy_enabled)
            self.assertGreater(loaded.procedures.rbf_strategy_router.observations,0)
            route=loaded.procedures.rbf_strategy_router.rank(
                loaded.procedures._dependency_rbf_features(4,(0,3),5),
                ['auto_library','no_library'])
            self.assertTrue(route['used'])
            self.assertEqual(route['order'][0],'no_library')

if __name__=='__main__':
    unittest.main()

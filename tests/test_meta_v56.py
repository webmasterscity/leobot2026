import tempfile
import unittest
from pathlib import Path
from leobot import Bot

F=lambda *x: tuple(x)


def train_numeric_swap(bot: Bot):
    bot.procedures.min_support=3
    report=None
    for before in [(2,9),(5,-3),(11,4)]:
        report=bot.observe_transition('Intercambia los valores.',before,(before[1],before[0]))
    return report


def observe_symbolic_swap(bot: Bot, a,b,x,y, success=True, missing=None):
    phrase='{a} permuta {x} con {b} por {y}.'
    before={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
    if missing=='connected': before.discard(F('connected',a,b))
    if missing=='owns_left': before.discard(F('owns',a,x))
    if missing=='owns_right': before.discard(F('owns',b,y))
    after=set(before)
    if success:
        after.discard(F('owns',a,x)); after.discard(F('owns',b,y))
        after.add(F('owns',a,y)); after.add(F('owns',b,x))
    return bot.observe_symbolic_transition(phrase.format(a=a,b=b,x=x,y=y),before,after)


def train_two_successes_and_failure(bot: Bot):
    rows=[]
    rows.append(observe_symbolic_swap(bot,'ana','beto','x1','y1',True))
    rows.append(observe_symbolic_swap(bot,'carla','dani','x2','y2',True))
    rows.append(observe_symbolic_swap(bot,'eva','fran','x3','y3',False,'connected'))
    return rows


def heldout_swap(bot: Bot, n=50):
    ok=0
    for i in range(n):
        a,b,x,y=f'a{i}',f'b{i}',f'x{i}',f'y{i}'
        state={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
        out=bot.execute_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',state)
        result=set(out.get('result',()))
        ok += out.get('status')=='executed_symbolic_action' and F('owns',a,y) in result and F('owns',b,x) in result
    return ok


class V56CrossRepresentationTransferTests(unittest.TestCase):
    def test_numeric_permutation_registers_domain_free_schema(self):
        bot=Bot(); report=train_numeric_swap(bot)
        self.assertEqual(report['status'],'procedure_learned')
        self.assertEqual(report['cross_modal_learning']['schema'],'perm:2:1,0')
        row=bot.symbolic.external_permutation_schemas['perm:2:1,0']
        self.assertEqual(row['perm'],[1,0])
        self.assertNotIn('owns',str(row)); self.assertNotIn('connected',str(row))

    def test_cross_modal_prior_reduces_positive_support(self):
        treatment=Bot(); control=Bot()
        train_numeric_swap(treatment)
        t=train_two_successes_and_failure(treatment)
        c=train_two_successes_and_failure(control)
        self.assertEqual(t[-1]['status'],'operator_learned')
        self.assertEqual(t[-1]['precondition_mode'],'cross_modal_permutation_transfer')
        self.assertEqual(t[-1]['support'],2)
        self.assertNotEqual(c[-1]['status'],'operator_learned')
        self.assertEqual(heldout_swap(treatment,100),100)
        self.assertEqual(heldout_swap(control,20),0)

    def test_cross_modal_transfer_requires_target_contrast(self):
        bot=Bot(); train_numeric_swap(bot)
        observe_symbolic_swap(bot,'a','b','x1','y1',True)
        out=observe_symbolic_swap(bot,'c','d','x2','y2',True)
        self.assertNotEqual(out['status'],'operator_learned')
        self.assertEqual(heldout_swap(bot,10),0)

    def test_incompatible_nonpermutation_action_does_not_receive_prior(self):
        bot=Bot(); train_numeric_swap(bot); bot.symbolic.min_support=3
        def move(p,s,d,success=True,missing=None):
            before={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
            if missing=='road': before.discard(F('road',s,d))
            after=set(before)
            if success:
                after.discard(F('at',p,s)); after.add(F('at',p,d))
            return bot.observe_symbolic_transition(f'Mueve a {p} de {s} a {d}.',before,after)
        move('a','s1','d1'); move('b','s2','d2'); out=move('c','s3','d3',False,'road')
        self.assertNotEqual(out['status'],'operator_learned')

    def test_cross_modal_schema_persists(self):
        bot=Bot(); train_numeric_swap(bot)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            self.assertIn('perm:2:1,0',loaded.symbolic.external_permutation_schemas)
            out=train_two_successes_and_failure(loaded)[-1]
            self.assertEqual(out['precondition_mode'],'cross_modal_permutation_transfer')

    def test_counterevidence_with_inconsistent_effect_withdraws_transfer(self):
        bot=Bot(); train_numeric_swap(bot); train_two_successes_and_failure(bot)
        self.assertEqual(heldout_swap(bot,5),5)
        # Third successful episode has a different effect (identity-like ownership),
        # invalidating the previously consistent effect hypothesis.
        a,b,x,y='g','h','x9','y9'
        before={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
        after=set(before); after.discard(F('owns',a,x)); after.add(F('owns',a,y))
        out=bot.observe_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',before,after)
        self.assertNotEqual(out['status'],'operator_learned')
        ops=[o for o in bot.symbolic.operators() if 'permuta' in o['pattern']]
        self.assertEqual(ops,[])


    def test_symbolic_permutation_transfers_back_to_numeric_procedure(self):
        treatment=Bot(); control=Bot(); treatment.symbolic.min_support=3
        for i,(a,b,x,y) in enumerate([('a','b','x1','y1'),('c','d','x2','y2'),('e','f','x3','y3')]):
            before={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
            after=(before-{F('owns',a,x),F('owns',b,y)})|{F('owns',a,y),F('owns',b,x)}
            report=treatment.observe_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',before,after)
        self.assertEqual(report['cross_modal_learning']['schema'],'perm:2:1,0')
        for before in [(2,9),(5,-3)]:
            tr=treatment.observe_transition('Revierte el par.',before,(before[1],before[0]))
            cr=control.observe_transition('Revierte el par.',before,(before[1],before[0]))
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(tr['support'],2)
        self.assertEqual(tr['precondition_mode'],'cross_modal_permutation_transfer')
        self.assertEqual(cr['status'],'procedure_pending')
        self.assertEqual(treatment.execute_transition('Revierte el par.',(101,-7))['result'],(-7,101))
        self.assertEqual(control.execute_transition('Revierte el par.',(101,-7))['status'],'unknown_procedure')

    def test_reverse_transfer_is_withdrawn_by_numeric_counterexample(self):
        bot=Bot(); bot.symbolic.min_support=3
        for a,b,x,y in [('a','b','x1','y1'),('c','d','x2','y2'),('e','f','x3','y3')]:
            before={F('owns',a,x),F('owns',b,y),F('connected',a,b),F('person',a),F('person',b),F('item',x),F('item',y)}
            after=(before-{F('owns',a,x),F('owns',b,y)})|{F('owns',a,y),F('owns',b,x)}
            bot.observe_symbolic_transition(f'{a} permuta {x} con {b} por {y}.',before,after)
        bot.observe_transition('Revierte el par.',(2,9),(9,2))
        bot.observe_transition('Revierte el par.',(5,-3),(-3,5))
        self.assertEqual(bot.execute_transition('Revierte el par.',(8,4))['result'],(4,8))
        # Third support contradicts the projection; ordinary synthesis takes over
        # and must not preserve the stale prior implementation.
        out=bot.observe_transition('Revierte el par.',(7,6),(7,6))
        self.assertNotEqual(bot.execute_transition('Revierte el par.',(8,4)).get('result'),(4,8))
        session=bot.procedures.sessions['revierte el par']
        self.assertEqual(len(session['supports']),3)

if __name__=='__main__': unittest.main()

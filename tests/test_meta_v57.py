import tempfile
import unittest
from pathlib import Path
from leobot import Bot

F=lambda *x:tuple(x)


def train_numeric_projection(bot:Bot):
    bot.procedures.min_support=3
    report=None
    for before in [(1,2,3),(4,5,6),(7,8,9)]:
        report=bot.observe_transition('Conserva primero y tercero.',before,(before[0],before[2]))
    return report


def move_episode(bot:Bot, person, src, dst, success=True, missing=None):
    state={F('at',person,src),F('road',src,dst),F('person',person),F('place',src),F('place',dst)}
    if missing=='road': state.discard(F('road',src,dst))
    after=set(state)
    if success:
        after.discard(F('at',person,src));after.add(F('at',person,dst))
    return bot.observe_symbolic_transition(f'Traslada a {person} de {src} a {dst}.',state,after)


def train_two_moves_and_failure(bot:Bot):
    return [move_episode(bot,'ana','casa','oficina'),
            move_episode(bot,'bruno','plaza','tienda'),
            move_episode(bot,'carla','patio','taller',False,'road')]


def move_heldout(bot:Bot,n=50):
    ok=bad=0
    for i in range(n):
        p,s,d=f'persona{i}',f'origen{i}',f'destino{i}'
        state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
        out=bot.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state)
        res=set(out.get('result',()))
        ok += out.get('status')=='executed_symbolic_action' and F('at',p,d) in res
        broken=set(state);broken.discard(F('road',s,d))
        bad += bot.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',broken).get('status')!='executed_symbolic_action'
    return ok,bad


class V57CrossRepresentationProjectionTests(unittest.TestCase):
    def test_numeric_projection_registers_domain_free_role_flow(self):
        bot=Bot();report=train_numeric_projection(bot)
        self.assertEqual(report['status'],'procedure_learned')
        self.assertEqual(report['cross_modal_learning']['schema'],'proj:3:0,2')
        row=bot.symbolic.external_projection_schemas['proj:3:0,2']
        self.assertEqual(row['input_arity'],3);self.assertEqual(row['mapping'],[0,2])
        self.assertNotIn('at',str(row));self.assertNotIn('road',str(row))

    def test_numeric_projection_reduces_symbolic_positive_support(self):
        treatment=Bot();control=Bot();train_numeric_projection(treatment)
        tr=train_two_moves_and_failure(treatment);cr=train_two_moves_and_failure(control)
        self.assertEqual(tr[-1]['status'],'operator_learned')
        self.assertEqual(tr[-1]['precondition_mode'],'cross_modal_projection_transfer')
        self.assertEqual(tr[-1]['support'],2)
        self.assertNotEqual(cr[-1]['status'],'operator_learned')
        self.assertEqual(move_heldout(treatment,100),(100,100))
        self.assertEqual(move_heldout(control,20)[0],0)

    def test_projection_requires_target_contrast(self):
        bot=Bot();train_numeric_projection(bot)
        move_episode(bot,'ana','casa','oficina');out=move_episode(bot,'bruno','plaza','tienda')
        self.assertNotEqual(out['status'],'operator_learned')

    def test_symbolic_projection_transfers_back_to_numeric(self):
        treatment=Bot();control=Bot();treatment.symbolic.min_support=3
        for row in [('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','patio','taller')]:
            rep=move_episode(treatment,*row)
        self.assertEqual(rep['cross_modal_learning']['schema'],'proj:3:0,2')
        for before in [(10,99,20),(5,77,9)]:
            tr=treatment.observe_transition('Elige extremos.',before,(before[0],before[2]))
            cr=control.observe_transition('Elige extremos.',before,(before[0],before[2]))
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(tr['support'],2)
        self.assertEqual(tr['precondition_mode'],'cross_modal_projection_transfer')
        self.assertEqual(cr['status'],'procedure_pending')
        self.assertEqual(treatment.execute_transition('Elige extremos.',(11,22,33))['result'],(11,33))

    def test_incompatible_arithmetic_not_accelerated(self):
        bot=Bot();train_numeric_projection(bot)
        bot.procedures.min_support=3
        a=bot.observe_transition('Suma extremos.',(1,2,3),(4,))
        b=bot.observe_transition('Suma extremos.',(4,5,6),(10,))
        self.assertEqual(b['status'],'procedure_pending')

    def test_projection_persists(self):
        bot=Bot();train_numeric_projection(bot)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json';bot.save(p);loaded=Bot.load(p)
            self.assertIn('proj:3:0,2',loaded.symbolic.external_projection_schemas)
            out=train_two_moves_and_failure(loaded)[-1]
            self.assertEqual(out['precondition_mode'],'cross_modal_projection_transfer')

if __name__=='__main__':unittest.main()

class V57ObservedProjectionRegressionTests(unittest.TestCase):
    def test_four_to_three_projection_exports_even_with_equivalent_program_bodies(self):
        bot=Bot(); bot.procedures.min_support=3
        mapping=(2,0,1)
        rep=None
        for j in range(3):
            row=(100*j+1,100*j+2,100*j+3,100*j+4)
            rep=bot.observe_transition('Proyecta los roles.',row,tuple(row[i] for i in mapping))
        self.assertEqual(rep['status'],'procedure_learned')
        self.assertEqual(rep.get('cross_modal_learning',{}).get('schema'),'proj:4:2,0,1')

    def test_observed_projection_abstains_when_input_roles_are_indistinguishable(self):
        bot=Bot(); bot.procedures.min_support=3
        # x0 and x1 are deliberately identical in every support, so an output
        # equal to that value cannot safely be assigned to either role.
        rep=None
        for j in range(3):
            row=(10+j,10+j,30+j)
            rep=bot.observe_transition('Conserva un rol.',row,(row[0],))
        self.assertEqual(rep['status'],'procedure_learned')
        self.assertIsNone(rep.get('cross_modal_learning'))
        self.assertIsNone(bot.procedures.observed_projection_signature(
            bot.procedures.sessions[rep['pattern']]))

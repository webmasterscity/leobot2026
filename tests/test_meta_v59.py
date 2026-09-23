import tempfile
import unittest
from pathlib import Path

from leobot import Bot, Atom

F=lambda *x: tuple(x)


def teach_schema_projection(bot: Bot):
    for p,z in [('ana','norte'),('beto','sur'),('carla','este')]:
        bot.kb.add(Atom('ubicacion',(p,z)),'v59-seed')
    for obj in ('rojo','azul','verde','negro'):
        bot.kb.add(Atom('objeto',(obj,)),'v59-seed')
    rows=[
        'persona ana coordina objeto rojo en zona norte',
        'persona beto coordina objeto azul en zona sur',
        'persona ana no coordina objeto azul en zona sur',
        'persona ana no coordina objeto verde en zona este',
    ]
    rep=None
    for text in rows:
        rep=bot.observe_schema_statement(text)
    return rep


def symbolic_episode(bot,p,s,d,success=True,missing=None):
    state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
    if missing=='road': state.discard(F('road',s,d))
    after=set(state)
    if success:
        after.discard(F('at',p,s)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state,after)


class V59MetaRepresentationTests(unittest.TestCase):
    def test_language_schema_projection_accelerates_numeric_representation_learning(self):
        treatment=Bot(); control=Bot()
        learned=teach_schema_projection(treatment)
        self.assertEqual(learned['status'],'schema_learned')
        self.assertEqual(learned['meta_representation']['meta']['schema'],'roles:3:0,2')
        self.assertEqual(learned['meta_representation']['meta']['families'],['schema'])
        tr=cr=None
        for row in [(1,2,3),(4,5,6)]:
            tr=treatment.observe_transition('Conserva extremos.',row,(row[0],row[2]))
            cr=control.observe_transition('Conserva extremos.',row,(row[0],row[2]))
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(tr.get('precondition_mode'),'meta_role_set_transfer')
        self.assertEqual(cr['status'],'procedure_pending')
        for i in range(100):
            x=(10+i,1000+i,-500-i)
            self.assertEqual(treatment.execute_transition('Conserva extremos.',x)['result'],(x[0],x[2]))

    def test_language_schema_projection_accelerates_symbolic_action_but_keeps_target_contrast(self):
        treatment=Bot(); control=Bot(); teach_schema_projection(treatment)
        rows=[('pa','sa','da',True,None),('pb','sb','db',True,None)]
        for row in rows:
            tr=symbolic_episode(treatment,*row); cr=symbolic_episode(control,*row)
        self.assertEqual(tr['status'],'pending_support')
        # Prior topology never supplies target preconditions by itself.
        failure=symbolic_episode(treatment,'px','sx','dx',False,'road')
        control_failure=symbolic_episode(control,'px','sx','dx',False,'road')
        self.assertEqual(failure['status'],'operator_learned')
        self.assertEqual(failure['precondition_mode'],'meta_role_set_transfer')
        self.assertEqual(control_failure['status'],'pending_support')
        for i in range(100):
            p,s,d=f'p{i}',f's{i}',f'd{i}'
            state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
            out=treatment.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state)
            self.assertEqual(out['status'],'executed_symbolic_action')
            self.assertIn(F('at',p,d),set(out['result']))

    def test_incompatible_arithmetic_does_not_receive_projection_prior(self):
        bot=Bot(); teach_schema_projection(bot)
        reports=[]
        for row in [(2,7,3),(5,9,4)]:
            reports.append(bot.observe_transition('Combina extremos.',row,(row[0]+row[2],)))
        self.assertEqual(reports[-1]['status'],'procedure_pending')

    def test_role_set_prior_does_not_invent_output_order(self):
        treatment=Bot(); control=Bot(); teach_schema_projection(treatment)
        tr=cr=None
        for row in [(1,2,3),(4,5,6)]:
            # The language source only says roles {0,2} matter.  Target evidence
            # must determine that their output order is 2,0 rather than 0,2.
            tr=treatment.observe_transition('Invierte los extremos.',row,(row[2],row[0]))
            cr=control.observe_transition('Invierte los extremos.',row,(row[2],row[0]))
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(tr.get('precondition_mode'),'meta_role_set_transfer')
        self.assertEqual(cr['status'],'procedure_pending')
        self.assertEqual(treatment.execute_transition('Invierte los extremos.',(7,8,9))['result'],(9,7))

    def test_contradictory_schema_withdraws_meta_prior_from_future_learners(self):
        bot=Bot(); learned=teach_schema_projection(bot)
        self.assertEqual(learned['status'],'schema_learned')
        source='schema_surface:'+str(learned.get('surface'))
        self.assertTrue(bot.meta_representations.has_source(source))
        contradicted=bot.observe_schema_statement('persona ana no coordina objeto rojo en zona norte')
        self.assertEqual(contradicted['status'],'schema_contradictory')
        self.assertFalse(bot.meta_representations.has_source(source))
        rep=None
        for row in [(1,2,3),(4,5,6)]:
            rep=bot.observe_transition('Después del retiro conserva extremos.',row,(row[0],row[2]))
        self.assertEqual(rep['status'],'procedure_pending')

    def test_meta_representation_persists_and_rehydrates_consumers(self):
        bot=Bot(); teach_schema_projection(bot)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
        rows=loaded.meta_representations.rows()
        role_rows=[r for r in rows if r.get('kind')=='role_set']
        self.assertEqual(len(role_rows),1)
        self.assertEqual(role_rows[0]['roles'],[0,2])
        tr=None
        for row in [(11,22,33),(44,55,66)]:
            tr=loaded.observe_transition('Retiene bordes.',row,(row[0],row[2]))
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(loaded.execute_transition('Retiene bordes.',(7,8,9))['result'],(7,9))


if __name__=='__main__':
    unittest.main()

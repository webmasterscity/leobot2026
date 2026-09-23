import unittest
from leobot import Bot
from tests.test_meta_v59 import teach_schema_projection, symbolic_episode


class V60DependencyMetaTransferTests(unittest.TestCase):
    def test_role_relevance_prior_reduces_arithmetic_synthesis_search(self):
        treatment=Bot(); control=Bot(); teach_schema_projection(treatment)
        treatment.programs.max_candidates=150
        control.programs.max_candidates=150
        rows=[(2,10,3),(2,999,3),(4,10,3),(2,10,5)]
        tr=cr=None
        for row in rows:
            expected=(row[0]*row[2]+1,)
            tr=treatment.observe_transition('Calcula mezcla.',row,expected)
            cr=control.observe_transition('Calcula mezcla.',row,expected)
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(cr['status'],'procedure_unresolved')
        trep=tr['reports'][0]; crep=cr['reports'][0]
        self.assertEqual(trep['meta_dependency_schema'],'roles:3:0,2')
        self.assertEqual(trep['allowed_vars'],[0,2])
        self.assertEqual(crep['allowed_vars'],[0,1,2])
        self.assertLess(trep['candidates'],crep['candidates'])
        self.assertEqual(treatment.execute_transition('Calcula mezcla.',(7,123,11))['result'],(78,))

    def test_irrelevant_skill_library_cannot_override_a_confirmed_role_prior(self):
        bot=Bot(); teach_schema_projection(bot); bot.programs.max_candidates=150
        # First learn several structurally unrelated skills so the automatic
        # reusable library is non-empty and can enlarge the frontier.
        for name,idx in [('Cuadra primero.',0),('Cuadra segundo.',1),('Cuadra tercero.',2)]:
            base=[2,3,5]
            rows=[tuple(base)]
            for k in range(3):
                if k != idx:
                    r=base.copy(); r[k]+=7; rows.append(tuple(r))
            r=base.copy(); r[idx]+=2; rows.append(tuple(r))
            for row in rows:
                bot.observe_transition(name,row,(row[idx]*row[idx]+1,))
        # The new target needs roles {0,2}. If the automatic library causes a
        # budget failure, meta-control retries the same structural prior without
        # irrelevant library calls rather than discarding the useful prior.
        rows=[(2,3,5),(2,10,5),(4,3,5),(2,3,7)]
        rep=None
        for row in rows:
            rep=bot.observe_transition('Multiplica extremos.',row,(row[0]*row[2]+1,))
        self.assertEqual(rep['status'],'procedure_learned')
        detail=rep['reports'][0]
        self.assertEqual(detail.get('meta_dependency_schema'),'roles:3:0,2')
        self.assertEqual(detail.get('allowed_vars'),[0,2])
        self.assertEqual(bot.execute_transition('Multiplica extremos.',(7,123,11))['result'],(78,))

    def test_target_invariance_is_required_before_role_prior_can_restrict_search(self):
        bot=Bot(); teach_schema_projection(bot)
        rows=[(2,10,3),(2,999,3),(4,10,5),(3,4,8)]
        rep=None
        for row in rows:
            # x1 genuinely matters, so the {0,2} prior is contradicted by the
            # first invariance comparison and must not constrain synthesis.
            rep=bot.observe_transition('Suma los dos primeros.',row,(row[0]+row[1],))
        self.assertEqual(rep['status'],'procedure_learned')
        detail=rep['reports'][0]
        self.assertEqual(detail['allowed_vars'],[0,1,2])
        self.assertNotIn('meta_dependency_schema',detail)
        self.assertEqual(bot.execute_transition('Suma los dos primeros.',(7,123,11))['result'],(130,))

    def test_arithmetic_dependency_certificate_transfers_to_symbolic_action(self):
        treatment=Bot(); control=Bot()
        for row in [(2,10,3),(2,999,3),(4,10,3),(2,10,5),(3,4,8)]:
            learned=treatment.observe_transition('Calcula fuente abstracta.',row,(row[0]*row[2]+1,))
        self.assertEqual(learned['status'],'procedure_learned')
        meta=learned.get('meta_dependency_representation',{}).get('meta',{})
        self.assertEqual(meta.get('schema'),'roles:3:0,2')
        self.assertIn('roles:3:0,2',treatment.symbolic.external_role_sets)
        tr=cr=None
        for row in [('pa','sa','da',True,None),('pb','sb','db',True,None),('px','sx','dx',False,'road')]:
            tr=symbolic_episode(treatment,*row); cr=symbolic_episode(control,*row)
        self.assertEqual(tr['status'],'operator_learned')
        self.assertEqual(tr.get('precondition_mode'),'meta_role_set_transfer')
        self.assertEqual(cr['status'],'pending_support')
        for i in range(25):
            p,s,d=f'personav{i}',f'origenv{i}',f'destinov{i}'
            state={('at',p,s),('road',s,d),('person',p),('place',s),('place',d)}
            out=treatment.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state)
            self.assertEqual(out.get('status'),'executed_symbolic_action')
            self.assertIn(('at',p,d),set(out.get('result',())))

    def test_counterevidence_withdraws_dependency_certificate(self):
        bot=Bot()
        for row in [(2,10,3),(2,999,3),(4,10,3),(2,10,5),(3,4,8)]:
            learned=bot.observe_transition('Calcula fuente revocable.',row,(row[0]*row[2]+1,))
        source='procedure:'+str(learned.get('pattern'))
        self.assertTrue(bot.meta_representations.has_source(source))
        # New evidence makes x1 relevant and invalidates the old implementation.
        out=bot.observe_transition('Calcula fuente revocable.',(2,123,3),(999,))
        self.assertNotEqual(out['status'],'procedure_learned')
        self.assertFalse(bot.meta_representations.has_source(source))
        sources=bot.symbolic.external_role_sets.get('roles:3:0,2',{}).get('sources',{})
        self.assertNotIn('meta:procedure:'+source,sources)

    def test_role_prior_is_search_hint_not_completeness_restriction(self):
        bot=Bot(); teach_schema_projection(bot)
        # These observations do not provide the controlled invariance witness
        # needed to activate a dependency prior. Ordinary synthesis remains
        # available and can learn a function involving every role.
        rows=[(1,2,3),(4,5,6),(7,8,10),(2,9,4)]
        rep=None
        for row in rows:
            rep=bot.observe_transition('Suma todos.',row,(sum(row),))
        self.assertEqual(rep['status'],'procedure_learned')
        self.assertEqual(rep['reports'][0]['allowed_vars'],[0,1,2])
        self.assertEqual(bot.execute_transition('Suma todos.',(11,22,33))['result'],(66,))

    def test_role_cardinality_prior_transfers_across_unseen_arity(self):
        treatment=Bot(); control=Bot()
        # Two independent schema sources establish only the abstract fact that
        # two roles can be relevant. They do not say which positions matter in
        # the future 4-input task.
        from experiments.v59_architecture_freeze import teach_role_set
        self.assertEqual(teach_role_set(treatment,3,(0,1))['status'],'schema_learned')
        self.assertEqual(teach_role_set(treatment,4,(0,2))['status'],'schema_learned')
        treatment.programs.max_candidates=control.programs.max_candidates=150
        base=[2,3,5,7]; rows=[tuple(base)]
        for k in (1,2):
            r=base.copy(); r[k]+=11; rows.append(tuple(r))
        for k in (0,3):
            r=base.copy(); r[k]+=2; rows.append(tuple(r))
        tr=cr=None
        for row in rows:
            expected=(row[0]*row[3]+1,)
            tr=treatment.observe_transition('Calcula cruce de cuatro.',row,expected)
            cr=control.observe_transition('Calcula cruce de cuatro.',row,expected)
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertEqual(cr['status'],'procedure_unresolved')
        detail=tr['reports'][0]
        self.assertEqual(detail.get('meta_dependency_schema'),'card:2->roles:4:0,3')
        self.assertEqual(detail.get('allowed_vars'),[0,3])
        self.assertEqual(treatment.execute_transition('Calcula cruce de cuatro.',(11,99,-44,13))['result'],(144,))

    def test_role_cardinality_prior_survives_reload_and_does_not_identify_roles_by_itself(self):
        import tempfile
        from pathlib import Path
        from experiments.v59_architecture_freeze import teach_role_set
        bot=Bot(); teach_role_set(bot,3,(0,1)); teach_role_set(bot,4,(0,2))
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json'; bot.save(state); loaded=Bot.load(state)
        cards=[r for r in loaded.meta_representations.rows() if r.get('kind')=='role_cardinality']
        self.assertTrue(any(r.get('cardinality')==2 and len(r.get('sources',{}))>=2 for r in cards))
        # A target depending on three inputs must reject the two-role prior.
        loaded.programs.max_candidates=5000
        rows=[(2,3,5,7),(4,3,5,7),(2,8,5,7),(2,3,5,11),(9,4,5,6)]
        rep=None
        for row in rows:
            rep=loaded.observe_transition('Suma tres roles.',row,(row[0]+row[1]+row[3],))
        self.assertEqual(rep['status'],'procedure_learned')
        detail=rep['reports'][0]
        self.assertEqual(detail.get('allowed_vars'),[0,1,2,3])
        self.assertNotIn('meta_dependency_schema',detail)
        self.assertEqual(loaded.execute_transition('Suma tres roles.',(10,20,999,30))['result'],(60,))

if __name__=='__main__': unittest.main()

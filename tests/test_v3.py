import tempfile
import unittest
from pathlib import Path
from leobot.core import Atom, Engine
from leobot.learning import RelationalLearner
from leobot.programs import ProgramLearner, Expr
from leobot.language import Language
from leobot.diskkb import SQLiteKnowledgeBase
from leobot.scalable import ScalableBot
from leobot.bot import Bot
from leobot.core import KnowledgeBase


def chain(kb, pred='p', count=12, prefix='n'):
    for i in range(count-1):
        kb.add(Atom(pred,(f'{prefix}{i}',f'{prefix}{i+1}')))


class V3Tests(unittest.TestCase):
    def test_numeric_auto_library_reuse(self):
        p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=5)
        xs=[(2,3,1),(4,5,3),(3,7,2),(5,2,4),(7,4,6),(8,3,5)]
        for a in xs:p.add_example('base',a,a[0]*a[1]+a[2])
        self.assertEqual(p.fit('base')['status'],'learned_hypothesis')
        for a in xs:p.add_example('double',a,2*(a[0]*a[1]+a[2]))
        p.max_size=3
        r=p.fit('double') # no explicit library
        self.assertEqual(r['status'],'learned_hypothesis')
        self.assertIn('base',r['library_selected'])
        self.assertIn('base',p.dependencies['double'])
        self.assertEqual(p.predict('double',(17,19,11))['value'],668)

    def test_program_references_do_not_expand_and_invalidate(self):
        p=ProgramLearner()
        p.examples['s0']={(1,):{1}}
        p.solutions['s0']=[Expr('var',0)]
        p.dependencies['s0']=set()
        for i in range(1,200):
            name,prev=f's{i}',f's{i-1}'
            p.examples[name]={(1,):{i+1}}
            p.solutions[name]=[Expr('add',children=(Expr('call',prev),Expr('const',1)))]
            p.dependencies[name]={prev}
        self.assertEqual(p.predict('s199',(7,))['value'],206)
        self.assertLess(len(str(p.solutions['s199'][0])),20)
        p.add_example('s0',(2,),2)
        self.assertNotIn('s199',p.solutions)

    def test_iterative_skill_dag_thousands_deep(self):
        p=ProgramLearner()
        p.examples['s0']={(1,):{1}};p.solutions['s0']=[Expr('var',0)];p.dependencies['s0']=set()
        depth=3000
        for i in range(1,depth+1):
            name,prev=f's{i}',f's{i-1}'
            p.examples[name]={(1,):{i+1}}
            p.solutions[name]=[Expr('add',children=(Expr('call',prev),Expr('const',1)))]
            p.dependencies[name]={prev}
        self.assertEqual(p.predict(f's{depth}',(3,))['value'],depth+3)

    def test_relational_auto_relevance_ignores_unrelated_predicates(self):
        kb=KnowledgeBase();chain(kb,'signal',10,'n')
        kb.add_example('twice',('n0','n2'),True);kb.add_example('twice',('n2','n4'),True)
        kb.add_example('twice',('n0','n3'),False)
        for j in range(250):
            kb.add(Atom(f'junk{j}',(f'x{j}',f'y{j}')))
        r=RelationalLearner(kb,max_length=2,max_candidates=2000).fit('twice')
        self.assertEqual(r['status'],'learned_hypothesis')
        self.assertEqual(r['predicate_selected'],['signal'])
        self.assertLess(r['candidates'],100)

    def test_compiled_closure_long_chain(self):
        kb=KnowledgeBase();chain(kb,'p',8,'n')
        kb.add_example('reach',('n0','n3'),True);kb.add_example('reach',('n1','n4'),True)
        kb.add_example('reach',('n3','n1'),False)
        r=RelationalLearner(kb,max_length=1,max_pairs=1000).fit('reach',allowed=['p'])
        self.assertIn('closure(',r['selected'])
        for i in range(7,6000):kb.add(Atom('p',(f'n{i}',f'n{i+1}')))
        q=Engine(kb,max_work=10000).query(Atom('reach',('n0','n6000')))
        self.assertTrue(q['complete']);self.assertTrue(q['answers'])
        self.assertTrue(q['stats'].get('compiled'))
        self.assertLessEqual(q['stats']['work'],6000)

    def test_compositional_paraphrase(self):
        l=Language()
        f=lambda who:{'act':'query','pred':'vive','args':[who,'?lugar']}
        l.teach('¿Dónde vive Ana?',f('ana'))
        l.teach('¿Dónde reside Bruno?',f('bruno'))
        l.teach('¿En qué ciudad vive Carla?',f('carla'))
        out=l.parse('¿En qué ciudad reside Diego?')
        self.assertEqual(out['status'],'parsed')
        self.assertTrue(out['composed_paraphrase'])
        self.assertEqual(out['frame']['args'][0],'diego')


    def test_generic_recurrence_discovers_factorial(self):
        p=ProgramLearner(max_size=7,max_seconds=3)
        for x,y in [(1,1),(2,2),(3,6),(4,24),(5,120),(6,720)]:p.add_example('seq',(x,),y)
        r=p.fit('seq')
        self.assertTrue(r.get('recurrence_discovered'))
        self.assertEqual(p.predict('seq',(8,))['value'],40320)

    def test_generic_recurrence_discovers_fibonacci(self):
        p=ProgramLearner(max_size=7,max_seconds=3)
        for x,y in [(0,0),(1,1),(2,1),(3,2),(4,3),(5,5),(6,8),(7,13)]:p.add_example('seq',(x,),y)
        r=p.fit('seq')
        self.assertTrue(r.get('recurrence_discovered'))
        self.assertEqual(p.predict('seq',(12,))['value'],144)



    def test_general_recurrence_discovers_lag3(self):
        seq=[0,1,1]
        for _ in range(3,11):seq.append(seq[-1]+seq[-3])
        p=ProgramLearner(max_size=7,max_seconds=3)
        for n,y in enumerate(seq):p.add_example('seq',(n,),y)
        r=p.fit('seq')
        self.assertTrue(r.get('recurrence_discovered'))
        self.assertIn('f(n-3)',r['programs'][0])
        self.assertEqual(p.predict('seq',(12,))['value'],41)

    def test_general_recurrence_discovers_tribonacci(self):
        seq=[0,0,1]
        for _ in range(3,11):seq.append(seq[-1]+seq[-2]+seq[-3])
        p=ProgramLearner(max_size=7,max_seconds=3)
        for n,y in enumerate(seq):p.add_example('seq',(n,),y)
        r=p.fit('seq')
        self.assertTrue(r.get('recurrence_discovered'))
        self.assertEqual(p.predict('seq',(12,))['value'],274)

    def test_recurrence_and_concepts_persist(self):
        import json
        p=ProgramLearner(max_size=7,max_seconds=3)
        p.set_concepts('seq',['series','math'])
        for x,y in [(0,0),(1,1),(2,1),(3,2),(4,3),(5,5),(6,8)]:p.add_example('seq',(x,),y)
        p.fit('seq')
        q=ProgramLearner.from_dict(json.loads(json.dumps(p.as_dict())))
        self.assertEqual(q.predict('seq',(12,))['value'],144)
        self.assertEqual(q.skill_concepts['seq'],{'series','math'})

    def test_scalable_bot_fact_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';state=Path(td)/'state.json'
            b=ScalableBot(db,allow_extensional_grounding=True)
            b.language.teach('Ana vive en Caracas.',{'act':'assert','pred':'vive','args':['ana','caracas']})
            b.language.teach('¿Dónde vive Ana?',{'act':'query','pred':'vive','args':['ana','?lugar']})
            b.respond('Eva vive en Mérida.')
            self.assertIn('merida',b.respond('¿Dónde vive Eva?')['text'])
            b.save(state);b.close()
            c=ScalableBot.load(state,db)
            try:self.assertIn('merida',c.respond('¿Dónde vive Eva?')['text'])
            finally:c.close()

    def test_sqlite_kb_works_with_engine_and_relevance(self):
        with tempfile.TemporaryDirectory() as td:
            kb=SQLiteKnowledgeBase(Path(td)/'facts.db')
            try:
                for i in range(1000):kb.add(Atom('p',(f'a{i}',f'b{i}')))
                out=Engine(kb).query(Atom('p',('a777','?x')))
                self.assertEqual(out['answers'][0].atom.args,('a777','b777'))
                self.assertEqual(kb.predicates_for_entities({'a777'}),{'p':1})
            finally:kb.close()

    def test_utility_abstraction_is_invented_and_reduces_search(self):
        samples=[(2,3,5),(4,5,7),(3,7,2),(5,2,9),(7,4,6),(8,3,1)]

        def train(auto):
            q=ProgramLearner(max_size=5,max_candidates=120000,max_seconds=5,
                             auto_abstraction=auto,auto_library_top_k=0)
            for a in samples:q.add_example('source_plus',a,a[0]*a[1]+a[2])
            q.fit('source_plus',library=[])
            for a in samples:q.add_example('source_minus',a,a[0]*a[1]-a[2])
            q.fit('source_minus',library=[])
            q.auto_library_top_k=16
            for a in samples:q.add_example('target',a,a[0]*a[1]+a[0])
            return q,q.fit('target')

        control,cr=train(False)
        learned,lr=train(True)
        self.assertEqual(cr['status'],'learned_hypothesis')
        self.assertEqual(lr['status'],'learned_hypothesis')
        self.assertTrue(any(v['program']=='(x0 * x1)' for v in learned.abstractions.values()))
        self.assertLess(lr['size'],cr['size'])
        self.assertLess(lr['candidates'],cr['candidates'])
        for x in range(11,31):
            args=(x,x+2,x-3)
            expected=args[0]*args[1]+args[0]
            self.assertEqual(learned.predict('target',args)['value'],expected)
            self.assertEqual(control.predict('target',args)['value'],expected)

    def test_utility_abstraction_can_be_latent_not_literal_subexpression(self):
        # Learned source programs need not contain the abstraction text.  The
        # utility learner derives a compact primitive from behaviour on probes.
        samples=[(2,5,3),(7,3,4),(8,11,2),(13,6,5),(4,9,7),(10,2,8)]
        p=ProgramLearner(max_size=5,max_seconds=5,auto_abstraction=True,auto_library_top_k=0)
        for a in samples:p.add_example('a',a,(a[0]-a[1])+a[2])
        ra=p.fit('a',library=[])
        for a in samples:p.add_example('b',a,(a[0]-a[1])-a[2])
        rb=p.fit('b',library=[])
        source_text=' '.join(ra['programs']+rb['programs'])
        self.assertNotIn('(x0 - x1)',source_text)
        self.assertTrue(any(v['program']=='(x0 - x1)' for v in p.abstractions.values()))

    def test_abstraction_provenance_invalidation_and_persistence(self):
        import json
        samples=[(2,3,5),(4,5,7),(3,7,2),(5,2,9),(7,4,6),(8,3,1)]
        p=ProgramLearner(max_size=5,max_seconds=5,auto_abstraction=True,auto_library_top_k=0)
        for a in samples:p.add_example('a',a,a[0]*a[1]+a[2])
        p.fit('a',library=[])
        for a in samples:p.add_example('b',a,a[0]*a[1]-a[2])
        p.fit('b',library=[])
        names=set(p.abstractions)
        self.assertTrue(names)
        q=ProgramLearner.from_dict(json.loads(json.dumps(p.as_dict())))
        self.assertEqual(set(q.abstractions),names)
        # A new observation about a source invalidates hypotheses derived from
        # that source until they are revalidated/relearned.
        p.add_example('a',(11,13,17),11*13+17)
        self.assertFalse(names & set(p.abstractions))


    def test_invented_primitive_is_parametric_across_positions_and_arity(self):
        source=[(2,3,5),(4,5,7),(3,7,2),(5,2,9),(7,4,6),(8,3,1)]
        target=[(2,3,5,7),(4,5,7,2),(3,7,2,9),(5,2,9,4),(7,4,6,3),(8,3,1,5)]
        p=ProgramLearner(max_size=5,max_seconds=5,auto_abstraction=True,auto_library_top_k=0)
        for a in source:p.add_example('a',a,a[0]*a[1]+a[2])
        p.fit('a',library=[])
        for a in source:p.add_example('b',a,a[0]*a[1]-a[2])
        p.fit('b',library=[])
        abstraction=next(v for v in p.abstractions.values() if v['program']=='(x0 * x1)')
        self.assertEqual(abstraction['arity'],2)
        p.max_size=3;p.auto_library_top_k=16
        for a in target:p.add_example('target4',a,a[2]*a[3]+a[0])
        r=p.fit('target4')
        self.assertEqual(r['status'],'learned_hypothesis')
        self.assertIn('(x2,x3)',r['programs'][0])
        self.assertEqual(p.predict('target4',(11,13,17,19))['value'],334)
        # Persistence must preserve parameterized calls and their dependencies.
        import json
        q=ProgramLearner.from_dict(json.loads(json.dumps(p.as_dict())))
        self.assertEqual(q.predict('target4',(11,13,17,19))['value'],334)


    def test_grounded_language_induction_transfers_without_frame_annotation(self):
        b=Bot(allow_extensional_grounding=True)
        b.language.teach('Ana vive en Caracas.',{'act':'assert','pred':'vive','args':['ana','caracas']})
        b.language.teach('¿Dónde vive Ana?',{'act':'query','pred':'vive','args':['ana','?answer']})
        b.kb.add(Atom('vive',('bruno','merida')),'seed')
        b.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
        self.assertEqual(b.language.parse('Bruno reside en Mérida.')['status'],'unrecognized')
        self.assertEqual(b.respond('Bruno reside en Mérida.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Eva reside en Barquisimeto.')['status'],'stored')
        induced=[e for e in b.language.examples if e.get('source')=='grounded_induction']
        self.assertGreaterEqual(len(induced),1)
        # No semantic frame is supplied for this new fact; the induced grammar
        # must transfer to new entities.
        self.assertEqual(b.respond('Diego reside en Maracay.')['status'],'stored')
        self.assertTrue(b.kb.contains(Atom('vive',('diego','maracay'))))
        # A distinct question construction also requires independent grounding.
        self.assertEqual(b.respond('¿En qué localidad reside Bruno?')['status'],'grounding_pending')
        self.assertEqual(b.respond('¿En qué localidad reside Eva?')['status'],'bindings')
        q2=b.respond('¿En qué localidad reside Diego?')
        self.assertEqual(q2['status'],'bindings')
        self.assertEqual(q2['proofs'][0]['atom']['args'],['diego','maracay'])

    def test_grounded_language_induction_abstains_when_semantics_are_ambiguous(self):
        b=Bot(allow_extensional_grounding=True)
        b.kb.add(Atom('vive',('ana','caracas')),'seed')
        b.kb.add(Atom('trabaja',('ana','acme')),'seed')
        before=len(b.language.examples)
        r=b.respond('¿Dónde está Ana?')
        self.assertEqual(r['status'],'grounding_pending')
        self.assertGreater(r['grounded_induction'].get('possible',0),1)
        self.assertEqual(len(b.language.examples),before)

    def test_grounded_language_induction_works_with_disk_memory(self):
        with tempfile.TemporaryDirectory() as td:
            b=ScalableBot(Path(td)/'facts.db',allow_extensional_grounding=True)
            try:
                b.kb.add(Atom('vive',('bruno','merida')),'seed')
                b.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
                self.assertEqual(b.respond('Bruno reside en Mérida.')['status'],'grounding_pending')
                r=b.respond('Eva reside en Barquisimeto.')
                self.assertEqual(r['status'],'stored')
                self.assertTrue(any(e.get('source')=='grounded_induction' for e in b.language.examples))
            finally:b.close()

    def test_grounded_language_does_not_promote_single_coincidence(self):
        b=Bot(allow_extensional_grounding=True)
        b.kb.add(Atom('trabaja',('bruno','acme')),'seed')
        r=b.respond('Bruno odia Acme.')
        self.assertEqual(r['status'],'grounding_pending')
        # Repeating the same evidence is not independent support.
        self.assertEqual(b.respond('Bruno odia Acme.')['status'],'grounding_pending')
        self.assertEqual(b.language.parse('Eva odia Globex.')['status'],'unrecognized')
        self.assertFalse(b.kb.contains(Atom('trabaja',('eva','globex'))))

    def test_grounded_language_promotes_after_independent_support(self):
        b=Bot(allow_extensional_grounding=True)
        b.kb.add(Atom('vive',('bruno','merida')),'seed')
        b.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
        self.assertEqual(b.respond('Bruno reside en Mérida.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Eva reside en Barquisimeto.')['status'],'stored')
        self.assertEqual(b.respond('Diego reside en Maracay.')['status'],'stored')
        self.assertTrue(b.kb.contains(Atom('vive',('diego','maracay'))))

    def test_grounded_language_supports_explicit_negative_facts(self):
        b=Bot(allow_extensional_grounding=True)
        b.kb.add(Atom('!vive',('ana','caracas')),'seed')
        b.kb.add(Atom('!vive',('bruno','merida')),'seed')
        self.assertEqual(b.respond('Ana no reside en Caracas.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Bruno no reside en Mérida.')['status'],'stored')
        self.assertEqual(b.respond('Eva no reside en Maracay.')['status'],'stored')
        self.assertTrue(b.kb.contains(Atom('!vive',('eva','maracay'))))

    def test_grounded_language_pending_state_persists(self):
        import json
        b=Bot(allow_extensional_grounding=True)
        b.kb.add(Atom('vive',('bruno','merida')),'seed')
        self.assertEqual(b.respond('Bruno reside en Mérida.')['status'],'grounding_pending')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; b.save(path); c=Bot.load(path)
            c.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
            self.assertEqual(c.respond('Eva reside en Barquisimeto.')['status'],'stored')
            self.assertEqual(c.respond('Diego reside en Maracay.')['status'],'stored')

    def test_negative_construction_beats_broader_positive_slot(self):
        b=Bot(allow_extensional_grounding=True)
        b.kb.add(Atom('vive',('bruno','merida')),'seed')
        b.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
        self.assertEqual(b.respond('Bruno reside en Mérida.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Eva reside en Barquisimeto.')['status'],'stored')
        b.kb.add(Atom('!vive',('ana','caracas')),'seed')
        b.kb.add(Atom('!vive',('pedro','valencia')),'seed')
        self.assertEqual(b.respond('Ana no reside en Caracas.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Pedro no reside en Valencia.')['status'],'stored')
        r=b.respond('Julia no reside en Maracay.')
        self.assertEqual(r['status'],'stored')
        self.assertTrue(b.kb.contains(Atom('!vive',('julia','maracay'))))
        self.assertFalse(b.kb.contains(Atom('vive',('julia no','maracay'))))

    def test_grounded_lexical_rewrite_transfers_across_acts(self):
        b=Bot(allow_extensional_grounding=True)
        for person,city in [('bruno','merida'),('eva','barquisimeto'),('luis','valencia'),('ana','caracas'),('carla','maracay')]:
            b.kb.add(Atom('vive',(person,city)),'seed')
        # Acquire two assertion constructions entirely through grounding.
        self.assertEqual(b.respond('Bruno vive en Mérida.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Eva vive en Barquisimeto.')['status'],'stored')
        self.assertEqual(b.respond('Luis reside en Valencia.')['status'],'grounding_pending')
        self.assertEqual(b.respond('Ana reside en Caracas.')['status'],'stored')
        # Acquire only the canonical question form; no "reside" question is taught.
        self.assertEqual(b.respond('¿Dónde vive Bruno?')['status'],'grounding_pending')
        self.assertEqual(b.respond('¿Dónde vive Eva?')['status'],'bindings')
        parsed=b.language.parse('¿Dónde reside Carla?')
        self.assertEqual(parsed['status'],'parsed')
        self.assertTrue(parsed['composed_paraphrase'])
        out=b.respond('¿Dónde reside Carla?')
        self.assertEqual(out['status'],'bindings')
        self.assertEqual(out['proofs'][0]['atom']['args'],['carla','maracay'])

    def test_grounded_language_resolves_ambiguity_by_version_space_intersection(self):
        b=Bot(allow_extensional_grounding=True)
        # Neither episode is individually unique: the shared surviving meaning is vive.
        for atom in [Atom('vive',('ana','caracas')),Atom('trabaja',('ana','caracas')),
                     Atom('vive',('bruno','merida')),Atom('posee',('bruno','merida'))]:
            b.kb.add(atom,'seed')
        a=b.respond('Ana está en Caracas.')
        self.assertEqual(a['status'],'grounding_pending')
        self.assertEqual(a['grounded_induction']['possible'],2)
        r=b.respond('Bruno está en Mérida.')
        self.assertEqual(r['status'],'stored')
        out=b.respond('Eva está en Valencia.')
        self.assertEqual(out['status'],'stored')
        self.assertTrue(b.kb.contains(Atom('vive',('eva','valencia'))))
        self.assertFalse(b.kb.contains(Atom('trabaja',('eva','valencia'))))
        self.assertFalse(b.kb.contains(Atom('posee',('eva','valencia'))))

    def test_scalable_grounding_hypothesis_persists_across_restart(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            b=ScalableBot(db,allow_extensional_grounding=True)
            b.kb.add(Atom('vive',('bruno','merida')),'seed')
            self.assertEqual(b.respond('Bruno reside en Mérida.')['status'],'grounding_pending')
            b.save(state); b.close()
            c=ScalableBot.load(state,db)
            try:
                c.kb.add(Atom('vive',('eva','barquisimeto')),'seed')
                self.assertEqual(c.respond('Eva reside en Barquisimeto.')['status'],'stored')
                self.assertEqual(c.respond('Diego reside en Maracay.')['status'],'stored')
            finally:c.close()


    def test_procedure_grounding_learns_numeric_parameter_without_frame(self):
        b=Bot(); b.procedures.min_support=3
        self.assertEqual(b.observe_transition('Suma 3 al valor.',(10,),(13,))['status'],'procedure_pending')
        self.assertEqual(b.observe_transition('Suma 5 al valor.',(7,),(12,))['status'],'procedure_pending')
        r=b.observe_transition('Suma 8 al valor.',(-2,),(6,))
        self.assertEqual(r['status'],'procedure_learned')
        out=b.execute_transition('Suma 11 al valor.',(31,))
        self.assertEqual(out['status'],'executed')
        self.assertEqual(out['result'],(42,))

    def test_procedure_grounding_learns_vector_state_transform(self):
        b=Bot(); b.procedures.min_support=3
        for before in [(2,9),(5,-3),(11,4)]:
            r=b.observe_transition('Intercambia los valores.',before,(before[1],before[0]))
        self.assertEqual(r['status'],'procedure_learned')
        self.assertEqual(b.execute_transition('Intercambia los valores.',(101,-7))['result'],(-7,101))

    def test_procedure_grounding_duplicate_is_not_independent_support(self):
        b=Bot(); b.procedures.min_support=3
        for _ in range(5):
            r=b.observe_transition('Suma 3 al valor.',(10,),(13,))
        self.assertEqual(r['status'],'procedure_pending')
        self.assertEqual(r['support'],1)
        self.assertTrue(r['duplicate'])

    def test_grounded_procedure_prior_skill_enables_tight_budget_transfer(self):
        samples=[(2,3,1),(4,5,3),(3,7,2),(5,2,4),(7,4,6),(8,3,5)]

        def learn_base(bot):
            bot.procedures.min_support=3
            bot.programs.max_size=5; bot.programs.max_candidates=120000; bot.programs.max_seconds=5
            for a in samples:
                rep=bot.observe_transition('Combina los valores.',a,(a[0]*a[1]+a[2],))
            self.assertEqual(rep['status'],'procedure_learned')

        transfer=Bot(); learn_base(transfer)
        transfer.programs.max_size=3; transfer.programs.max_candidates=3000; transfer.programs.max_seconds=2
        for a in samples:
            tr=transfer.observe_transition('Combina los valores y duplica el resultado.',a,(2*(a[0]*a[1]+a[2]),))
        self.assertEqual(tr['status'],'procedure_learned')
        self.assertTrue(any('proc_' in p for group in tr['programs'] for p in group))
        self.assertEqual(transfer.execute_transition('Combina los valores y duplica el resultado.',(17,19,11))['result'],(668,))

        # Same prior information and target examples, but composition/reuse disabled.
        ablated=Bot(); learn_base(ablated)
        ablated.programs.max_size=3; ablated.programs.max_candidates=3000; ablated.programs.max_seconds=2
        ablated.programs.auto_library_top_k=0
        for a in samples:
            ar=ablated.observe_transition('Combina los valores y duplica el resultado.',a,(2*(a[0]*a[1]+a[2]),))
        self.assertEqual(ar['status'],'procedure_unresolved')
        self.assertEqual(ablated.execute_transition('Combina los valores y duplica el resultado.',(17,19,11))['status'],'unknown_procedure')

    def test_grounded_procedure_persists_with_bot_and_disk_backend(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; state=Path(td)/'state.json'
            b=ScalableBot(db,allow_extensional_grounding=True); b.procedures.min_support=3
            for text,before,after in [('Suma 3 al valor.',(10,),(13,)),('Suma 5 al valor.',(7,),(12,)),('Suma 8 al valor.',(-2,),(6,))]:
                b.observe_transition(text,before,after)
            b.save(state); b.close()
            c=ScalableBot.load(state,db)
            try:
                self.assertEqual(c.execute_transition('Suma 11 al valor.',(31,))['result'],(42,))
            finally:c.close()


    def _teach_proc_family(self, bot):
        bot.procedures.min_support=3
        episodes=[
            ('Suma 3 al valor.',(10,),(13,)),('Suma 5 al valor.',(7,),(12,)),('Suma 8 al valor.',(-2,),(6,)),
            ('Añade 4 al valor.',(9,),(13,)),('Añade 6 al valor.',(1,),(7,)),('Añade 9 al valor.',(-4,),(5,)),
            ('Suma 2 a la cantidad.',(3,),(5,)),('Suma 7 a la cantidad.',(10,),(17,)),('Suma 12 a la cantidad.',(-5,),(7,)),
            ('Duplica el valor.',(3,),(6,)),('Duplica el valor.',(7,),(14,)),('Duplica el valor.',(-4,),(-8,)),
            ('Dobla el valor.',(5,),(10,)),('Dobla el valor.',(9,),(18,)),('Dobla el valor.',(-3,),(-6,)),
            ('Duplica el resultado.',(2,),(4,)),('Duplica el resultado.',(11,),(22,)),('Duplica el resultado.',(-5,),(-10,)),
        ]
        for text,before,after in episodes:
            rep=bot.observe_transition(text,before,after)
        return rep

    def test_procedure_semantic_rewrites_compose_unseen_paraphrase(self):
        b=Bot(); self._teach_proc_family(b)
        out=b.execute_transition('Añade 11 a la cantidad.',(31,))
        self.assertEqual(out['status'],'executed')
        self.assertEqual(out['result'],(42,))
        self.assertTrue(out['composed_paraphrase'])
        self.assertIn((('anade',),('suma',)),b.procedures.semantic_rewrites)
        self.assertIn((('a','la','cantidad'),('al','valor')),b.procedures.semantic_rewrites)

        control=Bot(); self._teach_proc_family(control)
        control.procedures.semantic_rewrites_enabled=False
        self.assertEqual(control.execute_transition('Añade 11 a la cantidad.',(31,))['status'],'unknown_procedure')

    def test_procedure_sequence_composes_unseen_actions_in_order(self):
        b=Bot(); self._teach_proc_family(b)
        out=b.execute_transition('Añade 11 a la cantidad y luego dobla el resultado.',(7,))
        self.assertEqual(out['status'],'executed_plan')
        self.assertEqual(out['result'],(36,))
        self.assertEqual(len(out['steps']),2)
        reverse=b.execute_transition('Dobla el resultado y luego añade 11 a la cantidad.',(7,))
        self.assertEqual(reverse['result'],(25,))
        self.assertNotEqual(out['result'],reverse['result'])

        noseq=Bot(); self._teach_proc_family(noseq)
        noseq.procedures.sequence_composition_enabled=False
        self.assertEqual(noseq.execute_transition('Añade 11 a la cantidad y luego dobla el resultado.',(7,))['status'],'unknown_procedure')

    def test_procedure_semantic_rewrite_withdraws_after_counterevidence(self):
        b=Bot(); self._teach_proc_family(b)
        self.assertEqual(b.execute_transition('Añade 11 a la cantidad.',(31,))['status'],'executed')
        # A contradictory new observation changes the learned meaning of this
        # surface family.  Previously induced rewrite evidence must not survive.
        r=b.observe_transition('Añade 10 al valor.',(1,),(100,))
        self.assertIn(r['status'],('procedure_unresolved','procedure_learned'))
        if r['status']=='procedure_unresolved':
            self.assertNotIn((('anade',),('suma',)),b.procedures.semantic_rewrites)
            self.assertEqual(b.execute_transition('Añade 11 a la cantidad.',(31,))['status'],'unknown_procedure')

    def test_procedure_semantic_rewrites_and_plans_persist(self):
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json'
            b=Bot(); self._teach_proc_family(b); b.save(state)
            c=Bot.load(state)
            out=c.execute_transition('Añade 11 a la cantidad y luego dobla el resultado.',(7,))
            self.assertEqual(out['status'],'executed_plan')
            self.assertEqual(out['result'],(36,))


    def _teach_planning_actions(self, bot, include_double=True):
        bot.procedures.min_support=3
        for x in (2,7,-3):
            bot.observe_transition('Incrementa el valor.',(x,),(x+1,))
        if include_double:
            for x in (2,5,-4):
                bot.observe_transition('Duplica el valor.',(x,),(2*x,))

    def test_grounded_actions_plan_to_unseen_goal(self):
        b=Bot(); self._teach_planning_actions(b)
        plan=b.plan_transition((1,),(15,),max_steps=6,max_nodes=1000)
        self.assertEqual(plan['status'],'plan_found')
        self.assertEqual(plan['result'],(15,))
        self.assertLessEqual(len(plan['steps']),6)
        current=(1,)
        for step in plan['steps']:
            out=b.execute_transition(step['action'],current)
            self.assertEqual(tuple(step['before']),current)
            self.assertEqual(out['result'],tuple(step['after']))
            current=out['result']
        self.assertEqual(current,(15,))

    def test_planner_uses_acquired_skill_under_tight_depth_budget(self):
        full=Bot(); control=Bot()
        self._teach_planning_actions(full,include_double=True)
        self._teach_planning_actions(control,include_double=False)
        fp=full.plan_transition((1,),(15,),max_steps=6,max_nodes=1000)
        cp=control.plan_transition((1,),(15,),max_steps=6,max_nodes=1000)
        self.assertEqual(fp['status'],'plan_found')
        self.assertEqual(cp['status'],'goal_unreached')


    def test_natural_goal_grounding_drives_planning_to_unseen_target(self):
        b=Bot(); self._teach_planning_actions(b)
        self.assertEqual(b.observe_goal('Lleva el valor a 7.',(7,))['status'],'goal_pending')
        self.assertEqual(b.observe_goal('Lleva el valor a 23.',(23,))['status'],'goal_pending')
        self.assertEqual(b.observe_goal('Lleva el valor a 41.',(41,))['status'],'goal_learned')
        plan=b.plan_goal('Lleva el valor a 15.',(1,),max_steps=6,max_nodes=1000)
        self.assertEqual(plan['status'],'plan_found')
        self.assertEqual(plan['resolved_goal'],(15,))
        self.assertEqual(plan['result'],(15,))

    def test_natural_goal_grounding_requires_independent_support_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'goal_state.json'
            b=Bot(); self._teach_planning_actions(b)
            for _ in range(4):r=b.observe_goal('Lleva el valor a 7.',(7,))
            self.assertEqual(r['status'],'goal_pending');self.assertEqual(r['support'],1)
            b.observe_goal('Lleva el valor a 23.',(23,));b.observe_goal('Lleva el valor a 41.',(41,))
            b.save(state);c=Bot.load(state)
            plan=c.plan_goal('Lleva el valor a 15.',(1,),max_steps=6,max_nodes=1000)
            self.assertEqual(plan['status'],'plan_found');self.assertEqual(plan['result'],(15,))


    def test_natural_goal_grounding_synthesizes_computed_target(self):
        b=Bot(); self._teach_planning_actions(b)
        self.assertEqual(b.observe_goal('Lleva el valor a 2 más que 5.',(7,))['status'],'goal_pending')
        self.assertEqual(b.observe_goal('Lleva el valor a 3 más que 8.',(11,))['status'],'goal_pending')
        self.assertEqual(b.observe_goal('Lleva el valor a 4 más que 10.',(14,))['status'],'goal_learned')
        resolved=b.procedures.resolve_goal('Lleva el valor a 6 más que 9.')
        self.assertEqual(resolved['status'],'goal_resolved');self.assertEqual(resolved['goal'],(15,))
        plan=b.plan_goal('Lleva el valor a 6 más que 9.',(1,),max_steps=6,max_nodes=1000)
        self.assertEqual(plan['status'],'plan_found');self.assertEqual(plan['result'],(15,))


    def test_planner_does_not_invent_parameters_for_parameterized_actions(self):
        b=Bot(); b.procedures.min_support=3
        for text,before,after in [('Suma 3 al valor.',(10,),(13,)),('Suma 5 al valor.',(7,),(12,)),('Suma 8 al valor.',(-2,),(6,))]:
            b.observe_transition(text,before,after)
        plan=b.plan_transition((1,),(5,),max_steps=4,max_nodes=100)
        self.assertEqual(plan['status'],'no_actions')

    def test_unknown_natural_goal_is_not_guessed(self):
        b=Bot(); self._teach_planning_actions(b)
        out=b.plan_goal('Quiero algo completamente nuevo.',(1,),max_steps=6,max_nodes=100)
        self.assertEqual(out['status'],'unknown_goal')
        self.assertIsNone(out['result'])


    @staticmethod
    def _symbolic_state(*facts):
        return {tuple(f) for f in facts}

    def _teach_symbolic_move(self, b):
        F=lambda *x: tuple(x); S=self._symbolic_state
        for person,src,dst in [('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','cuarto','laboratorio')]:
            before=S(F('at',person,src),F('road',src,dst),F('autorizado',person),F('person',person),F('place',src),F('place',dst))
            after=(before-{F('at',person,src)})|{F('at',person,dst)}
            b.observe_symbolic_transition(f'Mueve a {person} de {src} a {dst}.',before,after)
        # Counterexample missing road while preserving spurious correlates.
        before=S(F('at','lila','patio'),F('autorizado','lila'),F('person','lila'),F('place','patio'),F('place','taller'))
        b.observe_symbolic_transition('Mueve a lila de patio a taller.',before,before)
        # Counterexample missing at(person, source), also preserving spurious correlates.
        before=S(F('road','cocina','plaza'),F('autorizado','hugo'),F('person','hugo'),F('at','hugo','cuarto'),F('place','cocina'),F('place','plaza'),F('place','cuarto'))
        b.observe_symbolic_transition('Mueve a hugo de cocina a plaza.',before,before)

    def _teach_symbolic_pickup(self, b):
        F=lambda *x: tuple(x); S=self._symbolic_state
        for person,item,loc in [('ana','caja','bodega'),('bruno','libro','biblioteca'),('carla','llave','taller')]:
            before=S(F('at',person,loc),F('item_at',item,loc),F('entrenado',person),F('person',person),F('item',item),F('place',loc))
            after=(before-{F('item_at',item,loc)})|{F('holding',person,item)}
            b.observe_symbolic_transition(f'{person} toma {item} en {loc}.',before,after)
        before=S(F('at','diego','garaje'),F('entrenado','diego'),F('person','diego'),F('item','mapa'),F('place','garaje'))
        b.observe_symbolic_transition('diego toma mapa en garaje.',before,before)
        before=S(F('item_at','carta','salon'),F('entrenado','eva'),F('person','eva'),F('item','carta'),F('place','salon'),F('at','eva','patio'),F('place','patio'))
        b.observe_symbolic_transition('eva toma carta en salon.',before,before)

    def test_symbolic_action_induction_uses_counterexamples_to_remove_spurious_preconditions(self):
        b=Bot();self._teach_symbolic_move(b)
        ops=b.symbolic.operators();self.assertEqual(len(ops),1)
        self.assertEqual(set(ops[0]['preconditions']),{('at','<e0>','<e1>'),('road','<e1>','<e2>')})
        self.assertNotIn(('autorizado','<e0>'),ops[0]['preconditions'])
        state=self._symbolic_state(('at','nora','casa'),('road','casa','plaza'),('person','nora'),('place','casa'),('place','plaza'))
        out=b.execute_symbolic_transition('Mueve a Nora de casa a plaza.',state)
        self.assertEqual(out['status'],'executed_symbolic_action')
        self.assertIn(('at','nora','plaza'),out['result'])

    def test_symbolic_world_cross_operator_plan_transfers_to_new_entities(self):
        b=Bot();self._teach_symbolic_move(b);self._teach_symbolic_pickup(b)
        S=self._symbolic_state
        b.observe_symbolic_goal('Logra que Ana tenga caja.',S(('holding','ana','caja')))
        b.observe_symbolic_goal('Logra que Bruno tenga libro.',S(('holding','bruno','libro')))
        state=S(('at','nora','casa'),('road','casa','plaza'),('road','plaza','bodega'),
                ('item_at','paquete','bodega'),('person','nora'),('item','paquete'),
                ('place','casa'),('place','plaza'),('place','bodega'))
        out=b.plan_symbolic_goal('Logra que Nora tenga paquete.',state,max_steps=5,max_nodes=1000)
        self.assertEqual(out['status'],'plan_found');self.assertEqual(len(out['steps']),3)
        self.assertIn(('holding','nora','paquete'),out['result'])
        self.assertNotIn(('item_at','paquete','bodega'),out['result'])

    def test_symbolic_planner_does_not_ignore_learned_preconditions(self):
        b=Bot();self._teach_symbolic_pickup(b)
        S=self._symbolic_state
        state=S(('at','nora','casa'),('item_at','paquete','bodega'),('person','nora'),('item','paquete'),('place','casa'),('place','bodega'))
        out=b.execute_symbolic_transition('Nora toma paquete en bodega.',state)
        self.assertEqual(out['status'],'unknown_or_inapplicable_action')
        self.assertNotIn(('holding','nora','paquete'),out['result'])

    def test_symbolic_world_persists_with_bot(self):
        with tempfile.TemporaryDirectory() as td:
            state_path=Path(td)/'symbolic.json'
            b=Bot();self._teach_symbolic_move(b);self._teach_symbolic_pickup(b)
            S=self._symbolic_state
            b.observe_symbolic_goal('Logra que Ana tenga caja.',S(('holding','ana','caja')))
            b.observe_symbolic_goal('Logra que Bruno tenga libro.',S(('holding','bruno','libro')))
            b.save(state_path);c=Bot.load(state_path)
            world=S(('at','nora','casa'),('road','casa','bodega'),('item_at','paquete','bodega'),('person','nora'),('item','paquete'),('place','casa'),('place','bodega'))
            out=c.plan_symbolic_goal('Logra que Nora tenga paquete.',world,max_steps=3,max_nodes=100)
            self.assertEqual(out['status'],'plan_found');self.assertIn(('holding','nora','paquete'),out['result'])

    def test_symbolic_unknown_goal_is_not_invented(self):
        b=Bot();self._teach_symbolic_move(b)
        out=b.plan_symbolic_goal('Haz algo completamente distinto.',{('at','nora','casa')},max_steps=3,max_nodes=100)
        self.assertEqual(out['status'],'unknown_symbolic_goal')



    def test_symbolic_alias_reorders_roles_and_reuses_prior_operator(self):
        full=Bot();control=Bot();self._teach_symbolic_move(full)
        F=lambda *x:tuple(x);S=self._symbolic_state
        for person,src,dst in [('marta','patio','escuela'),('leo','garaje','parque')]:
            before=S(F('at',person,src),F('road',src,dst),F('person',person),F('place',src),F('place',dst))
            after=(before-{F('at',person,src)})|{F('at',person,dst)}
            full.observe_symbolic_transition(f'Desde {src} lleva a {person} hasta {dst}.',before,after)
            control.observe_symbolic_transition(f'Desde {src} lleva a {person} hasta {dst}.',before,after)
        self.assertEqual(len(full.symbolic.aliases()),1)
        self.assertEqual(len(control.symbolic.aliases()),0)
        state=S(F('at','nora','casa'),F('road','casa','plaza'),F('person','nora'),F('place','casa'),F('place','plaza'))
        self.assertEqual(full.execute_symbolic_transition('Desde casa lleva a Nora hasta plaza.',state)['status'],'executed_symbolic_action')
        self.assertEqual(control.execute_symbolic_transition('Desde casa lleva a Nora hasta plaza.',state)['status'],'unknown_or_inapplicable_action')

    def test_symbolic_alias_counterevidence_withdraws_surface(self):
        b=Bot();self._teach_symbolic_move(b);F=lambda *x:tuple(x);S=self._symbolic_state
        for person,src,dst in [('marta','patio','escuela'),('leo','garaje','parque')]:
            before=S(F('at',person,src),F('road',src,dst),F('person',person),F('place',src),F('place',dst));after=(before-{F('at',person,src)})|{F('at',person,dst)}
            b.observe_symbolic_transition(f'Desde {src} lleva a {person} hasta {dst}.',before,after)
        before=S(F('at','olga','cocina'),F('road','cocina','patio'),F('person','olga'),F('place','cocina'),F('place','patio'))
        after=before|{F('visited','olga','patio')}
        r=b.observe_symbolic_transition('Desde cocina lleva a Olga hasta patio.',before,after)
        self.assertIn(r['status'],('alias_withdrawn_by_counterevidence','alias_conflict'))
        self.assertEqual(b.symbolic.aliases(),[])

    def test_symbolic_alias_persists(self):
        with tempfile.TemporaryDirectory() as td:
            b=Bot();self._teach_symbolic_move(b);F=lambda *x:tuple(x);S=self._symbolic_state
            for person,src,dst in [('marta','patio','escuela'),('leo','garaje','parque')]:
                before=S(F('at',person,src),F('road',src,dst),F('person',person),F('place',src),F('place',dst));after=(before-{F('at',person,src)})|{F('at',person,dst)}
                b.observe_symbolic_transition(f'Desde {src} lleva a {person} hasta {dst}.',before,after)
            path=Path(td)/'alias.json';b.save(path);c=Bot.load(path)
            state=S(F('at','nora','casa'),F('road','casa','plaza'),F('person','nora'),F('place','casa'),F('place','plaza'))
            out=c.execute_symbolic_transition('Desde casa lleva a Nora hasta plaza.',state)
            self.assertEqual(out['status'],'executed_symbolic_action');self.assertIn(F('at','nora','plaza'),out['result'])


    def test_symbolic_world_persists_with_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json';b=ScalableBot(db,allow_extensional_grounding=True)
            self._teach_symbolic_move(b);self._teach_symbolic_pickup(b);S=self._symbolic_state
            b.observe_symbolic_goal('Logra que Ana tenga caja.',S(('holding','ana','caja')))
            b.observe_symbolic_goal('Logra que Bruno tenga libro.',S(('holding','bruno','libro')))
            b.save(side);b.close();c=ScalableBot.load(side,db)
            world=S(('at','nora','casa'),('road','casa','bodega'),('item_at','paquete','bodega'),('person','nora'),('item','paquete'),('place','casa'),('place','bodega'))
            out=c.plan_symbolic_goal('Logra que Nora tenga paquete.',world,max_steps=3,max_nodes=100)
            self.assertEqual(out['status'],'plan_found');c.close()


    def _teach_symbolic_drop(self, b):
        F=lambda *x:tuple(x);S=self._symbolic_state
        for person,item,loc in [('ana','caja','oficina'),('bruno','libro','casa'),('carla','llave','biblioteca')]:
            before=S(F('at',person,loc),F('holding',person,item),F('person',person),F('item',item),F('place',loc))
            after=(before-{F('holding',person,item)})|{F('item_at',item,loc)}
            b.observe_symbolic_transition(f'{person} deja {item} en {loc}.',before,after)

    def _teach_delivery_macro(self, b):
        self._teach_symbolic_move(b);self._teach_symbolic_pickup(b);self._teach_symbolic_drop(b)
        F=lambda *x:tuple(x);S=self._symbolic_state
        reports=[]
        for k in range(3):
            person,item,home,store,dest=f'persona{k}',f'objeto{k}',f'inicio{k}',f'tienda{k}',f'destino{k}'
            state=S(F('at',person,home),F('road',home,store),F('road',store,dest),F('item_at',item,store),
                    F('person',person),F('item',item),F('place',home),F('place',store),F('place',dest))
            goal=S(F('item_at',item,dest))
            reports.append(b.learn_symbolic_macro(state,goal,max_steps=6,max_nodes=5000))
        return reports

    def test_symbolic_macro_is_induced_from_independent_primitive_plans(self):
        b=Bot();reports=self._teach_delivery_macro(b)
        self.assertEqual(reports[0]['learning']['status'],'macro_pending')
        self.assertEqual(reports[1]['learning']['status'],'macro_pending')
        self.assertEqual(reports[2]['learning']['status'],'macro_learned')
        macros=b.symbolic.macros();self.assertEqual(len(macros),1)
        self.assertEqual(macros[0]['primitive_length'],4)
        self.assertEqual(macros[0]['support'],3)
        # The macro is not an episodic cache: its schema contains role markers,
        # not any concrete entity from the three training worlds.
        dumped=str(macros[0])
        self.assertNotIn('persona0',dumped);self.assertNotIn('objeto0',dumped)

    def test_symbolic_macro_reduces_search_depth_and_nodes_on_new_entities(self):
        b=Bot();self._teach_delivery_macro(b);F=lambda *x:tuple(x);S=self._symbolic_state
        person='nora';i1='paquete';i2='carta';home='casa';s1='bodega';d1='oficina';s2='tienda';d2='escuela'
        state=S(F('at',person,home),F('road',home,s1),F('road',s1,d1),F('item_at',i1,s1),
                F('road',d1,s2),F('road',s2,d2),F('item_at',i2,s2),F('person',person),F('item',i1),F('item',i2),
                F('place',home),F('place',s1),F('place',d1),F('place',s2),F('place',d2))
        goal=S(F('item_at',i1,d1),F('item_at',i2,d2))
        tight_control=b.plan_symbolic(state,goal,max_steps=2,max_nodes=5000,use_macros=False)
        tight_full=b.plan_symbolic(state,goal,max_steps=2,max_nodes=5000,use_macros=True)
        self.assertEqual(tight_control['status'],'goal_unreached')
        self.assertEqual(tight_full['status'],'plan_found')
        self.assertEqual(tight_full['hierarchical_steps'],2);self.assertEqual(tight_full['primitive_steps'],8)
        self.assertEqual(tight_full['macro_steps'],2)
        deep_control=b.plan_symbolic(state,goal,max_steps=8,max_nodes=50000,use_macros=False)
        deep_full=b.plan_symbolic(state,goal,max_steps=8,max_nodes=50000,use_macros=True)
        self.assertEqual(deep_control['status'],'plan_found');self.assertEqual(deep_full['status'],'plan_found')
        self.assertLess(deep_full['nodes'],deep_control['nodes'])
        self.assertIn(F('item_at',i1,d1),deep_full['result']);self.assertIn(F('item_at',i2,d2),deep_full['result'])

    def test_symbolic_macro_requires_distinct_role_instances_and_invalidates_with_dependency(self):
        b=Bot();self._teach_symbolic_move(b);self._teach_symbolic_pickup(b);self._teach_symbolic_drop(b)
        F=lambda *x:tuple(x);S=self._symbolic_state
        state=S(F('at','ana','casa'),F('road','casa','tienda'),F('road','tienda','oficina'),F('item_at','caja','tienda'),F('person','ana'),F('item','caja'),F('place','casa'),F('place','tienda'),F('place','oficina'))
        goal=S(F('item_at','caja','oficina'))
        first=b.learn_symbolic_macro(state,goal,max_steps=6,max_nodes=5000)
        self.assertEqual(first['learning']['status'],'macro_pending')
        for _ in range(5):
            dup=b.learn_symbolic_macro(state,goal,max_steps=6,max_nodes=5000)
            self.assertEqual(dup['learning']['status'],'duplicate_macro_episode')
        self.assertEqual(len(b.symbolic.macros()),0)
        # Add two independent supports to promote.
        for k in (1,2):
            st=S(F('at',f'p{k}',f'h{k}'),F('road',f'h{k}',f's{k}'),F('road',f's{k}',f'd{k}'),F('item_at',f'i{k}',f's{k}'),F('person',f'p{k}'),F('item',f'i{k}'),F('place',f'h{k}'),F('place',f's{k}'),F('place',f'd{k}'))
            b.learn_symbolic_macro(st,S(F('item_at',f'i{k}',f'd{k}')),max_steps=6,max_nodes=5000)
        self.assertEqual(len(b.symbolic.macros()),1)
        # Counterevidence changes the learned move model, so its dependent macro
        # must not remain executable under a stale operator fingerprint.
        before=S(F('at','zoe','x'),F('road','x','y'))
        after=(before-{F('at','zoe','x')})|{F('at','zoe','y'),F('visited','zoe','y')}
        b.observe_symbolic_transition('Mueve a zoe de x a y.',before,after)
        self.assertEqual(len(b.symbolic.macros()),0)

    def test_symbolic_macro_persists_and_expands_to_auditable_primitives(self):
        with tempfile.TemporaryDirectory() as td:
            b=Bot();self._teach_delivery_macro(b);path=Path(td)/'macro.json';b.save(path);c=Bot.load(path)
            self.assertEqual(len(c.symbolic.macros()),1)
            F=lambda *x:tuple(x);S=self._symbolic_state
            state=S(F('at','nora','casa'),F('road','casa','bodega'),F('road','bodega','oficina'),F('item_at','paquete','bodega'),F('person','nora'),F('item','paquete'),F('place','casa'),F('place','bodega'),F('place','oficina'))
            goal=S(F('item_at','paquete','oficina'))
            out=c.plan_symbolic(state,goal,max_steps=1,max_nodes=100,use_macros=True)
            self.assertEqual(out['status'],'plan_found');self.assertEqual(out['macro_steps'],1)
            self.assertEqual(len(out['steps'][0]['expanded_steps']),4)
            # Replaying the four primitive actions is represented explicitly for audit.
            self.assertEqual([st['kind'] for st in out['steps'][0]['expanded_steps']],['primitive']*4)


    def test_symbolic_hierarchy_rollout_scales_long_monotonic_goal_chain(self):
        b=Bot();self._teach_delivery_macro(b);F=lambda *x:tuple(x);S=self._symbolic_state
        person='nora';current='inicio';facts={F('at',person,current),F('person',person),F('place',current)};goal=set()
        for j in range(32):
            store=f'tienda_larga_{j}';dest=f'destino_largo_{j}';item=f'objeto_largo_{j}'
            facts.update({F('road',current,store),F('road',store,dest),F('item_at',item,store),F('item',item),F('place',store),F('place',dest)})
            goal.add(F('item_at',item,dest));current=dest
        out=b.plan_symbolic(frozenset(facts),frozenset(goal),max_steps=32,max_nodes=64,use_macros=True)
        self.assertEqual(out['status'],'plan_found');self.assertEqual(out.get('strategy'),'hierarchical_rollout')
        self.assertEqual(out['nodes'],32);self.assertEqual(out['macro_steps'],32);self.assertEqual(out['primitive_steps'],128)


    def test_symbolic_hierarchy_ambiguous_fast_path_falls_back_without_guessing(self):
        b=Bot();self._teach_delivery_macro(b);F=lambda *x:tuple(x);S=self._symbolic_state
        state=S(F('at','nora','hub'),F('road','hub','tienda_a'),F('road','tienda_a','dest_a'),F('item_at','a','tienda_a'),
                F('road','hub','tienda_b'),F('road','tienda_b','dest_b'),F('item_at','b','tienda_b'),
                F('road','dest_a','tienda_b'),F('person','nora'),F('item','a'),F('item','b'),
                F('place','hub'),F('place','tienda_a'),F('place','dest_a'),F('place','tienda_b'),F('place','dest_b'))
        goal=S(F('item_at','a','dest_a'),F('item_at','b','dest_b'))
        out=b.plan_symbolic(state,goal,max_steps=3,max_nodes=1000,use_macros=True)
        self.assertEqual(out['status'],'plan_found')
        self.assertNotEqual(out.get('strategy'),'hierarchical_rollout')
        self.assertEqual(out['macro_steps'],2)


    def _symbolic_chain_world(self, prefix, length, branches=0):
        F=lambda *x:tuple(x);person=f'persona_{prefix}';facts={F('at',person,f'{prefix}_0'),F('person',person)}
        for i in range(length):
            src,dst=f'{prefix}_{i}',f'{prefix}_{i+1}'
            facts.update({F('road',src,dst),F('place',src),F('place',dst)})
            for j in range(branches):
                dead=f'{prefix}_dead_{i}_{j}';facts.update({F('road',src,dead),F('place',dead)})
        return frozenset(facts),frozenset({F('at',person,f'{prefix}_{length}')})

    def _teach_iterative_move(self, b):
        self._teach_symbolic_move(b);reports=[]
        for idx,length in enumerate((2,3,4)):
            state,goal=self._symbolic_chain_world(f'train_iter_{idx}',length)
            reports.append(b.learn_symbolic_iteration(state,goal,max_steps=8,max_nodes=1000))
        return reports

    def test_iterative_skill_learns_only_after_variable_length_support_and_transfers_far_beyond_training(self):
        b=Bot();reports=self._teach_iterative_move(b)
        self.assertEqual(reports[0]['learning']['status'],'iteration_pending')
        self.assertEqual(reports[1]['learning']['status'],'iteration_pending')
        self.assertEqual(reports[2]['learning']['status'],'iteration_learned')
        skill=b.symbolic.iterative_skills()[0]
        self.assertEqual(skill['training_lengths'],[2,3,4])
        state,goal=self._symbolic_chain_world('heldout_iter',25,branches=1)
        full=b.plan_symbolic(state,goal,max_steps=1,max_nodes=10,use_macros=False,use_iterations=True,max_iterative_steps=100)
        control=b.plan_symbolic(state,goal,max_steps=1,max_nodes=1000,use_macros=False,use_iterations=False)
        self.assertEqual(full['status'],'plan_found');self.assertEqual(full['strategy'],'iterative_closure')
        self.assertEqual(full['primitive_steps'],25);self.assertEqual(len(full['steps'][0]['expanded_steps']),25)
        self.assertEqual(control['status'],'goal_unreached')

    def test_iterative_skill_same_length_only_does_not_claim_variable_length_abstraction(self):
        b=Bot();self._teach_symbolic_move(b)
        for idx in range(3):
            state,goal=self._symbolic_chain_world(f'same_len_{idx}',3)
            report=b.learn_symbolic_iteration(state,goal,max_steps=5,max_nodes=1000)['learning']
        self.assertEqual(report['status'],'iteration_pending')
        self.assertEqual(report['lengths'],[3]);self.assertEqual(b.symbolic.iterative_skills(),[])

    def test_iterative_skill_invalidates_when_base_operator_changes(self):
        b=Bot();self._teach_iterative_move(b);self.assertEqual(len(b.symbolic.iterative_skills()),1)
        F=lambda *x:tuple(x);S=self._symbolic_state
        before=S(F('at','zoe','x'),F('road','x','y'),F('person','zoe'),F('place','x'),F('place','y'))
        after=(before-{F('at','zoe','x')})|{F('at','zoe','y'),F('visited','zoe','y')}
        b.observe_symbolic_transition('Mueve a zoe de x a y.',before,after)
        self.assertEqual(b.symbolic.iterative_skills(),[])

    def test_iterative_skill_persists_and_keeps_expanded_trace(self):
        with tempfile.TemporaryDirectory() as td:
            b=Bot();self._teach_iterative_move(b);path=Path(td)/'iterative.json';b.save(path);c=Bot.load(path)
            self.assertEqual(len(c.symbolic.iterative_skills()),1)
            state,goal=self._symbolic_chain_world('persist_iter',12)
            out=c.plan_symbolic(state,goal,max_steps=1,max_nodes=10,use_macros=False,use_iterations=True,max_iterative_steps=50)
            self.assertEqual(out['status'],'plan_found');self.assertEqual(out['primitive_steps'],12)
            self.assertEqual(len(out['steps'][0]['expanded_steps']),12)


    def _teach_named_concept_world(self, b):
        # Two latent relations coexist so alias induction must discriminate
        # between previously learned concepts rather than map every new phrase
        # to the only available relation.
        facts=[
            ('parent',('ana','beto')),('parent',('beto','carla')),
            ('parent',('diego','elena')),('parent',('elena','fabio')),
            ('parent',('gina','hugo')),('parent',('hugo','ines')),
            ('parent',('juan','kira')),('parent',('kira','luis')),
            ('friend',('gina','oscar')),('friend',('juan','paula')),
            ('friend',('marta','nora')),('friend',('leo','olga')),
        ]
        for pred,args in facts:b.kb.add(Atom(pred,args))
        for text in ('Ana enlaza a Carla.','Diego enlaza a Fabio.',
                     'Gina no enlaza a Oscar.','Juan no enlaza a Paula.'):
            last_a=b.observe_concept_statement(text)
        for text in ('Marta empareja con Nora.','Leo empareja con Olga.',
                     'Ana no empareja con Carla.','Diego no empareja con Fabio.'):
            last_b=b.observe_concept_statement(text)
        return last_a,last_b

    def test_concept_grounder_invents_opaque_relation_and_transfers(self):
        b=Bot();a,_=self._teach_named_concept_world(b)
        self.assertEqual(a['status'],'concept_learned')
        self.assertTrue(a['target'].startswith('concept_'))
        self.assertEqual(a['learning']['selected'],'parent ; parent')
        # The natural phrase names no pre-existing KB predicate.
        self.assertNotIn('enlaza',b.kb.arity)
        self.assertEqual(b.query_concept('Gina enlaza a Ines?')['status'],'entailed')
        self.assertEqual(b.query_concept('Juan enlaza a Luis?')['status'],'entailed')
        # Open-world distinction: an unsupported pair remains unknown, not false.
        self.assertEqual(b.query_concept('Ana enlaza a Oscar?')['status'],'unknown')

    def test_concept_prior_skill_reduces_examples_for_new_surface(self):
        full=Bot();self._teach_named_concept_world(full)
        # A new wording gets one positive and one explicit negative episode.  The
        # prior concept makes one root relation uniquely compatible.
        r1=full.observe_concept_statement('Gina conecta de lejos con Ines.')
        r2=full.observe_concept_statement('Marta no conecta de lejos con Nora.')
        self.assertEqual(r1['status'],'concept_pending')
        self.assertEqual(r2['status'],'concept_alias_learned')
        self.assertEqual(full.query_concept('Juan conecta de lejos con Luis?')['status'],'entailed')

        # Same two utterances from scratch cannot invent a new relation because
        # the normal concept learner requires 2 positive + 2 negative examples.
        control=Bot()
        for fact in full.kb.facts.values():
            atom=fact['atom']
            if not atom.pred.startswith('concept_'):
                control.kb.add(atom,'control')
        c1=control.observe_concept_statement('Gina conecta de lejos con Ines.')
        c2=control.observe_concept_statement('Marta no conecta de lejos con Nora.')
        self.assertEqual(c1['status'],'concept_pending')
        self.assertEqual(c2['status'],'concept_pending')
        self.assertEqual(control.query_concept('Juan conecta de lejos con Luis?')['status'],'concept_unknown')

    def test_concept_alias_counterevidence_withdraws_only_alias(self):
        b=Bot();self._teach_named_concept_world(b)
        b.observe_concept_statement('Gina conecta de lejos con Ines.')
        self.assertEqual(b.observe_concept_statement('Marta no conecta de lejos con Nora.')['status'],'concept_alias_learned')
        root_before=b.query_concept('Juan enlaza a Luis?')['status']
        bad=b.observe_concept_statement('Leo conecta de lejos con Olga.')
        self.assertEqual(bad['status'],'concept_alias_withdrawn')
        self.assertEqual(b.query_concept('Juan conecta de lejos con Luis?')['status'],'concept_unknown')
        self.assertEqual(b.query_concept('Juan enlaza a Luis?')['status'],root_before)

    def test_concept_grounder_persists_and_works_through_conversation(self):
        with tempfile.TemporaryDirectory() as td:
            b=Bot();self._teach_named_concept_world(b)
            path=Path(td)/'concepts.json';b.save(path);c=Bot.load(path)
            out=c.respond('¿Gina enlaza a Ines?')
            self.assertEqual(out['status'],'entailed')
            self.assertIn('deducir',out['text'])
            # Learning a new wording uses the normal conversation route too.
            self.assertEqual(c.respond('Gina conecta de lejos con Ines.')['status'],'concept_pending')
            self.assertEqual(c.respond('Marta no conecta de lejos con Nora.')['status'],'concept_alias_learned')
            self.assertEqual(c.respond('¿Juan conecta de lejos con Luis?')['status'],'entailed')



    def test_concept_grounder_discovers_inverse_relation_on_distinct_structure(self):
        b=Bot()
        for pred,args in [('teach',('mentor1','alumno1')),('teach',('mentor2','alumno2')),
                          ('teach',('mentor3','alumno3')),('other',('x1','y1')),('other',('x2','y2'))]:
            b.kb.add(Atom(pred,args))
        reports=[b.observe_concept_statement(t) for t in (
            'Alumno1 sigue a Mentor1.','Alumno2 sigue a Mentor2.',
            'X1 no sigue a Y1.','X2 no sigue a Y2.')]
        self.assertEqual(reports[-1]['status'],'concept_learned')
        self.assertEqual(reports[-1]['learning']['selected'],'inverse(teach)')
        self.assertEqual(b.query_concept('Alumno3 sigue a Mentor3?')['status'],'entailed')

    def test_concept_grounder_persists_with_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'concepts.db';side=Path(td)/'concepts.json';b=ScalableBot(db,allow_extensional_grounding=True)
            for pred,args in [('edge',('ana','beto')),('edge',('beto','carla')),
                              ('edge',('diego','elena')),('edge',('elena','fabio')),
                              ('other',('gina','oscar')),('other',('juan','paula'))]:
                b.kb.add(Atom(pred,args))
            for text in ('Ana relaciona con Carla.','Diego relaciona con Fabio.',
                         'Gina no relaciona con Oscar.','Juan no relaciona con Paula.'):
                last=b.observe_concept_statement(text)
            self.assertEqual(last['status'],'concept_learned')
            b.save(side);b.close();c=ScalableBot.load(side,db)
            self.assertEqual(c.query_concept('Ana relaciona con Carla?')['status'],'entailed')
            c.close()



    def test_invented_concept_becomes_primitive_for_higher_order_concept(self):
        def add_alt_world(bot):
            for prefix in ('a','b','c','d','e','f'):
                ns=[f'{prefix}{i}' for i in range(5)]
                bot.kb.add(Atom('r',(ns[0],ns[1])));bot.kb.add(Atom('s',(ns[1],ns[2])))
                bot.kb.add(Atom('r',(ns[2],ns[3])));bot.kb.add(Atom('s',(ns[3],ns[4])))
            for x,y in (('n1','n2'),('n3','n4'),('n5','n6'),('n7','n8')):
                bot.kb.add(Atom('other',(x,y)))

        full=Bot();full.concepts.max_relation_length=2;full.concepts.allow_predicate_invention=False;add_alt_world(full)
        for text in ('A0 enlaza a A2.','B0 enlaza a B2.',
                     'N1 no enlaza a N2.','N3 no enlaza a N4.'):
            base=full.observe_concept_statement(text)
        self.assertEqual(base['learning']['selected'],'r ; s')
        for text in ('C0 abarca a C4.','D0 abarca a D4.',
                     'N5 no abarca a N6.','N7 no abarca a N8.'):
            higher=full.observe_concept_statement(text)
        self.assertEqual(higher['status'],'concept_learned')
        self.assertIn(base['target'],higher['learning']['selected'])
        self.assertEqual(full.query_concept('E0 abarca a E4?')['status'],'entailed')

        control=Bot();control.concepts.max_relation_length=2;control.concepts.allow_predicate_invention=False;add_alt_world(control)
        for text in ('C0 abarca a C4.','D0 abarca a D4.',
                     'N5 no abarca a N6.','N7 no abarca a N8.'):
            no_library=control.observe_concept_statement(text)
        self.assertEqual(no_library['status'],'concept_unresolved')
        self.assertEqual(control.query_concept('E0 abarca a E4?')['status'],'concept_unknown')



    def _add_predicate_invention_world(self, b):
        for prefix in ('a','b','c','d','e'):
            ns=[f'{prefix}{i}' for i in range(5)]
            b.kb.add(Atom('r',(ns[0],ns[1])));b.kb.add(Atom('s',(ns[1],ns[2])))
            b.kb.add(Atom('r',(ns[2],ns[3])));b.kb.add(Atom('s',(ns[3],ns[4])))
        for prefix in ('u','v','w','z'):
            ns=[f'{prefix}x{i}' for i in range(4)]
            b.kb.add(Atom('r',(ns[0],ns[1])));b.kb.add(Atom('s',(ns[1],ns[2])));b.kb.add(Atom('t',(ns[2],ns[3])))
        for x,y in (('n1','n2'),('n3','n4'),('n5','n6'),('n7','n8')):
            b.kb.add(Atom('other',(x,y)))

    def test_predicate_invention_solves_target_beyond_direct_depth_budget(self):
        b=Bot();b.concepts.max_relation_length=2;self._add_predicate_invention_world(b)
        for text in ('A0 abarca a A4.','B0 abarca a B4.',
                     'N1 no abarca a N2.','N3 no abarca a N4.'):
            learned=b.observe_concept_statement(text)
        self.assertEqual(learned['status'],'concept_learned')
        report=learned['learning']
        self.assertTrue(report['predicate_invention_used'])
        self.assertTrue(report['invented_predicate'].startswith('invent_'))
        self.assertIn(report['invented_predicate'],report['selected'])
        self.assertEqual(b.query_concept('E0 abarca a E4?')['status'],'entailed')

        control=Bot();control.concepts.max_relation_length=2;control.concepts.allow_predicate_invention=False
        self._add_predicate_invention_world(control)
        for text in ('A0 abarca a A4.','B0 abarca a B4.',
                     'N1 no abarca a N2.','N3 no abarca a N4.'):
            failed=control.observe_concept_statement(text)
        self.assertEqual(failed['status'],'concept_unresolved')
        self.assertEqual(control.query_concept('E0 abarca a E4?')['status'],'concept_unknown')

    def test_invented_predicate_transfers_to_different_concept_without_new_invention(self):
        b=Bot();b.concepts.max_relation_length=2;self._add_predicate_invention_world(b)
        for text in ('A0 abarca a A4.','B0 abarca a B4.',
                     'N1 no abarca a N2.','N3 no abarca a N4.'):
            first=b.observe_concept_statement(text)
        helper=first['learning']['invented_predicate']
        b.concepts.allow_predicate_invention=False
        for text in ('Ux0 alcanza a Ux3.','Vx0 alcanza a Vx3.',
                     'N5 no alcanza a N6.','N7 no alcanza a N8.'):
            second=b.observe_concept_statement(text)
        self.assertEqual(second['status'],'concept_learned')
        self.assertIn(helper,second['learning']['selected'])
        self.assertEqual(b.query_concept('Wx0 alcanza a Wx3?')['status'],'entailed')

        c=Bot();c.concepts.max_relation_length=2;c.concepts.allow_predicate_invention=False
        self._add_predicate_invention_world(c)
        for text in ('Ux0 alcanza a Ux3.','Vx0 alcanza a Vx3.',
                     'N5 no alcanza a N6.','N7 no alcanza a N8.'):
            baseline=c.observe_concept_statement(text)
        self.assertEqual(baseline['status'],'concept_unresolved')
        self.assertEqual(c.query_concept('Wx0 alcanza a Wx3?')['status'],'concept_unknown')

    def test_failed_predicate_invention_does_not_leave_helpers_installed(self):
        b=Bot();b.concepts.max_relation_length=1
        for pred,args in [('r',('a','b')),('s',('c','d')),('other',('x','y')),('other',('u','v'))]:
            b.kb.add(Atom(pred,args))
        # No path in the world can explain these labels.
        for text in ('A mezcla con D.','C mezcla con B.','X no mezcla con Y.','U no mezcla con V.'):
            out=b.observe_concept_statement(text)
        self.assertIn(out['status'],('concept_unresolved','concept_learned'))
        if out['status']=='concept_unresolved':
            self.assertFalse(any(r.head.pred.startswith('invent_') for r in b.kb.rules.values()))



if __name__=='__main__':unittest.main()

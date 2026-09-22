from __future__ import annotations
import json
from pathlib import Path
import random
import tempfile
import unittest
from leobot import Atom, Rule, KnowledgeBase, Engine
from leobot.core import unify
from leobot.learning import RelationalLearner
from leobot.programs import ProgramLearner, Expr
from leobot.language import Language
from leobot.bot import Bot

ROOT = Path(__file__).resolve().parents[1]


def chain(kb, pred='p', count=7, prefix='n'):
    for i in range(count - 1):
        kb.add(Atom(pred, (f'{prefix}{i}', f'{prefix}{i+1}')))


def distance_examples(kb, target, distance, count=7, prefix='n'):
    for i in range(count):
        for j in range(count):
            kb.add_example(target, (f'{prefix}{i}', f'{prefix}{j}'), j - i == distance)


def closure_rules(target='r', base='p', origin='taught'):
    return [Rule('base', Atom(target, ('?x','?y')), (Atom(base, ('?x','?y')),), origin),
            Rule('rec', Atom(target, ('?x','?y')), (Atom(base, ('?x','?z')), Atom(target, ('?z','?y'))), origin)]


class CoreTests(unittest.TestCase):
    def test_atom_invalid(self):
        for bad in ('a-b', 'a()', 'a;rm', ''):
            with self.assertRaises(ValueError): Atom(bad, ('x',))

    def test_parse_atom(self):
        self.assertEqual(Atom.parse(' p(algo, ?y) '), Atom('p', ('algo','?y')))

    def test_unification_repeated_variable(self):
        self.assertIsNone(unify(('?x','?x'), ('a','b')))
        self.assertEqual(unify(('?x','?x'), ('a','a')), {'?x':'a'})

    def test_unsafe_rule_rejected(self):
        with self.assertRaises(ValueError): Rule('x', Atom('p', ('?x',)), (Atom('q', ('?y',)),))

    def test_unknown_is_not_false(self):
        self.assertEqual(Engine(KnowledgeBase()).answer(Atom('p', ('a','b')))['status'], 'unknown')

    def test_explicit_negative(self):
        kb=KnowledgeBase(); kb.add(Atom('!p', ('a','b')))
        self.assertEqual(Engine(kb).answer(Atom('p', ('a','b')))['status'], 'refuted')

    def test_conflict_and_no_explosion(self):
        kb=KnowledgeBase()
        kb.add(Atom('p', ('a','b'))); kb.add(Atom('!p', ('a','b')))
        e=Engine(kb)
        self.assertEqual(e.answer(Atom('p', ('a','b')))['status'], 'conflict')
        self.assertEqual(e.answer(Atom('anything', ('x','y')))['status'], 'unknown')

    def test_conflict_propagates(self):
        kb=KnowledgeBase()
        kb.add(Atom('p', ('a','b'))); kb.add(Atom('!p', ('a','b')))
        kb.add_rule(Rule('q', Atom('q', ('?x','?y')), (Atom('p', ('?x','?y')),)))
        self.assertEqual(Engine(kb).answer(Atom('q', ('a','b')))['status'], 'contested')

    def test_derived_conflict_propagates(self):
        kb=KnowledgeBase(); kb.add(Atom('p', ('a','b')))
        kb.add_rule(Rule('no',Atom('!p', ('?x','?y')), (Atom('p', ('?x','?y')),)))
        kb.add_rule(Rule('q',Atom('q', ('?x','?y')), (Atom('p', ('?x','?y')),)))
        self.assertEqual(Engine(kb).answer(Atom('q', ('a','b')))['status'], 'contested')

    def test_multiple_sources(self):
        kb=KnowledgeBase(); a=Atom('p', ('a','b'))
        f1=kb.add(a,'s1'); f2=kb.add(a,'s2')
        self.assertNotEqual(f1,f2)
        kb.remove(f1)
        self.assertTrue(kb.contains(a))

    def test_duplicate_does_not_grow(self):
        kb=KnowledgeBase(); a=Atom('p', ('a','b'))
        x=kb.add(a,'s1'); before=kb.stats()
        self.assertEqual(kb.add(a,'s1'),x)
        self.assertEqual(kb.stats(),before)

    def test_arity_validated(self):
        kb=KnowledgeBase(); kb.add(Atom('p', ('a','b')))
        with self.assertRaises(ValueError): kb.add(Atom('p', ('a',)))
        with self.assertRaises(ValueError): Engine(kb).query(Atom('p', ('a','b','c')))

    def test_rule_transactional_validation(self):
        kb=KnowledgeBase(); kb.add(Atom('p', ('a','b')))
        with self.assertRaises(ValueError): kb.add_rule(Rule('bad',Atom('new', ('?x',)), (Atom('p', ('?x',)),)))
        self.assertNotIn('new', kb.arity)
        self.assertNotIn('bad', kb.rules)

    def test_correction_and_recomputation(self):
        kb=KnowledgeBase(); fid=kb.add(Atom('p', ('a','b')))
        kb.add_rule(Rule('q',Atom('q', ('?x','?y')), (Atom('p', ('?x','?y')),)))
        e=Engine(kb)
        self.assertEqual(e.answer(Atom('q', ('a','b')))['status'],'supported')
        kb.replace(fid,Atom('p', ('a','c')))
        self.assertEqual(e.answer(Atom('q', ('a','b')))['status'],'unknown')
        self.assertEqual(e.answer(Atom('q', ('a','c')))['status'],'supported')

    def test_failed_correction_preserves_original(self):
        kb=KnowledgeBase(); fid=kb.add(Atom('p', ('a','b')))
        with self.assertRaises(ValueError): kb.replace(fid,Atom('p', ('a',)))
        self.assertIn(fid,kb.facts)

    def test_budget_is_not_negative(self):
        kb=KnowledgeBase(); chain(kb)
        for r in closure_rules(): kb.add_rule(r)
        result=Engine(kb,max_work=3).answer(Atom('r', ('n0','n6')))
        self.assertEqual(result['status'],'incomplete')

    def test_recursive_chain(self):
        kb=KnowledgeBase(); chain(kb,count=15)
        for r in closure_rules(): kb.add_rule(r)
        result=Engine(kb).query(Atom('r', ('n0','?y')))
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['answers']),14)

    def test_recursive_cycle_terminates(self):
        kb=KnowledgeBase(); kb.add(Atom('p',('a','b')));kb.add(Atom('p',('b','a')))
        for r in closure_rules(): kb.add_rule(r)
        result=Engine(kb).query(Atom('r', ('a','?y')))
        self.assertTrue(result['complete'])
        self.assertEqual({p.atom.args[1] for p in result['answers']},{'a','b'})

    def test_round_memoization_preserves_recursive_answers(self):
        kb=KnowledgeBase()
        for x,y in [('a','b'),('a','c'),('b','c'),('c','a'),('c','d'),('d','e')]:
            kb.add(Atom('p',(x,y)))
        for rule in closure_rules():kb.add_rule(rule)
        for start in 'abcde':
            answers=[]
            for mode in (False,True):
                result=Engine(kb,reuse_within_round=mode).query(Atom('r',(start,'?y')))
                self.assertTrue(result['complete'])
                answers.append({p.atom.args for p in result['answers']})
            self.assertEqual(answers[0],answers[1])

    def test_round_memoization_reduces_redundant_work(self):
        kb=KnowledgeBase()
        for x in range(7):
            for y in range(7):
                if x!=y:kb.add(Atom('p',(str(x),str(y))))
        for rule in closure_rules():kb.add_rule(rule)
        slow=Engine(kb,reuse_within_round=False).query(Atom('r',('0','?y')))
        fast=Engine(kb,reuse_within_round=True).query(Atom('r',('0','?y')))
        self.assertTrue(fast['complete'])
        self.assertEqual(len(fast['answers']),7)
        self.assertLess(fast['stats']['work'],slow['stats']['work'])

    def test_mutual_recursion(self):
        kb=KnowledgeBase();kb.add(Atom('a',('x',)))
        kb.add_rule(Rule('ab',Atom('b',('?x',)),(Atom('a',('?x',)),)))
        kb.add_rule(Rule('ba',Atom('a',('?x',)),(Atom('b',('?x',)),)))
        self.assertEqual(Engine(kb).answer(Atom('b',('x',)))['status'],'supported')

    def test_join_repeated_variables(self):
        kb=KnowledgeBase();kb.add(Atom('p',('a','b')));kb.add(Atom('p',('b','a')));kb.add(Atom('p',('b','c')))
        kb.add_rule(Rule('r',Atom('r',('?x','?y')),(Atom('p',('?x','?y')),Atom('p',('?y','?x')))))
        self.assertEqual({p.atom.args for p in Engine(kb).query(Atom('r',('?x','?y')))['answers']},{('a','b'),('b','a')})

    def test_random_graphs_against_independent_bfs(self):
        rng=random.Random(17)
        for case in range(20):
            nodes=[str(i) for i in range(7)]
            graph={x:{y for y in nodes if rng.random()<0.16} for x in nodes}
            kb=KnowledgeBase()
            for x,ys in graph.items():
                for y in ys: kb.add(Atom('p',(x,y)))
            for r in closure_rules():kb.add_rule(r)
            for root in nodes:
                reached, pending=set(), list(graph[root])
                while pending:
                    x=pending.pop()
                    if x not in reached: reached.add(x);pending.extend(graph[x])
                result=Engine(kb).query(Atom('r',(root,'?y')))
                self.assertTrue(result['complete'])
                self.assertEqual({p.atom.args[1] for p in result['answers']},reached)

    def test_serialization_preserves_ids_and_proofs(self):
        kb=KnowledgeBase(); f=kb.add(Atom('p',('a','b'))); kb.add(Atom('p',('b','c')));kb.remove(f);kb.add(Atom('p',('c','d')))
        copy=KnowledgeBase.from_dict(json.loads(json.dumps(kb.as_dict())))
        self.assertEqual(copy.as_dict(),kb.as_dict())
        self.assertEqual(copy.add(Atom('p',('new','data'))),'f4')


class RelationalTests(unittest.TestCase):
    def test_learns_not_retrieves(self):
        kb=KnowledgeBase();chain(kb);distance_examples(kb,'q',2)
        r=RelationalLearner(kb,max_length=2).fit('q')
        self.assertEqual(r['selected'],'p ; p')
        self.assertFalse(any(f['atom'].pred=='q' for f in kb.facts.values()))
        kb.add(Atom('p',('new_a','new_b')));kb.add(Atom('p',('new_b','new_c')))
        ans=Engine(kb).answer(Atom('q',('new_a','new_c')))
        self.assertEqual(ans['status'],'hypothesis')
        self.assertTrue(ans['positive']['answers'][0].children)

    def test_names_do_not_select_solutions(self):
        kb=KnowledgeBase();chain(kb,pred='zz_837');distance_examples(kb,'unknown_837',2)
        r=RelationalLearner(kb,max_length=2).fit('unknown_837')
        self.assertEqual(r['selected'],'zz_837 ; zz_837')

    def test_inverse(self):
        kb=KnowledgeBase();chain(kb)
        for i in range(7):
            for j in range(7):kb.add_example('q',(f'n{i}',f'n{j}'),i-j==1)
        r=RelationalLearner(kb,max_length=2).fit('q')
        self.assertEqual(r['selected'],'inverse(p)')

    def test_two_distinct_predicates(self):
        kb=KnowledgeBase();kb.add(Atom('p',('a','b')));kb.add(Atom('r',('b','c')))
        kb.add(Atom('p',('d','e')));kb.add(Atom('r',('e','f')))
        for x,y,label in [('a','c',True),('d','f',True),('a','b',False),('b','c',False),('c','a',False)]:kb.add_example('q',(x,y),label)
        r=RelationalLearner(kb,max_length=2).fit('q')
        self.assertEqual(r['selected'],'p ; r')

    def test_learns_recursion(self):
        kb=KnowledgeBase();chain(kb,count=6)
        for i in range(6):
            for j in range(6):kb.add_example('q',(f'n{i}',f'n{j}'),j>i)
        r=RelationalLearner(kb,max_length=2).fit('q')
        self.assertEqual(r['selected'],'closure(p)')
        chain(kb,count=13,prefix='new')
        self.assertTrue(Engine(kb).query(Atom('q',('new0','new12')))['answers'])

    def test_library_reuse_and_ablation(self):
        kb=KnowledgeBase();chain(kb,count=9);distance_examples(kb,'twice',2,count=9);distance_examples(kb,'four',4,count=9)
        no_lib=RelationalLearner(kb,max_length=2).fit('four',allowed=['p'])
        self.assertEqual(no_lib['status'],'no_solution')
        RelationalLearner(kb,max_length=2).fit('twice',allowed=['p'])
        with_lib=RelationalLearner(kb,max_length=2).fit('four',allowed=['p','twice'])
        self.assertEqual(with_lib['selected'],'twice ; twice')
        self.assertTrue(with_lib['used_learned_library'])

    def test_contradictory_example_withdraws_dependents(self):
        kb=KnowledgeBase();chain(kb,count=9);distance_examples(kb,'twice',2,count=9);distance_examples(kb,'four',4,count=9)
        RelationalLearner(kb,max_length=2).fit('twice',allowed=['p'])
        RelationalLearner(kb,max_length=2).fit('four',allowed=['p','twice'])
        kb.add_example('twice',('n0','n2'),False)
        self.assertFalse(kb.rules)
        self.assertEqual(RelationalLearner(kb).fit('twice')['status'],'contradictory_examples')

    def test_duplicate_example_keeps_rule(self):
        kb=KnowledgeBase();chain(kb);distance_examples(kb,'q',2)
        RelationalLearner(kb,max_length=2).fit('q')
        before=kb.stats()
        self.assertFalse(kb.add_example('q',('n0','n2'),True))
        self.assertEqual(before,kb.stats())

    def test_no_positives(self):
        kb=KnowledgeBase();kb.add_example('q',('a','b'),False)
        self.assertEqual(RelationalLearner(kb).fit('q')['status'],'need_positive_examples')

    def test_search_budget_reported(self):
        kb=KnowledgeBase();chain(kb);distance_examples(kb,'q',2)
        r=RelationalLearner(kb,max_candidates=1).fit('q')
        self.assertFalse(r['search_complete'])


class ProgramTests(unittest.TestCase):
    def test_ambiguity_and_counterexample(self):
        p=ProgramLearner();p.add_example('f',(2,),4);p.fit('f')
        self.assertEqual(p.predict('f',(3,))['status'],'ambiguous')
        self.assertIsNotNone(p.request_example('f'))
        p.add_example('f',(3,),6);p.fit('f')
        self.assertEqual(p.predict('f',(71,))['value'],142)

    def test_goal_join_matches_enumeration_on_small_problems(self):
        rng = random.Random(404)
        oracles = [lambda x: x[0] + x[1], lambda x: x[0] * x[1],
                   lambda x: min(x), lambda x: max(x), lambda x: x[0] - x[1],
                   lambda x: x[0] // x[1], lambda x: x[0] % x[1]]
        for oracle in oracles:
            examples = [(rng.randint(-7,7), rng.choice([-3,-2,-1,1,2,3])) for _ in range(7)]
            learners = [ProgramLearner(max_size=5, goal_directed=mode) for mode in (False,True)]
            for learner in learners:
                for a in examples:learner.add_example('f',a,oracle(a))
                learner.fit('f')
            for x in range(-9,10):
                for y in (-5,-2,2,5):
                    left = {e.run((x,y)) for e in learners[0].solutions.get('f',[])}
                    right = {e.run((x,y)) for e in learners[1].solutions.get('f',[])}
                    self.assertEqual(left,right)

    def test_goal_constraints_solve_composed_program(self):
        rng=random.Random(43)
        p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=5,goal_directed=True)
        for _ in range(12):
            a=tuple(rng.randint(-6,9) for _ in range(4))
            p.add_example('f',a,(a[0]+a[1])*(a[2]-a[3]))
        report=p.fit('f')
        self.assertTrue(report['goal_join_solved'])
        self.assertEqual(p.predict('f',(23,91,-75,17))['value'],-10488)

    def test_numeric_contradiction(self):
        p=ProgramLearner();p.add_example('f',(2,),4);p.fit('f');p.add_example('f',(2,),9)
        self.assertEqual(p.fit('f')['status'],'contradictory_examples')
        self.assertEqual(p.predict('f',(3,))['status'],'contradictory_examples')

    def test_numeric_duplicate(self):
        p=ProgramLearner();p.add_example('f',(2,),4);p.fit('f')
        self.assertFalse(p.add_example('f',(2,),4))
        self.assertIn('f',p.solutions)

    def test_numeric_generalization(self):
        p=ProgramLearner()
        for args in [(2,3,1),(4,5,3),(3,7,2),(5,2,4)]:p.add_example('f',args,args[0]*args[1]+args[2])
        report=p.fit('f')
        self.assertEqual(report['status'],'learned_hypothesis')
        self.assertEqual(p.predict('f',(17,19,11))['value'],334)


    def test_learned_program_library_reuse(self):
        p=ProgramLearner(max_size=7,max_candidates=120000,max_seconds=5)
        examples=[(2,3,1),(4,5,3),(3,7,2),(5,2,4),(7,4,6),(8,3,5)]
        for a in examples:
            p.add_example('base3',a,a[0]*a[1]+a[2])
        self.assertEqual(p.fit('base3')['status'],'learned_hypothesis')
        for a in examples:
            p.add_example('double_base3',a,2*(a[0]*a[1]+a[2]))
        p.max_size=3
        no_lib=p.fit('double_base3', library=[])
        self.assertEqual(no_lib['status'],'no_solution')
        with_lib=p.fit('double_base3', library=['base3'])
        self.assertEqual(with_lib['status'],'learned_hypothesis')
        self.assertGreater(with_lib['library_seeded'],0)
        self.assertEqual(p.predict('double_base3',(17,19,11))['value'],668)

    def test_division_by_zero(self):
        e=Expr('floordiv',children=(Expr('var',0),Expr('var',1)))
        self.assertIsNone(e.run((1,0)))

    def test_no_eval_injection(self):
        with self.assertRaises(ValueError):Expr('__import__')
        with self.assertRaises(ValueError):ProgramLearner().add_example('x;print(1)',(1,),2)

    def test_numeric_limits(self):
        p=ProgramLearner()
        with self.assertRaises(ValueError):p.add_example('f',(2.5,),4)
        with self.assertRaises(ValueError):p.add_example('f',(10**15,),2)
        p.add_example('f',(1,),2)
        with self.assertRaises(ValueError):p.add_example('f',(1,2),3)

    def test_numeric_resource_limit(self):
        p=ProgramLearner(max_candidates=1)
        p.add_example('f',(2,),7)
        self.assertFalse(p.fit('f')['search_complete'])

    def test_persistence_numeric(self):
        p=ProgramLearner();p.add_example('f',(2,),4);p.add_example('f',(3,),6);p.fit('f')
        q=ProgramLearner.from_dict(json.loads(json.dumps(p.as_dict())))
        self.assertEqual(q.predict('f',(91,))['value'],182)


class LanguageTests(unittest.TestCase):
    def test_new_entities(self):
        l=Language();l.teach('Ana vive en Caracas.',{'act':'assert','pred':'p','args':['ana','caracas']})
        self.assertEqual(l.parse('Leonardo vive en Nueva York.')['frame']['args'],['leonardo','nueva york'])

    def test_question_slot(self):
        l=Language();l.teach('¿Dónde vive Ana?',{'act':'query','pred':'p','args':['ana','?lugar']})
        self.assertEqual(l.parse('¿Dónde vive Leonardo?')['frame']['args'],['leonardo','?lugar'])

    def test_unknown_paraphrase_honestly_rejected(self):
        l=Language();l.teach('¿Dónde vive Ana?',{'act':'query','pred':'p','args':['ana','?lugar']})
        self.assertEqual(l.parse('¿Cuál es la residencia actual de Ana?')['status'],'unrecognized')

    def test_ambiguous_annotations(self):
        l=Language()
        l.teach('Ana vio a Bruno.',{'act':'assert','pred':'p','args':['ana','bruno']})
        l.teach('Ana vio a Bruno.',{'act':'assert','pred':'q','args':['ana','bruno']})
        self.assertEqual(l.parse('Eva vio a Luis.')['status'],'ambiguous')

    def test_alignment_rejects_missing_value(self):
        with self.assertRaises(ValueError):Language().teach('Hola Ana',{'act':'assert','pred':'p','args':['bruno']})

    def test_duplicate_construction(self):
        l=Language();f={'act':'assert','pred':'p','args':['ana','bruno']}
        self.assertTrue(l.teach('Ana vio a Bruno',f))
        self.assertFalse(l.teach('Eva vio a Luis',{'act':'assert','pred':'p','args':['eva','luis']}))

    def test_render_composes_from_slots(self):
        l=Language();l.teach('Ana vive en Caracas.',{'act':'assert','pred':'p','args':['ana','caracas']})
        self.assertEqual(l.describe('p',('eva','maracaibo')),'eva vive en maracaibo')

    def test_correction_multiturn(self):
        b=Bot();b.ingest(json.loads((ROOT/'examples/curso_inicial.json').read_text()))
        b.respond('La reunión es el jueves.')
        self.assertIn('jueves',b.respond('¿Cuándo es la reunión?')['text'])
        b.respond('No, era el viernes.')
        self.assertIn('viernes',b.respond('¿Cuándo es la reunión?')['text'])
        self.assertEqual(b.answer_atom(Atom('fecha',('la reunion','jueves')))['status'],'unknown')

    def test_teach_paraphrase_changes_coverage(self):
        b=Bot()
        text='¿Cuál es el paradero de Eva?'
        self.assertEqual(b.respond(text)['status'],'unrecognized')
        b.language.teach('¿Cuál es el paradero de Ana?',{'act':'query','pred':'ubicacion','args':['ana','?lugar']})
        b.kb.add(Atom('ubicacion',('eva','merida')))
        self.assertIn('merida',b.respond(text)['text'])

    def test_bot_round_trip(self):
        b=Bot();b.ingest(json.loads((ROOT/'examples/curso_inicial.json').read_text()))
        b.respond('La entrega es el jueves.');b.respond('No, era el viernes.')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json';b.save(path);other=Bot.load(path)
            self.assertIn('viernes',other.respond('¿Cuándo es la entrega?')['text'])
            self.assertEqual(other.programs.predict('doble',(101,))['value'],202)

    def test_no_history_to_correct(self):
        b=Bot();b.language.teach('No, era el viernes.',{'act':'correct_last','slot':1,'value':'viernes'})
        self.assertEqual(b.respond('No, era el jueves.')['status'],'unknown')

    def test_long_input_guard(self):
        self.assertEqual(Language().parse('a'*3000)['status'],'unrecognized')


if __name__=='__main__': unittest.main()

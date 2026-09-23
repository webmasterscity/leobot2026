import tempfile
import unittest
from pathlib import Path

from leobot import Bot

F=lambda *x:tuple(x)
S=lambda *x:set(x)


def teach_move(bot: Bot):
    bot.symbolic.min_support=3
    for p,s,d in [('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','cuarto','laboratorio')]:
        before=S(F('at',p,s),F('road',s,d),F('autorizado',p),F('person',p),F('place',s),F('place',d))
        after=(before-{F('at',p,s)})|{F('at',p,d)}
        bot.observe_symbolic_transition(f'Mueve a {p} de {s} a {d}.',before,after)
    before=S(F('at','lila','patio'),F('autorizado','lila'),F('person','lila'),F('place','patio'),F('place','taller'))
    bot.observe_symbolic_transition('Mueve a lila de patio a taller.',before,before)
    before=S(F('road','cocina','plaza'),F('autorizado','hugo'),F('at','hugo','cuarto'),F('person','hugo'),F('place','cocina'),F('place','plaza'),F('place','cuarto'))
    bot.observe_symbolic_transition('Mueve a hugo de cocina a plaza.',before,before)


def nav_episode(bot: Bot,p,s,d,success=True,ambiguous_context=False):
    before=S(F('located',p,s),F('link',s,d),F('licensed',p),F('person',p),F('place',s),F('place',d))
    if ambiguous_context: before.add(F('permit_path',s,d))
    after=(before-{F('located',p,s)})|{F('located',p,d)} if success else before
    return bot.observe_symbolic_transition(f'Navega a {p} de {s} a {d}.',before,after)


class V4AnalogyTests(unittest.TestCase):
    def test_structural_analogy_reduces_support_with_renamed_predicates(self):
        b=Bot();teach_move(b)
        self.assertEqual(nav_episode(b,'nora','uno','dos')['status'],'pending_support')
        r=nav_episode(b,'omar','tres','cuatro')
        self.assertEqual(r['status'],'operator_learned')
        self.assertEqual(r['precondition_mode'],'analogical_transfer')
        self.assertIn('mueve a <e0> de <e1> a <e2>',r['analogy_sources'])
        st=S(F('located','paz','x','') ) if False else S(F('located','paz','x'),F('link','x','y'),F('person','paz'),F('place','x'),F('place','y'))
        out=b.execute_symbolic_transition('Navega a paz de x a y.',st)
        self.assertEqual(out['status'],'executed_symbolic_action')
        self.assertIn(F('located','paz','y'),out['result'])

    def test_same_two_episodes_do_not_teach_fresh_bot(self):
        b=Bot()
        nav_episode(b,'nora','uno','dos');r=nav_episode(b,'omar','tres','cuatro')
        self.assertEqual(r['status'],'pending_support')
        st=S(F('located','paz','x'),F('link','x','y'),F('person','paz'),F('place','x'),F('place','y'))
        self.assertNotEqual(b.execute_symbolic_transition('Navega a paz de x a y.',st)['status'],'executed_symbolic_action')

    def test_analogy_refuses_ambiguous_context_shape(self):
        b=Bot();teach_move(b)
        nav_episode(b,'nora','uno','dos',ambiguous_context=True)
        r=nav_episode(b,'omar','tres','cuatro',ambiguous_context=True)
        self.assertEqual(r['status'],'pending_support')
        self.assertFalse(any(op['pattern'].startswith('navega a ') for op in b.symbolic.operators()))

    def test_counterevidence_withdraws_analogical_operator(self):
        b=Bot();teach_move(b)
        nav_episode(b,'nora','uno','dos');nav_episode(b,'omar','tres','cuatro')
        self.assertTrue(any(op.get('precondition_mode')=='analogical_transfer' for op in b.symbolic.operators()))
        # All predicted preconditions hold but the action is observed not to change state.
        r=nav_episode(b,'paz','cinco','seis',success=False)
        self.assertNotEqual(r.get('status'),'operator_learned')
        self.assertFalse(any(op['pattern'].startswith('navega a ') for op in b.symbolic.operators()))

    def test_analogical_operator_persists(self):
        b=Bot();teach_move(b);nav_episode(b,'nora','uno','dos');nav_episode(b,'omar','tres','cuatro')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json';b.save(p);c=Bot.load(p)
            op=[x for x in c.symbolic.operators() if x['pattern'].startswith('navega a ')][0]
            self.assertEqual(op['precondition_mode'],'analogical_transfer')
            st=S(F('located','paz','x'),F('link','x','y'),F('person','paz'),F('place','x'),F('place','y'))
            self.assertEqual(c.execute_symbolic_transition('Navega a paz de x a y.',st)['status'],'executed_symbolic_action')

    def test_structural_analogy_transfers_second_operator_family(self):
        b=Bot();teach_move(b)
        # Also teach a pickup-like source operator independently.
        for p0,item,loc in [('ana','caja','bodega'),('bruno','libro','biblioteca'),('carla','llave','taller')]:
            before=S(F('at',p0,loc),F('item_at',item,loc),F('person',p0),F('item',item),F('place',loc))
            after=(before-{F('item_at',item,loc)})|{F('holding',p0,item)}
            b.observe_symbolic_transition(f'{p0} toma {item} en {loc}.',before,after)
        # Contrastive failures remove spurious unary type preconditions.
        before=S(F('at','diego','garaje'),F('person','diego'),F('item','mapa'),F('place','garaje'))
        b.observe_symbolic_transition('diego toma mapa en garaje.',before,before)
        before=S(F('item_at','carta','salon'),F('person','eva'),F('item','carta'),F('place','salon'),F('at','eva','patio'),F('place','patio'))
        b.observe_symbolic_transition('eva toma carta en salon.',before,before)
        def obs(p0,tok,loc):
            before=S(F('positioned',p0,loc),F('token_at',tok,loc),F('certified',p0),F('person',p0),F('token',tok),F('place',loc))
            after=(before-{F('token_at',tok,loc)})|{F('possesses',p0,tok)}
            return b.observe_symbolic_transition(f'{p0} recolecta {tok} en {loc}.',before,after)
        obs('nora','t1','l1');r=obs('omar','t2','l2')
        self.assertEqual(r['status'],'operator_learned')
        self.assertEqual(r['precondition_mode'],'analogical_transfer')
        self.assertIn('<e0> toma <e1> en <e2>',r['analogy_sources'])
        st=S(F('positioned','paz','l3'),F('token_at','t3','l3'),F('person','paz'),F('token','t3'),F('place','l3'))
        out=b.execute_symbolic_transition('paz recolecta t3 en l3.',st)
        self.assertEqual(out['status'],'executed_symbolic_action')
        self.assertIn(F('possesses','paz','t3'),out['result'])

    def test_two_prior_domains_reduce_third_domain_to_one_success(self):
        b=Bot();teach_move(b)
        def nav(p0,s,d):
            before=S(F('located',p0,s),F('link',s,d),F('licensed',p0),F('person',p0),F('place',s),F('place',d))
            after=(before-{F('located',p0,s)})|{F('located',p0,d)}
            return b.observe_symbolic_transition(f'Navega a {p0} de {s} a {d}.',before,after)
        nav('nora','n1','n2');nav('omar','n3','n4')
        before=S(F('positioned','paz','p1'),F('path','p1','p2'),F('cleared','paz'),F('person','paz'),F('place','p1'),F('place','p2'))
        after=(before-{F('positioned','paz','p1')})|{F('positioned','paz','p2')}
        r=b.observe_symbolic_transition('Desplaza a paz desde p1 hasta p2.',before,after)
        self.assertEqual(r['status'],'operator_learned')
        self.assertEqual(r['precondition_mode'],'analogical_transfer')
        self.assertGreaterEqual(r['analogy_source_count'],2)
        st=S(F('positioned','luz','q1'),F('path','q1','q2'),F('person','luz'),F('place','q1'),F('place','q2'))
        self.assertEqual(b.execute_symbolic_transition('Desplaza a luz desde q1 hasta q2.',st)['status'],'executed_symbolic_action')
        control=Bot();teach_move(control)
        rc=control.observe_symbolic_transition('Desplaza a paz desde p1 hasta p2.',before,after)
        self.assertEqual(rc['status'],'pending_support')


if __name__=='__main__':unittest.main()

class V41MetaSchemaTests(unittest.TestCase):
    def test_meta_schema_consolidates_many_domains_with_bounded_source_evidence(self):
        b=Bot();teach_move(b)
        nav_episode(b,'nora','uno','dos');r=nav_episode(b,'omar','tres','cuatro')
        self.assertEqual(r['status'],'operator_learned')
        self.assertEqual(len(b.symbolic.structural_schemas()),1)
        for idx in range(30):
            pos=f'posx{idx}';edge=f'edgex{idx}';p=f'p{idx}';s=f's{idx}';d=f'd{idx}'
            before=S(F(pos,p,s),F(edge,s,d),F('person',p),F('place',s),F('place',d))
            after=(before-{F(pos,p,s)})|{F(pos,p,d)}
            rr=b.observe_symbolic_transition(f'Accion{idx} a {p} de {s} a {d}.',before,after)
            self.assertEqual(rr['status'],'operator_learned')
            self.assertGreaterEqual(rr['analogy_source_count'],2)
            self.assertLessEqual(len(rr['analogy_sources']),2)
        schemas=b.symbolic.structural_schemas()
        self.assertEqual(len(schemas),1)
        self.assertEqual(schemas[0]['support'],32)

    def test_meta_schema_persists_and_teaches_next_domain_from_one_episode(self):
        b=Bot();teach_move(b);nav_episode(b,'nora','uno','dos');nav_episode(b,'omar','tres','cuatro')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json';b.save(p);c=Bot.load(p)
            self.assertEqual(len(c.symbolic.structural_schemas()),1)
            before=S(F('positioned','paz','origenx'),F('path','origenx','destinoy'),F('person','paz'),F('place','origenx'),F('place','destinoy'))
            after=(before-{F('positioned','paz','origenx')})|{F('positioned','paz','destinoy')}
            r=c.observe_symbolic_transition('Desplaza a paz desde origenx hasta destinoy.',before,after)
            self.assertEqual(r['status'],'operator_learned')
            self.assertGreaterEqual(r['analogy_source_count'],2)

    def test_meta_schema_dissolves_when_independent_support_is_withdrawn(self):
        b=Bot();teach_move(b);nav_episode(b,'nora','uno','dos');nav_episode(b,'omar','tres','cuatro')
        self.assertEqual(len(b.symbolic.structural_schemas()),1)
        nav_episode(b,'paz','cinco','seis',success=False)
        self.assertEqual(b.symbolic.structural_schemas(),[])
        before=S(F('positioned','luz','q1'),F('path','q1','q2'),F('person','luz'),F('place','q1'),F('place','q2'))
        after=(before-{F('positioned','luz','q1')})|{F('positioned','luz','q2')}
        r=b.observe_symbolic_transition('Desplaza a luz desde q1 hasta q2.',before,after)
        self.assertEqual(r['status'],'pending_support')

    def test_meta_schemas_keep_different_operator_topologies_separate(self):
        b=Bot();teach_move(b);nav_episode(b,'nora','uno','dos');nav_episode(b,'omar','tres','cuatro')
        # Independently establish pickup, then a renamed pickup domain.
        for p0,item,loc in [('ana','caja','bodega'),('bruno','libro','biblioteca'),('carla','llave','taller')]:
            before=S(F('at',p0,loc),F('item_at',item,loc),F('person',p0),F('item',item),F('place',loc))
            after=(before-{F('item_at',item,loc)})|{F('holding',p0,item)}
            b.observe_symbolic_transition(f'{p0} toma {item} en {loc}.',before,after)
        before=S(F('at','d','l'),F('person','d'),F('item','x'),F('place','l'))
        b.observe_symbolic_transition('d toma x en l.',before,before)
        before=S(F('item_at','y','m'),F('person','e'),F('item','y'),F('place','m'),F('at','e','n'),F('place','n'))
        b.observe_symbolic_transition('e toma y en m.',before,before)
        for p0,tok,loc in [('nora','t1','l1'),('omar','t2','l2')]:
            before=S(F('positioned',p0,loc),F('token_at',tok,loc),F('person',p0),F('token',tok),F('place',loc))
            after=(before-{F('token_at',tok,loc)})|{F('possesses',p0,tok)}
            rr=b.observe_symbolic_transition(f'{p0} recolecta {tok} en {loc}.',before,after)
        self.assertEqual(rr['status'],'operator_learned')
        schemas=b.symbolic.structural_schemas()
        self.assertEqual(len(schemas),2)
        self.assertEqual(sorted(s['support'] for s in schemas),[2,2])

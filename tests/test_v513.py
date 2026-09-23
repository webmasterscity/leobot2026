import unittest

from leobot import Bot
from leobot.core import Atom


class V513OpenRawArityTests(unittest.TestCase):
    def test_four_roles_require_four_independent_supports(self):
        bot=Bot(allow_extensional_grounding=False)
        rows=[
            'ana mueve caja de casa a oficina',
            'bea mueve libro de plaza a tienda',
            'cora mueve mapa de cuarto a taller',
            'dora mueve carta de parque a banco',
        ]
        for row in rows[:3]:
            self.assertNotEqual(bot.respond(row)['status'],'raw_relation_learned')
        learned=bot.respond(rows[3])
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],4)
        self.assertEqual(learned['support'],4)
        self.assertEqual(learned['surface'],'{s0} mueve {s1} de {s2} a {s3}')

    def test_five_role_relation_promotes_after_five_supports(self):
        bot=Bot(allow_extensional_grounding=False)
        rows=[
            'ana envia caja de casa a oficina con camion',
            'bea envia libro de plaza a tienda con moto',
            'cora envia mapa de cuarto a taller con bici',
            'dora envia carta de parque a banco con van',
            'eva envia llave de puerto a museo con tren',
        ]
        for row in rows[:-1]: self.assertNotEqual(bot.respond(row)['status'],'raw_relation_learned')
        learned=bot.respond(rows[-1])
        self.assertEqual(learned['arity'],5)
        self.assertEqual(learned['support'],5)
        self.assertEqual(bot.respond('fede envia sobre de escuela a teatro con barco')['status'],'stored')

    def test_eight_role_relation_reaches_core_atom_limit(self):
        bot=Bot(allow_extensional_grounding=False)
        learned=None
        for i in range(8):
            learned=bot.respond(
                f'p{i} relaciona q{i} via r{i} hacia s{i} con t{i} desde u{i} sobre v{i} para w{i}'
            )
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],8)
        pred=learned['predicate']
        text='px relaciona qx via rx hacia sx con tx desde ux sobre vx para wx'
        self.assertEqual(bot.respond(text)['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('px','qx','rx','sx','tx','ux','vx','wx')))['status'],'supported')

    def test_negative_four_role_induction_keeps_polarity_separate(self):
        bot=Bot(allow_extensional_grounding=False)
        rows=[
            'ana no mueve caja de casa a oficina',
            'bea no mueve libro de plaza a tienda',
            'cora no mueve mapa de cuarto a taller',
            'dora no mueve carta de parque a banco',
        ]
        for row in rows[:3]: self.assertNotEqual(bot.respond(row)['status'],'raw_negative_relation_learned')
        learned=bot.respond(rows[3])
        self.assertEqual(learned['status'],'raw_negative_relation_learned')
        self.assertEqual(learned['arity'],4)
        self.assertEqual(bot.raw_relation_observations,[])
        pred=learned['predicate']
        self.assertTrue(bot.kb.contains(Atom('!'+pred,('ana','caja','casa','oficina'))))

    def test_four_role_hypothetical_clause_requires_four_conditional_examples(self):
        bot=Bot(allow_extensional_grounding=False)
        conds=[
            'si ana mueve caja de casa a oficina entonces caja llega oficina',
            'si bea mueve libro de plaza a tienda entonces libro llega tienda',
            'si cora mueve mapa de cuarto a taller entonces mapa llega taller',
            'si dora mueve carta de parque a banco entonces carta llega banco',
        ]
        reports=[bot.respond(x) for x in conds]
        self.assertNotEqual(reports[2]['status'],'conditional_bootstrap_learned')
        self.assertEqual(reports[3]['status'],'conditional_bootstrap_learned')
        self.assertEqual(reports[3]['required'],4)
        self.assertEqual(bot.kb.stats()['facts'],0)
        bot.respond('eva mueve llave de puerto a museo')
        self.assertEqual(bot.respond('¿llave llega museo?')['status'],'hypothesis')


if __name__=='__main__': unittest.main()

import unittest
from leobot.bot import Bot
from leobot.core import KnowledgeBase

class V51UnifiedBootstrapTests(unittest.TestCase):
    def test_zero_ontology_raw_primitives_compose_and_transfer(self):
        bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
        a=['sujeto alfa enlaza modulo rojo','sujeto beta enlaza modulo azul','sujeto gamma enlaza modulo verde']
        b=['modulo rojo reposa zona norte','modulo azul reposa zona sur','modulo verde reposa zona este']
        ra=[bot.respond(x) for x in a]; rb=[bot.respond(x) for x in b]
        self.assertEqual(ra[-1]['status'],'raw_relation_learned')
        self.assertEqual(rb[-1]['status'],'raw_relation_learned')
        pa,pb=ra[-1]['predicate'],rb[-1]['predicate']
        train=[
            'sujeto alfa coordina modulo rojo en zona norte',
            'sujeto beta coordina modulo azul en zona sur',
            'sujeto alfa no coordina modulo rojo en zona sur',
            'sujeto alfa no coordina modulo azul en zona sur',
            'sujeto alfa no coordina modulo azul en zona norte',
        ]
        reports=[bot.observe_schema_statement(x) for x in train]
        self.assertEqual(reports[-1]['status'],'schema_learned')
        selected=reports[-1]['learning']['selected']
        self.assertIn(pa,selected); self.assertIn(pb,selected)
        self.assertEqual(reports[-1]['learning']['arity'],3)
        for i in range(20):
            self.assertEqual(bot.respond(f'sujeto n{i} enlaza modulo m{i}')['status'],'stored')
            self.assertEqual(bot.respond(f'modulo m{i} reposa zona z{i}')['status'],'stored')
            self.assertEqual(bot.query_schema(f'sujeto n{i} coordina modulo m{i} en zona z{i}')['status'],'entailed')
            self.assertNotEqual(bot.query_schema(f'sujeto n{i} coordina modulo m{i} en zona z{(i+1)%20}')['status'],'entailed')

    def test_raw_bootstrap_control_without_promotion_does_not_learn(self):
        bot=Bot(KnowledgeBase(),raw_relation_min_support=999,allow_extensional_grounding=False)
        for x in ['sujeto alfa enlaza modulo rojo','sujeto beta enlaza modulo azul','sujeto gamma enlaza modulo verde']:
            report=bot.respond(x)
        self.assertEqual(len(bot.raw_relation_promotions),0)
        self.assertIn(report['status'],('raw_relation_pending','schema_pending','concept_pending'))

if __name__=='__main__': unittest.main()

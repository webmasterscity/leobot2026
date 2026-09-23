import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V522DocumentRoleBridgeTests(unittest.TestCase):
    TRAIN='''
ana frobla caja.
bea frobla libro.
cora frobla mapa.
dario norga puerto.
eva norga nodo.
fabio norga zona.
gina tulka lima.
hugo tulka quito.
iris tulka bogota.
'''

    def _trained(self, scalable=None):
        bot = scalable or Bot(allow_extensional_grounding=False)
        report=bot.ingest_document_text(self.TRAIN, source='bridge_grammar')
        self.assertEqual(report['relations_promoted'], 3)
        by_surface={p['surface']:p['predicate'] for p in bot.raw_relation_promotions.values()}
        return bot, by_surface['{s0} frobla {s1}'], by_surface['{s0} norga {s1}'], by_surface['{s0} tulka {s1}']

    @staticmethod
    def _teach_bridge(bot, left='frobla', right='norga'):
        rows=[('ana','caja','luis'),('bea','libro','mario'),('cora','mapa','nora')]
        for i,(a,obj,b) in enumerate(rows,1):
            bot.ingest_document_text(f'{a} {left} {obj}. {b} {right} {obj}.', source=f'bridge_{left}_{right}_{i}')

    def test_three_independent_explicit_documents_promote_cross_predicate_role_bridge(self):
        bot, frobla, norga, _ = self._trained()
        self._teach_bridge(bot)
        promoted=[s for s in bot.document_role_bridge_hypotheses.values() if s.get('promoted')]
        self.assertEqual(len(promoted),1)
        self.assertEqual(promoted[0]['support'],3)
        self.assertEqual({tuple(x) for x in promoted[0]['roles']}, {(frobla,1),(norga,1)})

    def test_bridge_resolves_new_reference_across_predicates_and_ignores_later_distractor(self):
        bot, frobla, norga, tulka = self._trained()
        self._teach_bridge(bot)
        report=bot.ingest_document_text(
            'dora frobla paquete. zoe tulka ciudad. raul norga eso.', source='bridge_target')
        row=report['sentence_results'][2]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['args'],['raul','paquete'])
        self.assertIn('learned_role_bridge_v522',row['references'][0]['criteria'])
        self.assertTrue(bot.kb.contains(Atom(norga,('raul','paquete'))))
        self.assertFalse(bot.kb.contains(Atom(norga,('raul','ciudad'))))

    def test_two_bridge_documents_are_not_enough(self):
        bot, _, norga, _ = self._trained()
        rows=[('ana','caja','luis'),('bea','libro','mario')]
        for i,(a,obj,b) in enumerate(rows,1):
            bot.ingest_document_text(f'{a} frobla {obj}. {b} norga {obj}.', source=f'bridge_control_{i}')
        report=bot.ingest_document_text('dora frobla paquete. raul norga eso.', source='bridge_unlicensed')
        self.assertEqual(report['sentence_results'][1]['status'],'document_coreference_unresolved')
        self.assertFalse(bot.kb.contains(Atom(norga,('raul','paquete'))))

    def test_reingesting_same_document_does_not_fake_independent_support(self):
        bot, _, _, _ = self._trained()
        text='ana frobla pieza. luis norga pieza.'
        for i in range(5):
            bot.ingest_document_text(text, source=f'renamed_same_bridge_doc_{i}')
        states=list(bot.document_role_bridge_hypotheses.values())
        self.assertEqual(len(states),1)
        self.assertFalse(states[0]['promoted'])
        self.assertEqual(len(states[0]['observations']),1)

    def test_conflicting_promoted_bridges_abstain_instead_of_using_recency(self):
        bot, _, norga, _ = self._trained()
        self._teach_bridge(bot,'frobla','norga')
        self._teach_bridge(bot,'tulka','norga')
        report=bot.ingest_document_text(
            'dora frobla paquete. zoe tulka ciudad. raul norga eso.', source='bridge_conflict')
        row=report['sentence_results'][2]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        self.assertEqual(set(row['candidates']),{'paquete','ciudad'})
        self.assertFalse(bot.kb.contains(Atom(norga,('raul','paquete'))))
        self.assertFalse(bot.kb.contains(Atom(norga,('raul','ciudad'))))

    def test_role_bridge_and_resolved_fact_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot, _, norga, _ = self._trained(ScalableBot(db,allow_extensional_grounding=False))
            self._teach_bridge(bot)
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(s.get('promoted') for s in loaded.document_role_bridge_hypotheses.values()))
                report=loaded.ingest_document_text('dora frobla paquete. raul norga eso.', source='after_reload')
                self.assertEqual(report['sentence_results'][1]['status'],'document_coreference_resolved')
                self.assertTrue(loaded.kb.contains(Atom(norga,('raul','paquete'))))
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V524DocumentDiscourseLinkTests(unittest.TestCase):
    TRAIN='''
ana frobla caja.
bea frobla libro.
cora frobla mapa.
dario norga puerto.
eva norga nodo.
fabio norga zona.
'''

    def _trained(self, bot=None):
        bot=bot or Bot(allow_extensional_grounding=False)
        bot.ingest_document_text(self.TRAIN,source='discourse_train')
        return bot

    def test_luego_stores_explicit_temporal_edge_between_adjacent_facts(self):
        bot=self._trained()
        report=bot.ingest_document_text('Dora frobla paquete. Luego Eva norga ciudad.',source='temporal_doc')
        first,second=report['sentence_results']
        link=second['discourse_link']
        self.assertEqual(link['status'],'document_discourse_link_stored')
        self.assertEqual(link['relation'],'after')
        self.assertTrue(bot.kb.contains(Atom('_doc_precedes',(first['id'],second['id']))))
        self.assertEqual(report['document_links_stored'],1)

    def test_por_eso_stores_causal_edge_but_does_not_invent_rule(self):
        bot=self._trained(); before_rules=len(bot.kb.rules)
        report=bot.ingest_document_text('Dora frobla paquete. Por eso Eva norga ciudad.',source='causal_doc')
        first,second=report['sentence_results']; link=second['discourse_link']
        self.assertEqual(link['relation'],'caused_by_previous')
        self.assertTrue(bot.kb.contains(Atom('_doc_causes',(first['id'],second['id']))))
        self.assertEqual(len(bot.kb.rules),before_rules)

    def test_connective_without_immediately_previous_fact_keeps_assertion_but_abstains_on_link(self):
        bot=self._trained()
        report=bot.ingest_document_text('¿Dora frobla paquete? Luego Eva norga ciudad.',source='missing_prior')
        self.assertEqual(report['sentence_results'][0]['status'],'document_question_skipped')
        second=report['sentence_results'][1]
        self.assertEqual(second['status'],'document_fact_stored')
        self.assertEqual(second['discourse_link']['status'],'document_discourse_unresolved')
        self.assertEqual(report['document_links_stored'],0)
        self.assertEqual(report['document_links_unresolved'],1)

    def test_discourse_prefix_is_not_part_of_new_relation_surface(self):
        bot=Bot(allow_extensional_grounding=False)
        report=bot.ingest_document_text('A frobla x. Luego B frobla y. Luego C frobla z.',source='learn_with_links')
        self.assertEqual(report['relations_promoted'],1)
        promotion=next(iter(bot.raw_relation_promotions.values()))
        self.assertEqual(promotion['surface'],'{s0} frobla {s1}')
        self.assertNotIn('luego',promotion['surface'])
        self.assertEqual(report['sentence_results'][2]['discourse_link']['status'],'document_discourse_link_stored')

    def test_discourse_link_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=self._trained(ScalableBot(db,allow_extensional_grounding=False))
            report=bot.ingest_document_text('Dora frobla paquete. Después Eva norga ciudad.',source='persistent_temporal')
            first,second=report['sentence_results']; bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(loaded.kb.contains(Atom('_doc_precedes',(first['id'],second['id']))))
                events=[x for x in loaded.kb.audit if x.get('event')=='document_discourse_link_stored']
                self.assertTrue(any(x.get('from_fact')==first['id'] and x.get('to_fact')==second['id'] for x in events))
            finally:
                loaded.close()


if __name__=='__main__': unittest.main()

import unittest

from leobot import Bot
from leobot.core import Atom


class V523DocumentReferenceChainTests(unittest.TestCase):
    TRAIN='''
a1 frobla x1.
a2 frobla x2.
a3 frobla x3.
b1 norga y1.
b2 norga y2.
b3 norga y3.
c1 tulka z1.
c2 tulka z2.
c3 tulka z3.
'''

    def _bot(self):
        b=Bot(allow_extensional_grounding=False)
        b.ingest_document_text(self.TRAIN,source='chain_train')
        by={p['surface']:p['predicate'] for p in b.raw_relation_promotions.values()}
        for i,(obj,a,c) in enumerate([('uno','aa','bb'),('dos','cc','dd'),('tres','ee','ff')],1):
            b.ingest_document_text(f'{a} frobla {obj}. {c} norga {obj}.',source=f'fn_{i}')
        for i,(obj,a,c) in enumerate([('rojo','gg','hh'),('azul','ii','jj'),('verde','kk','ll')],1):
            b.ingest_document_text(f'{a} norga {obj}. {c} tulka {obj}.',source=f'nt_{i}')
        return b,by

    def test_reference_can_chain_across_two_learned_role_bridges(self):
        b,by=self._bot()
        r=b.ingest_document_text('dora frobla paquete. raul norga eso. zoe tulka eso.',source='chain_target')
        self.assertEqual([x['status'] for x in r['sentence_results']],
                         ['document_fact_stored','document_coreference_resolved','document_coreference_resolved'])
        self.assertEqual(r['sentence_results'][1]['args'],['raul','paquete'])
        self.assertEqual(r['sentence_results'][2]['args'],['zoe','paquete'])
        self.assertTrue(b.kb.contains(Atom(by['{s0} tulka {s1}'],('zoe','paquete'))))

    def test_coreference_generated_facts_do_not_increase_bridge_support(self):
        b,_=self._bot()
        before={k:s.get('support') for k,s in b.document_role_bridge_hypotheses.items() if s.get('promoted')}
        for i in range(40):
            b.ingest_document_text(f'd{i} frobla p{i}. r{i} norga eso. z{i} tulka eso.',source=f'generated_chain_{i}')
        after={k:s.get('support') for k,s in b.document_role_bridge_hypotheses.items() if s.get('promoted')}
        self.assertEqual(after,before)

    def test_chain_stops_when_intermediate_reference_is_ambiguous(self):
        b,by=self._bot()
        r=b.ingest_document_text('dora frobla paquete. luis frobla carta. raul norga eso. zoe tulka eso.',source='chain_amb')
        self.assertEqual(r['sentence_results'][2]['status'],'document_coreference_ambiguous')
        self.assertEqual(r['sentence_results'][3]['status'],'document_coreference_unresolved')
        self.assertFalse(b.kb.contains(Atom(by['{s0} norga {s1}'],('raul','paquete'))))
        self.assertFalse(b.kb.contains(Atom(by['{s0} tulka {s1}'],('zoe','paquete'))))


if __name__=='__main__': unittest.main()

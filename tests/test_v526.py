import unittest

from leobot import Bot
from leobot.core import Atom


class V526VariableLengthDocumentEventTests(unittest.TestCase):
    GRAMMAR='''
ana frobla caja.
bruno frobla carta.
cora frobla libro.
ana tulka puerto.
bruno tulka plaza.
cora tulka parque.
ana norga lunes.
bruno norga martes.
cora norga miercoles.
uno activa alarma1.
dos activa alarma2.
tres activa alarma3.
'''
    ROWS=[
        ('dora','paquete','norte','jueves'),
        ('eva','caja azul','sur','viernes'),
        ('luis','archivo','centro','sabado'),
    ]

    def _trained(self):
        b=Bot(allow_extensional_grounding=False)
        r=b.ingest_document_text(self.GRAMMAR,source='cluster_grammar')
        self.assertEqual(r['relations_promoted'],4)
        by={p['surface']:p['predicate'] for p in b.raw_relation_promotions.values()}
        for i,(person,obj,place,time) in enumerate(self.ROWS):
            b.ingest_document_text(
                f'{person} frobla {obj}. {person} tulka {place}. {person} norga {time}.',
                source=f'cluster_train_{i}')
        return b,by

    def test_three_sentence_cluster_is_promoted_alongside_subschemas(self):
        b,_=self._trained()
        promoted=[s for s in b.document_event_schema_hypotheses.values() if s.get('promoted')]
        sizes=sorted(len(s['structure']['facts']) for s in promoted)
        self.assertIn(3,sizes)
        self.assertGreaterEqual(sizes.count(2),2)
        triple=[s for s in promoted if len(s['structure']['facts'])==3]
        self.assertEqual(len(triple),1)
        self.assertEqual(triple[0]['support'],3)

    def test_unique_maximal_cluster_dominates_overlapping_pair_schemas(self):
        b,by=self._trained()
        r=b.ingest_document_text(
            'marta frobla paquete rojo. marta tulka deposito. marta norga domingo. Eso activa sirena.',
            source='cluster_target')
        row=r['sentence_results'][3]
        self.assertEqual(row['status'],'document_coreference_resolved')
        ref=row['references'][0]
        self.assertEqual(ref['criteria'],['latent_document_event_v526'])
        event_id=ref['antecedent']
        event=row['provenance']['materialized_events'][0]
        self.assertEqual(len(event['member_fact_ids']),3)
        self.assertEqual(event['sentence_span'],[1,3])
        self.assertTrue(b.kb.contains(Atom(by['{s0} activa {s1}'],(event_id,'sirena'))))
        members=[f['atom'].args[1] for f in b.kb.facts.values()
                 if f['atom'].pred=='_event_member' and f['atom'].args[0]==event_id]
        self.assertEqual(len(set(members)),3)

    def test_two_incomparable_maximal_clusters_still_abstain(self):
        b,_=self._trained()
        r=b.ingest_document_text(
            'a frobla x. a tulka y. a norga z. '
            'b frobla u. b tulka v. b norga w. Eso activa alarma.',
            source='cluster_ambiguous')
        row=r['sentence_results'][6]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        self.assertEqual(len(row['candidates']),2)
        self.assertEqual(r['document_events_materialized'],0)

    def test_connectedness_is_required_so_adjacent_unrelated_facts_do_not_form_event_schema(self):
        b,_=self._trained()
        before=len(b.document_event_schema_hypotheses)
        for i in range(4):
            b.ingest_document_text(
                f'persona{i+20} frobla objeto{i+20}. otra{i+20} tulka lugar{i+20}. tercero{i+20} norga tiempo{i+20}.',
                source=f'unconnected_{i}')
        # No signature can be created for the disconnected windows, so only the
        # schemas learned in _trained remain.
        self.assertEqual(len(b.document_event_schema_hypotheses),before)


if __name__=='__main__': unittest.main()

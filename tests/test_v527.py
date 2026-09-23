import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V527EventTopologyMetaTransferTests(unittest.TestCase):
    RELATIONS=('frobla','tulka','norga','peka','rula','soma','zeta','kora','miva','activa','chaina','chainb','chainc')

    def _ground_all(self, bot):
        # Three natural assertions per relation are sufficient for the existing
        # raw relation learner; no event annotations or schema IDs are supplied.
        lines=[]
        for j,name in enumerate(self.RELATIONS):
            lines += [f'a{j}x {name} b{j}x.', f'a{j}y {name} b{j}y.', f'a{j}z {name} b{j}z.']
        r=bot.ingest_document_text(' '.join(lines),source='v527_grammar')
        self.assertEqual(r['relations_promoted'],len(self.RELATIONS))
        return {p['surface'].split()[1]:p['predicate'] for p in bot.raw_relation_promotions.values()}

    @staticmethod
    def _train_exact_family(bot, names, prefix):
        p,q,r=names
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
                source=f'{prefix}_schema_{i}')

    @staticmethod
    def _use_family(bot,names,prefix):
        p,q,r=names
        return bot.ingest_document_text(
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso activa {prefix}alarm.',
            source=f'{prefix}_use')

    def _meta_trained(self, bot=None):
        b=bot or Bot(allow_extensional_grounding=False)
        preds=self._ground_all(b)
        self._train_exact_family(b,('frobla','tulka','norga'),'f')
        first=self._use_family(b,('frobla','tulka','norga'),'f')
        self.assertEqual(first['sentence_results'][3]['status'],'document_coreference_resolved')
        self._train_exact_family(b,('peka','rula','soma'),'g')
        second=self._use_family(b,('peka','rula','soma'),'g')
        self.assertEqual(second['sentence_results'][3]['status'],'document_coreference_resolved')
        return b,preds

    def test_two_predicate_disjoint_used_schemas_promote_event_topology_meta_schema(self):
        b,_=self._meta_trained()
        promoted=[s for s in b.document_event_meta_hypotheses.values() if s.get('promoted')]
        self.assertEqual(len(promoted),1)
        self.assertEqual(promoted[0]['support'],2)
        self.assertEqual(len(promoted[0]['source_schemas']),2)
        families=[set(x['predicates']) for x in promoted[0]['source_schemas']]
        self.assertTrue(families[0].isdisjoint(families[1]))

    def test_meta_topology_transfers_event_representation_to_unseen_predicate_family_one_shot(self):
        b,preds=self._meta_trained()
        before=[s for s in b.document_event_schema_hypotheses.values()
                if s.get('promoted') and [x['pred'] for x in s['structure']['facts']]==[preds['zeta'],preds['kora'],preds['miva']]]
        self.assertEqual(before,[])
        r=b.ingest_document_text(
            'neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='meta_transfer_target')
        row=r['sentence_results'][3]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_event_meta_v527'])
        event_id=row['references'][0]['antecedent']
        self.assertTrue(b.kb.contains(Atom(preds['activa'],(event_id,'sirena'))))
        materialized=row['provenance']['materialized_events'][0]
        self.assertEqual(materialized['mechanism'],'demand_driven_event_meta_transfer_v527')
        self.assertEqual(len(materialized['member_fact_ids']),3)

    def test_one_used_family_is_not_enough_for_meta_transfer(self):
        b=Bot(allow_extensional_grounding=False);self._ground_all(b)
        self._train_exact_family(b,('frobla','tulka','norga'),'f')
        self._use_family(b,('frobla','tulka','norga'),'f')
        self.assertFalse(any(s.get('promoted') for s in b.document_event_meta_hypotheses.values()))
        r=b.ingest_document_text('neo zeta obj. neo kora loc. neo miva time. Eso activa alarm.',source='meta_undertrained')
        self.assertEqual(r['sentence_results'][3]['status'],'document_coreference_unresolved')
        self.assertEqual(r['document_events_materialized'],0)

    def test_different_role_topology_does_not_inherit_star_event_meta_schema(self):
        b,_=self._meta_trained()
        r=b.ingest_document_text(
            'a chaina b. b chainb c. c chainc d. Eso activa alarma.',source='meta_wrong_topology')
        self.assertEqual(r['sentence_results'][3]['status'],'document_coreference_unresolved')
        self.assertEqual(r['document_events_materialized'],0)

    def test_event_meta_schema_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b,preds=self._meta_trained(ScalableBot(db,allow_extensional_grounding=False))
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(s.get('promoted') for s in loaded.document_event_meta_hypotheses.values()))
                r=loaded.ingest_document_text(
                    'neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='meta_after_reload')
                self.assertEqual(r['sentence_results'][3]['references'][0]['criteria'],['latent_document_event_meta_v527'])
                ev=r['sentence_results'][3]['references'][0]['antecedent']
                self.assertTrue(loaded.kb.contains(Atom(preds['activa'],(ev,'sirena'))))
            finally:
                loaded.close()


if __name__=='__main__': unittest.main()

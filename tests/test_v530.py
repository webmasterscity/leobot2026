import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V530EventCounterevidenceTests(unittest.TestCase):
    RELATIONS=('frobla','tulka','norga','peka','rula','soma','zeta','kora','miva','activa')

    def _ground(self, bot):
        lines=[]
        for j,name in enumerate(self.RELATIONS):
            lines += [f'a{j}x {name} b{j}x.', f'a{j}y {name} b{j}y.', f'a{j}z {name} b{j}z.']
        bot.ingest_document_text(' '.join(lines),source='v530_grammar')
        return {p['surface'].split()[1]:p['predicate'] for p in bot.raw_relation_promotions.values()}

    @staticmethod
    def _train_family(bot,names,prefix):
        p,q,r=names
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
                source=f'{prefix}_schema_{i}')

    @staticmethod
    def _use(bot,names,prefix):
        p,q,r=names
        return bot.ingest_document_text(
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso activa {prefix}alarm.',
            source=f'{prefix}_use')

    def _meta_trained(self, bot=None):
        b=bot or Bot(allow_extensional_grounding=False);preds=self._ground(b)
        self._train_family(b,('frobla','tulka','norga'),'f');self._use(b,('frobla','tulka','norga'),'f')
        self._train_family(b,('peka','rula','soma'),'g');self._use(b,('peka','rula','soma'),'g')
        self.assertTrue(any(m.get('promoted') for m in b.document_event_meta_hypotheses.values()))
        self.assertTrue(any(g.get('promoted') for g in b.document_event_reference_hypotheses.values()))
        return b,preds

    def test_explicit_feedback_revises_meta_fact_retracts_event_and_blocks_repeat(self):
        b,preds=self._meta_trained()
        r=b.ingest_document_text(
            'neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='v530_bad_meta')
        row=r['sentence_results'][3]; old_id=row['id'];event_id=row['references'][0]['antecedent']
        before_raw=len(b.raw_relation_observations)
        correction=b.respond('No, eso se refería a objeto.')
        self.assertEqual(correction['status'],'event_reference_corrected')
        self.assertIsNone(b.kb.get_fact(old_id))
        self.assertTrue(b.kb.contains(Atom(preds['activa'],('objeto','sirena'))))
        self.assertFalse(any(f['atom'].pred.startswith('_event_') for f in b._facts_referencing_entity(event_id)))
        self.assertEqual(len(b.raw_relation_observations),before_raw)
        gate=next(g for g in b.document_event_reference_hypotheses.values() if g.get('gate_id')==correction['gate_id'])
        self.assertTrue(gate['contested']);self.assertFalse(gate['promoted'])
        again=b.ingest_document_text(
            'zed zeta o2. zed kora l2. zed miva t2. Eso activa alarma2.',source='v530_after_counter')
        self.assertEqual(again['sentence_results'][3]['status'],'document_coreference_unresolved')
        self.assertEqual(again['document_events_materialized'],0)

    def test_counterevidence_against_exact_schema_withdraws_dependent_meta_transfer(self):
        b,_=self._meta_trained()
        r=self._use(b,('frobla','tulka','norga'),'h')
        self.assertEqual(r['sentence_results'][3]['references'][0]['criteria'],['latent_document_event_v526'])
        correction=b.respond('No, eso se refería a hobj.')
        self.assertEqual(correction['status'],'event_reference_corrected')
        self.assertTrue(correction['schema_contested'])
        self.assertTrue(any(s.get('contested') for s in b.document_event_schema_hypotheses.values()))
        self.assertFalse(any(m.get('promoted') for m in b.document_event_meta_hypotheses.values()))
        target=b.ingest_document_text(
            'neo zeta o. neo kora l. neo miva t. Eso activa alarm.',source='v530_meta_withdrawn')
        self.assertEqual(target['sentence_results'][3]['status'],'document_coreference_unresolved')

    def test_invalid_feedback_does_not_mutate_fact_or_gate(self):
        b,_=self._meta_trained()
        r=b.ingest_document_text(
            'neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='v530_invalid')
        row=r['sentence_results'][3]; fid=row['id']
        before=b.kb.get_fact(fid)['atom']
        gate_before=[(g['gate_id'],g.get('promoted'),g.get('contested')) for g in b.document_event_reference_hypotheses.values()]
        out=b.respond('No, eso se refería a entidad inexistente.')
        self.assertEqual(out['status'],'event_reference_feedback_unresolved')
        self.assertEqual(b.kb.get_fact(fid)['atom'],before)
        gate_after=[(g['gate_id'],g.get('promoted'),g.get('contested')) for g in b.document_event_reference_hypotheses.values()]
        self.assertEqual(gate_after,gate_before)

    def test_contested_gate_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b,_=self._meta_trained(ScalableBot(db,allow_extensional_grounding=False))
            b.ingest_document_text('neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='v530_persist')
            self.assertEqual(b.respond('No, eso se refería a objeto.')['status'],'event_reference_corrected')
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(g.get('contested') for g in loaded.document_event_reference_hypotheses.values()))
                r=loaded.ingest_document_text(
                    'n zeta o. n kora l. n miva t. Eso activa a.',source='v530_persist_after')
                self.assertEqual(r['sentence_results'][3]['status'],'document_coreference_unresolved')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

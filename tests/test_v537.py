import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V537PersistentStateMetaTransferTests(unittest.TestCase):
    RELS=('palpha','qbeta','rdelta','sepsilon','zeta','kora','ruido','activa')

    def _ground(self, bot):
        lines=[]
        for j,name in enumerate(self.RELS):
            lines += [f'g{j}a {name} h{j}a.',f'g{j}b {name} h{j}b.',f'g{j}c {name} h{j}c.']
        r=bot.ingest_document_text(' '.join(lines),source='v537_grammar')
        self.assertEqual(r['relations_promoted'],len(self.RELS))

    @staticmethod
    def _train_family(bot,p,q,prefix):
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}x{i}. {prefix}n{i} ruido {prefix}m{i}. '
                f'{prefix}{i} {q} {prefix}y{i}.',source=f'v537_{prefix}_train_{i}')

    @staticmethod
    def _use_family(bot,p,q,prefix):
        return bot.ingest_document_text(
            f'{prefix}u {p} {prefix}x. {prefix}n ruido {prefix}m. '
            f'{prefix}u {q} {prefix}y. Eso activa {prefix}alarm.',source=f'v537_{prefix}_use')

    def _prepare(self,two=True,bot=None):
        b=bot or Bot(allow_extensional_grounding=False);self._ground(b)
        self._train_family(b,'palpha','qbeta','a')
        r1=self._use_family(b,'palpha','qbeta','a')
        self.assertEqual(r1['sentence_results'][-1]['references'][0]['criteria'],['latent_document_state_v535'])
        if two:
            self._train_family(b,'rdelta','sepsilon','b')
            r2=self._use_family(b,'rdelta','sepsilon','b')
            self.assertEqual(r2['sentence_results'][-1]['references'][0]['criteria'],['latent_document_state_v535'])
        return b

    @staticmethod
    def _target(bot,prefix='neo',source='v537_target'):
        return bot.ingest_document_text(
            f'{prefix} zeta {prefix}obj. {prefix}n ruido {prefix}m. '
            f'{prefix} kora {prefix}val. Eso activa {prefix}alarm.',source=source)

    def test_two_used_predicate_disjoint_state_families_promote_meta_topology(self):
        b=self._prepare(True)
        promoted=[s for s in b.document_state_meta_hypotheses.values() if s.get('promoted')]
        self.assertEqual(len(promoted),1)
        self.assertEqual(promoted[0]['support'],2)
        families=[set(x['predicates']) for x in promoted[0]['source_schemas']]
        self.assertEqual(len(families),2)
        self.assertTrue(families[0].isdisjoint(families[1]))
        gates=[g for g in b.document_state_meta_reference_hypotheses.values() if g.get('promoted')]
        self.assertEqual(len(gates),1)
        self.assertEqual(gates[0]['support'],2)

    def test_meta_topology_transfers_persistence_to_unseen_family_one_shot(self):
        b=self._prepare(True)
        before=[s for s in b.document_state_schema_hypotheses.values()
                if s.get('promoted') and any('zeta' in str(f.get('pred')) for f in s.get('structure',{}).get('facts',[]))]
        self.assertEqual(before,[])
        r=self._target(b)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_state_meta_v537'])
        self.assertEqual(r['document_states_materialized'],1)
        # One target episode is below V5.35's 3-document exact promotion threshold.
        target_exact=[s for s in b.document_state_schema_hypotheses.values()
                      if s.get('promoted') and any('zeta' in str(f.get('pred')) for f in s.get('structure',{}).get('facts',[]))]
        self.assertEqual(target_exact,[])

    def test_one_source_family_is_not_enough_for_state_meta_transfer(self):
        b=self._prepare(False)
        self.assertFalse(any(s.get('promoted') for s in b.document_state_meta_hypotheses.values()))
        r=self._target(b,prefix='solo',source='v537_one_source')
        self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_unresolved')
        self.assertEqual(r['document_states_materialized'],0)

    def test_changed_carrier_role_does_not_inherit_meta_persistence(self):
        b=self._prepare(True)
        r=b.ingest_document_text(
            'obj zeta neo. n ruido m. val kora neo. Eso activa alarma.',source='v537_wrong_carrier_role')
        self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_unresolved')
        self.assertEqual(r['document_states_materialized'],0)

    def test_meta_transferred_uses_do_not_increase_meta_support(self):
        b=self._prepare(True)
        gate=next(g for g in b.document_state_meta_reference_hypotheses.values() if g.get('promoted'))
        self.assertEqual(gate['support'],2)
        self._target(b,prefix='m1',source='v537_meta_use_1')
        self._target(b,prefix='m2',source='v537_meta_use_2')
        gate2=next(g for g in b.document_state_meta_reference_hypotheses.values() if g.get('promoted'))
        self.assertEqual(gate2['support'],2)
        self.assertEqual(len(gate2['source_schemas']),2)

    def test_state_meta_transfer_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b=self._prepare(True,ScalableBot(db,allow_extensional_grounding=False))
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(s.get('promoted') for s in loaded.document_state_meta_hypotheses.values()))
                self.assertTrue(any(g.get('promoted') for g in loaded.document_state_meta_reference_hypotheses.values()))
                r=self._target(loaded,prefix='disk',source='v537_after_reload')
                self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],
                                 ['latent_document_state_meta_v537'])
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V536LatentRepresentationCompetitionTests(unittest.TestCase):
    RELS=('palpha','qbeta','ruido','rgamma','activa')

    def _ground(self,b):
        lines=[]
        for j,n in enumerate(self.RELS):
            lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
        self.assertEqual(b.ingest_document_text(' '.join(lines),source='v536_grammar')['relations_promoted'],len(self.RELS))

    def _prepare(self,state_uses=4,event_uses=2,bot=None):
        b=bot or Bot(allow_extensional_grounding=False);self._ground(b)
        for i in range(3):
            b.ingest_document_text(
                f's{i} palpha sx{i}. sn{i} ruido sm{i}. s{i} qbeta sy{i}.',
                source=f'v536_state_train_{i}')
        for i in range(state_uses):
            r=b.ingest_document_text(
                f'su{i} palpha ux{i}. un{i} ruido um{i}. su{i} qbeta uy{i}. Eso activa sa{i}.',
                source=f'v536_state_use_{i}')
            self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],['latent_document_state_v535'])
        for i in range(3):
            b.ingest_document_text(
                f'e{i} qbeta ey{i}. ey{i} rgamma ez{i}.',source=f'v536_event_train_{i}')
        for i in range(event_uses):
            r=b.ingest_document_text(
                f'eu{i} qbeta eyy{i}. eyy{i} rgamma ezz{i}. Eso activa ea{i}.',
                source=f'v536_event_use_{i}')
            self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],['latent_document_event_v525'])
        return b

    def _target(self,b,prefix='t',source='v536_target'):
        return b.ingest_document_text(
            f'{prefix} palpha {prefix}x. {prefix}n ruido {prefix}m. '
            f'{prefix} qbeta {prefix}y. {prefix}y rgamma {prefix}z. Eso activa {prefix}alarm.',
            source=source)

    def test_predictive_support_selects_state_over_competing_event(self):
        b=self._prepare(4,2);r=self._target(b)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_state_v535'])
        sel=row['references'][0]['evidence'][0]['type_selection']
        self.assertEqual(sel['mechanism'],'latent_representation_type_competition_v536')
        supports={x['representation_type']:x['support'] for x in sel['candidates']}
        self.assertEqual(supports['latent_persistent_state'],4)
        self.assertEqual(supports['event'],2)
        self.assertEqual(r['document_states_materialized'],1)
        self.assertEqual(r['document_events_materialized'],0)

    def test_v534_ablation_without_state_generator_selects_event(self):
        b=self._prepare(4,2);b._document_state_candidates=lambda facts: []
        r=self._target(b,prefix='abl',source='v536_ablation')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_event_v525'])
        self.assertEqual(r['document_events_materialized'],1)

    def test_equal_predictive_support_abstains(self):
        b=self._prepare(2,2);r=self._target(b,prefix='tie',source='v536_tie')
        self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_ambiguous')
        self.assertEqual(r['document_states_materialized'],0)
        self.assertEqual(r['document_events_materialized'],0)

    def test_under_supported_state_does_not_steal_event(self):
        b=self._prepare(1,2);r=self._target(b,prefix='low',source='v536_low')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_event_v525'])

    def test_competition_state_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b=self._prepare(4,2,ScalableBot(db,allow_extensional_grounding=False))
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                r=self._target(loaded,prefix='disk',source='v536_disk')
                row=r['sentence_results'][-1]
                self.assertEqual(row['references'][0]['criteria'],['latent_document_state_v535'])
                sel=row['references'][0]['evidence'][0]['type_selection']
                self.assertEqual(sel['support'],4)
                self.assertEqual(sel['runner_up_support'],2)
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

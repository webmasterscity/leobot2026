import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V535LatentPersistentStateTests(unittest.TestCase):
    RELS=('palpha','qbeta','ruido','activa','bloquea')

    def _ground(self,b):
        lines=[]
        for j,name in enumerate(self.RELS):
            lines += [f'g{j}a {name} h{j}a.',f'g{j}b {name} h{j}b.',f'g{j}c {name} h{j}c.']
        r=b.ingest_document_text(' '.join(lines),source='v535_grammar')
        self.assertEqual(r['relations_promoted'],len(self.RELS))

    def _train(self,b=None):
        b=b or Bot(allow_extensional_grounding=False);self._ground(b)
        for i in range(3):
            b.ingest_document_text(
                f'a{i} palpha x{i}. n{i} ruido m{i}. a{i} qbeta y{i}.',
                source=f'v535_train_{i}')
        promoted=[s for s in b.document_state_schema_hypotheses.values() if s.get('promoted')]
        self.assertEqual(len(promoted),1)
        self.assertEqual(promoted[0]['support'],3)
        return b

    def _target(self,b,prefix='t',source='v535_target',extra=False):
        middle=f'{prefix}n ruido {prefix}m.'
        tail=(f'{prefix}n2 ruido {prefix}m2. ' if extra else '')
        return b.ingest_document_text(
            f'{prefix} palpha {prefix}x. {middle} {prefix} qbeta {prefix}y. '
            f'{tail}Eso activa {prefix}alarm.',source=source)

    def test_noncontiguous_recurrence_promotes_state_without_event_schema(self):
        b=self._train()
        self.assertEqual(sum(1 for s in b.document_event_schema_hypotheses.values() if s.get('promoted')),0)
        state=next(s for s in b.document_state_schema_hypotheses.values() if s.get('promoted'))
        self.assertTrue(state['structure']['non_contiguous'])
        self.assertEqual(state['structure']['carrier_positions'],[0,0])

    def test_unique_latent_state_resolves_demonstrative_and_materializes(self):
        b=self._train();r=self._target(b)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_state_v535'])
        sid=row['references'][0]['antecedent']
        self.assertTrue(sid.startswith('state_'))
        self.assertEqual(r['document_states_materialized'],1)
        self.assertEqual(r['document_events_materialized'],0)
        self.assertEqual(r['document_dependencies_materialized'],0)
        self.assertTrue(b.kb.contains(Atom('_state_carrier',(sid,'t'))))

    def test_state_survives_unrelated_later_sentence(self):
        b=self._train();r=self._target(b,prefix='persist',source='v535_late',extra=True)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_state_v535'])
        self.assertEqual(row['references'][0]['evidence'][0]['state_candidate']['sentence_span'],[1,3])

    def test_object_to_subject_chain_is_not_misclassified_as_persistent_state(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        # Same value flows object -> subject; this is an event chain, not
        # persistence of one role across an interval.
        for i in range(3):
            b.ingest_document_text(
                f'a{i} palpha x{i}. n{i} ruido m{i}. x{i} qbeta y{i}.',
                source=f'v535_chain_{i}')
        self.assertEqual(sum(1 for s in b.document_state_schema_hypotheses.values() if s.get('promoted')),0)

    def test_two_compatible_states_abstain(self):
        b=self._train()
        r=b.ingest_document_text(
            'a palpha ax. n1 ruido m1. a qbeta ay. '
            'b palpha bx. n2 ruido m2. b qbeta by. Eso activa alarm.',
            source='v535_ambiguous')
        self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_ambiguous')
        self.assertEqual(r['document_states_materialized'],0)

    def test_state_hypotheses_and_materialization_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b=self._train(ScalableBot(db,allow_extensional_grounding=False))
            r=self._target(b,prefix='disk',source='v535_disk')
            sid=r['sentence_results'][-1]['references'][0]['antecedent']
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(s.get('promoted') for s in loaded.document_state_schema_hypotheses.values()))
                self.assertTrue(loaded.kb.contains(Atom('_state_carrier',(sid,'disk'))))
                r2=self._target(loaded,prefix='again',source='v535_disk_again')
                self.assertEqual(r2['sentence_results'][-1]['status'],'document_coreference_resolved')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

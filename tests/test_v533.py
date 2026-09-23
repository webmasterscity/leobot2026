import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class EventOnlyAblation(Bot):
    def _document_causal_candidates(self, document_facts):
        return []


class V533RepresentationTypeCompetitionTests(unittest.TestCase):
    EVENT=(('epa','eqa'),('epb','eqb'))
    CAUSAL=(('c0a','c0b'),('c1a','c1b'),('c2a','c2b'),('c3a','c3b'))
    TARGET=('tpa','tpb')

    @classmethod
    def relations(cls):
        return tuple(x for fam in cls.EVENT+cls.CAUSAL for x in fam)+cls.TARGET+('activa',)

    def _ground(self,b):
        lines=[]
        for j,n in enumerate(self.relations()):
            lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
        r=b.ingest_document_text(' '.join(lines),source='v533_grammar')
        self.assertEqual(r['relations_promoted'],len(self.relations()))

    def _train_causal(self,b,count=4):
        for i,(p,q) in enumerate(self.CAUSAL[:count]):
            r=b.ingest_document_text(
                f'c{i}u {p} cx{i}. Por eso, c{i}u {q} cy{i}. Eso activa ca{i}.',
                source=f'v533_causal_{i}')
            self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_resolved')
            self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],['latent_document_causal_v533'])
            self.assertEqual(r['document_events_materialized'],0)
            self.assertEqual(r['document_causal_dependencies_materialized'],1)

    def _train_events(self,b):
        for fi,(p,q) in enumerate(self.EVENT):
            for i in range(3):
                b.ingest_document_text(
                    f'e{fi}{i} {p} x{fi}{i}. e{fi}{i} {q} y{fi}{i}.',
                    source=f'v533_event_{fi}_{i}')
            r=b.ingest_document_text(
                f'e{fi}u {p} xo{fi}. e{fi}u {q} yo{fi}. Eso activa ea{fi}.',
                source=f'v533_event_use_{fi}')
            self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_resolved')

    def _trained(self,bot=None,causal_count=4):
        b=bot or Bot(allow_extensional_grounding=False)
        self._ground(b)
        self._train_causal(b,causal_count)
        self._train_events(b)
        return b

    def _target(self,b,prefix='neo',source='v533_target',causal=True):
        p,q=self.TARGET
        middle=f'Por eso, {prefix} {q} {prefix}loc.' if causal else f'Luego, {prefix} {q} {prefix}loc.'
        return b.ingest_document_text(
            f'{prefix} {p} {prefix}obj. {middle} Eso activa {prefix}alarm.',source=source)

    def test_explicit_causal_dependency_is_distinct_representation_type(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        self._train_causal(b,1)
        causal_facts=[f for f in b.kb.facts.values() if f['atom'].pred in {'_causal_from','_causal_to'}]
        self.assertEqual(len(causal_facts),2)
        self.assertFalse(any(f['atom'].pred.startswith('_event_') for f in b.kb.facts.values()))

    def test_predictive_type_support_selects_causal_over_event(self):
        b=self._trained(causal_count=4)
        r=self._target(b)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_causal_v533'])
        evidence=row['references'][0]['evidence'][0]
        sel=evidence['type_selection']
        self.assertEqual(sel['mechanism'],'generated_representation_type_competition_v534')
        supports={x['representation_type']:x['support'] for x in sel['candidates']}
        self.assertEqual(supports['document_dependency:_doc_causes'],4)
        self.assertEqual(supports['event'],2)
        self.assertEqual(r['document_events_materialized'],0)
        self.assertEqual(r['document_causal_dependencies_materialized'],1)

    def test_event_only_ablation_selects_event_on_same_target(self):
        # Train the full state on the treatment class, then disable only the new
        # causal candidate generator to isolate V5.33 at decision time.
        b=self._trained(causal_count=4)
        b._document_dependency_candidates=lambda facts: []
        r=self._target(b,prefix='abl',source='v533_ablation')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertIn('latent_document_event_meta_v527',row['references'][0]['criteria'])
        self.assertEqual(r['document_events_materialized'],1)
        self.assertEqual(r['document_causal_dependencies_materialized'],0)

    def test_equal_type_support_abstains(self):
        b=self._trained(causal_count=2)
        r=self._target(b,prefix='tie',source='v533_tie')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        self.assertEqual(r['document_events_materialized'],0)
        self.assertEqual(r['document_causal_dependencies_materialized'],0)
        self.assertEqual(len(row['candidates']),2)

    def test_after_link_is_generic_temporal_dependency_not_causal(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        p,q=self.CAUSAL[0]
        r=b.ingest_document_text(
            f'ax {p} one. Luego, ax {q} two. Eso activa alarm.',source='v534_after_only')
        self.assertEqual(r['document_links_stored'],1)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_dependency_v534'])
        dep=row['references'][0]['evidence'][0]['dependency_candidate']
        self.assertEqual(dep['link_predicate'],'_doc_precedes')
        self.assertEqual(r['document_causal_dependencies_materialized'],0)

    def test_renaming_same_causal_document_does_not_fake_support(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        p,q=self.CAUSAL[0]
        text=f'cx {p} one. Por eso, cx {q} two. Eso activa alarm.'
        for i in range(4):
            b.ingest_document_text(text,source=f'v533_duplicate_{i}')
        state=next(iter(b.document_causal_reference_hypotheses.values()))
        self.assertEqual(state['support'],1)
        self.assertFalse(state['promoted'])

    def test_causal_gate_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            b=self._trained(ScalableBot(db,allow_extensional_grounding=False),causal_count=4)
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                state=next(iter(loaded.document_causal_reference_hypotheses.values()))
                self.assertEqual(state['support'],4)
                r=self._target(loaded,prefix='persist',source='v533_persist')
                self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],['latent_document_causal_v533'])
                cid=r['sentence_results'][-1]['references'][0]['antecedent']
                self.assertTrue(loaded.kb.contains(Atom('_causal_from',(cid,r['sentence_results'][0]['id']))))
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

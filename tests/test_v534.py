import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V534GeneratedRepresentationTypeTests(unittest.TestCase):
    CAUSAL=(('caa','cab'),('cba','cbb'))
    TEMPORAL=(('taa','tab'),('tba','tbb'),('tca','tcb'),('tda','tdb'))
    EVENT=(('epa','eqa','era'),('epb','eqb','erb'))
    TARGET=('npa','nqa','nra')

    @classmethod
    def relations(cls):
        return (tuple(x for fam in cls.CAUSAL+cls.TEMPORAL+cls.EVENT for x in fam)
                + cls.TARGET + ('activa',))

    def _ground(self,b):
        lines=[]
        for j,n in enumerate(self.relations()):
            lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
        r=b.ingest_document_text(' '.join(lines),source='v534_grammar')
        self.assertEqual(r['relations_promoted'],len(self.relations()))

    @staticmethod
    def _use_dependency(b,names,prefix,temporal):
        p,q=names
        connector='Luego' if temporal else 'Por eso'
        r=b.ingest_document_text(
            f'{prefix} {p} {prefix}x. {connector}, {prefix} {q} {prefix}y. Eso activa {prefix}alarm.',
            source=f'v534_dep_{prefix}')
        assert r['sentence_results'][-1]['status']=='document_coreference_resolved'
        return r

    def _train_dependencies(self,b):
        for i,fam in enumerate(self.CAUSAL):
            r=self._use_dependency(b,fam,f'C{i}',False)
            self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],['latent_document_causal_v533'])
        for i,fam in enumerate(self.TEMPORAL):
            r=self._use_dependency(b,fam,f'T{i}',True)
            self.assertEqual(r['sentence_results'][-1]['references'][0]['criteria'],['latent_document_dependency_v534'])

    def _train_events(self,b):
        for fi,(p,q,rn) in enumerate(self.EVENT):
            for i in range(3):
                b.ingest_document_text(
                    f'E{fi}{i} {p} E{fi}x{i}. E{fi}{i} {q} E{fi}y{i}. E{fi}x{i} {rn} E{fi}z{i}.',
                    source=f'v534_event_train_{fi}_{i}')
            out=b.ingest_document_text(
                f'E{fi}u {p} E{fi}obj. E{fi}u {q} E{fi}loc. E{fi}obj {rn} E{fi}time. Eso activa E{fi}alarm.',
                source=f'v534_event_use_{fi}')
            self.assertEqual(out['sentence_results'][-1]['status'],'document_coreference_resolved')

    def _trained(self,bot=None):
        b=bot or Bot(allow_extensional_grounding=False)
        self._ground(b);self._train_dependencies(b);self._train_events(b);return b

    def _target(self,b,prefix='neo',source='v534_target'):
        p,q,r=self.TARGET
        return b.ingest_document_text(
            f'{prefix} {p} {prefix}obj. Por eso, {prefix} {q} {prefix}loc. '
            f'Luego, {prefix}obj {r} {prefix}time. Eso activa {prefix}alarm.',source=source)

    def test_generator_discovers_causal_and_temporal_types_without_per_type_candidate_code(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        p,q=self.CAUSAL[0];r=b.ingest_document_text(
            f'x {p} one. Por eso, x {q} two.',source='v534_causal_scan')
        facts=[b.kb.get_fact(x['id']) for x in r['sentence_results'] if x.get('id')]
        cands=b._document_dependency_candidates([x for x in facts if x])
        self.assertEqual({x['link_predicate'] for x in cands},{'_doc_causes'})
        p,q=self.TEMPORAL[0];r=b.ingest_document_text(
            f'y {p} one. Luego, y {q} two.',source='v534_temporal_scan')
        facts=[b.kb.get_fact(x['id']) for x in r['sentence_results'] if x.get('id')]
        cands=b._document_dependency_candidates([x for x in facts if x])
        self.assertEqual({x['link_predicate'] for x in cands},{'_doc_precedes'})

    def test_user_injected_internal_looking_link_is_not_a_generated_type(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        p,q=self.CAUSAL[0]
        r=b.ingest_document_text(f'z {p} one. z {q} two.',source='v534_injected_base')
        facts=[b.kb.get_fact(x['id']) for x in r['sentence_results'] if x.get('id')]
        ids=[x['id'] for x in facts if x]
        self.assertEqual(len(ids),2)
        b.kb.add(Atom('_doc_fake',(ids[0],ids[1])),'usuario')
        cands=b._document_dependency_candidates([x for x in facts if x])
        self.assertFalse(any(x['link_predicate']=='_doc_fake' for x in cands))

    def test_three_type_competition_selects_temporal_dependency_by_prior_utility(self):
        b=self._trained()
        r=self._target(b)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_dependency_v534'])
        dep=row['references'][0]['evidence'][0]['dependency_candidate']
        self.assertEqual(dep['link_predicate'],'_doc_precedes')
        selection=row['references'][0]['evidence'][0]['type_selection']
        self.assertEqual(selection['mechanism'],'generated_representation_type_competition_v534')
        supports={x['representation_type']:x['support'] for x in selection['candidates']}
        self.assertEqual(supports['document_dependency:_doc_precedes'],4)
        self.assertEqual(supports['document_dependency:_doc_causes'],2)
        self.assertEqual(supports['event'],2)

    def test_event_only_ablation_cannot_make_the_same_choice(self):
        b=self._trained();b._document_dependency_candidates=lambda facts: []
        r=self._target(b,prefix='abl',source='v534_ablation')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertIn('latent_document_event_meta_v527',row['references'][0]['criteria'])

    def test_equal_best_dependency_types_abstain(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        # Two supports for each generated dependency kind; no event meta topology.
        for i,fam in enumerate(self.CAUSAL): self._use_dependency(b,fam,f'EC{i}',False)
        for i,fam in enumerate(self.TEMPORAL[:2]): self._use_dependency(b,fam,f'ET{i}',True)
        p,q,r=self.TARGET
        out=b.ingest_document_text(
            f'tie {p} tieobj. Por eso, tie {q} tieloc. Luego, tieobj {r} tietime. Eso activa tiealarm.',
            source='v534_equal_types')
        row=out['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        self.assertEqual(out['document_events_materialized'],0)

    def test_generic_dependency_state_persists(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b=self._trained(ScalableBot(db,allow_extensional_grounding=False))
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                supports=sorted((x['link_predicate'],x['support']) for x in loaded.document_dependency_reference_hypotheses.values())
                self.assertIn(('_doc_causes',2),supports)
                self.assertIn(('_doc_precedes',4),supports)
                out=self._target(loaded,prefix='persist',source='v534_persist')
                dep=out['sentence_results'][-1]['references'][0]['evidence'][0]['dependency_candidate']
                self.assertEqual(dep['link_predicate'],'_doc_precedes')
                did=out['sentence_results'][-1]['references'][0]['antecedent']
                self.assertTrue(loaded.kb.contains(Atom('_dependency_kind',(did,'_doc_precedes'))))
            finally:
                loaded.close()

if __name__=='__main__': unittest.main()

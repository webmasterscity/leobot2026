import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V532GeneratedEventScopeCompetitionTests(unittest.TestCase):
    PAIR_FAMILIES=(('paxa','qaxa'),('paxb','qaxb'),('paxc','qaxc'),('paxd','qaxd'))
    TRIPLE_FAMILIES=(('trpa','trqa','trra'),('trpb','trqb','trrb'))
    TARGET=('nova','novb','novc')

    @classmethod
    def _relations(cls, pair_count=4):
        return (tuple(x for fam in cls.PAIR_FAMILIES[:pair_count] for x in fam)
                + tuple(x for fam in cls.TRIPLE_FAMILIES for x in fam)
                + cls.TARGET + ('activa',))

    def _ground(self, bot, pair_count=4):
        lines=[]
        for j,name in enumerate(self._relations(pair_count)):
            lines += [f'g{j}a {name} h{j}a.',f'g{j}b {name} h{j}b.',f'g{j}c {name} h{j}c.']
        r=bot.ingest_document_text(' '.join(lines),source=f'v532_grammar_{pair_count}')
        self.assertEqual(r['relations_promoted'],len(self._relations(pair_count)))

    @staticmethod
    def _train_pair(bot,names,prefix):
        p,q=names
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}x{i}. {prefix}{i} {q} {prefix}y{i}.',
                source=f'{prefix}_train_{i}')
        r=bot.ingest_document_text(
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. Eso activa {prefix}alarm.',
            source=f'{prefix}_use')
        assert r['sentence_results'][-1]['status']=='document_coreference_resolved'

    @staticmethod
    def _train_triple(bot,names,prefix):
        p,q,rn=names
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}x{i}. {prefix}{i} {q} {prefix}y{i}. '
                f'{prefix}x{i} {rn} {prefix}z{i}.',source=f'{prefix}_train_{i}')
        r=bot.ingest_document_text(
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. '
            f'{prefix}obj {rn} {prefix}time. Eso activa {prefix}alarm.',source=f'{prefix}_use')
        assert r['sentence_results'][-1]['status']=='document_coreference_resolved'

    def _trained(self,pair_count=4,bot=None):
        b=bot or Bot(allow_extensional_grounding=False)
        self._ground(b,pair_count)
        for i,fam in enumerate(self.PAIR_FAMILIES[:pair_count]):
            self._train_pair(b,fam,f'P{i}')
        for i,fam in enumerate(self.TRIPLE_FAMILIES):
            self._train_triple(b,fam,f'T{i}')
        return b

    def _target(self,bot,prefix='neo',source='v532_target'):
        p,q,rn=self.TARGET
        return bot.ingest_document_text(
            f'{prefix} {p} {prefix}obj. {prefix} {q} {prefix}loc. '
            f'{prefix}obj {rn} {prefix}time. Eso activa {prefix}alarm.',source=source)

    def test_predictive_support_can_select_smaller_subevent_over_maximal_cluster(self):
        b=self._trained(pair_count=4)
        r=self._target(b)
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        ev=row['references'][0]['evidence'][0]['event_candidate']
        self.assertEqual(len(ev['member_fact_ids']),2)
        sel=ev['scope_selection']
        self.assertEqual(sel['mechanism'],'predictive_scope_competition_v532')
        self.assertEqual(sel['support'],4)
        self.assertEqual(sel['runner_up_support'],2)
        self.assertEqual(sorted(len(x['members']) for x in sel['candidates']),[2,3])

    def test_v531_maximal_cluster_ablation_selects_different_scope(self):
        b=self._trained(pair_count=4)
        def maximal_only(candidates,pred,slot):
            viable=[c for c in candidates if b._document_event_reference_gate_allows(c,pred,slot)]
            return b._maximal_document_event_candidates(viable),{'status':'v531_maximal_ablation'}
        b._select_document_event_scopes=maximal_only
        r=self._target(b,prefix='zen',source='v532_ablation')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        ev=row['references'][0]['evidence'][0]['event_candidate']
        self.assertEqual(len(ev['member_fact_ids']),3)

    def test_equal_predictive_support_abstains_instead_of_size_tiebreak(self):
        b=self._trained(pair_count=2)
        r=self._target(b,prefix='tie',source='v532_tie')
        row=r['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        self.assertEqual(r['document_events_materialized'],0)
        self.assertEqual(len(row['candidates']),2)

    def test_one_meta_transferred_target_does_not_self_increase_scope_support(self):
        b=self._trained(pair_count=4)
        before=sorted(s['support'] for s in b.document_event_reference_hypotheses.values() if s.get('promoted'))
        self.assertEqual(before,[2,4])
        r=self._target(b,prefix='novel',source='v532_single_meta_use')
        self.assertEqual(r['sentence_results'][-1]['status'],'document_coreference_resolved')
        after=sorted(s['support'] for s in b.document_event_reference_hypotheses.values() if s.get('promoted'))
        self.assertEqual(after,[2,4])

    def test_scope_competition_survives_scalable_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            b=self._trained(pair_count=4,bot=ScalableBot(db,allow_extensional_grounding=False))
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                r=self._target(loaded,prefix='persist',source='v532_persist')
                ev=r['sentence_results'][-1]['references'][0]['evidence'][0]['event_candidate']
                self.assertEqual(len(ev['member_fact_ids']),2)
                self.assertEqual(ev['scope_selection']['mechanism'],'predictive_scope_competition_v532')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

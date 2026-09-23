import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V531AutonomousRepresentationChoiceTests(unittest.TestCase):
    META_FAMILIES=(('zeta','kora','miva'),('zeti','kori','mivi'),('zetu','koru','mivu'),('zeto','koro','mivo'),('zetaq','koraq','mivaq'))
    RELATIONS=('frobla','tulka','norga','peka','rula','soma','activa') + tuple(x for fam in META_FAMILIES for x in fam)

    def _ground(self, bot):
        lines=[]
        for j,name in enumerate(self.RELATIONS):
            lines += [f'a{j}x {name} b{j}x.', f'a{j}y {name} b{j}y.', f'a{j}z {name} b{j}z.']
        result=bot.ingest_document_text(' '.join(lines),source='v531_grammar')
        self.assertEqual(result['relations_promoted'],len(self.RELATIONS))

    @staticmethod
    def _train_family(bot,names,prefix):
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

    def _trained(self, bot=None):
        b=bot or Bot(allow_extensional_grounding=False)
        self._ground(b)
        self._train_family(b,('frobla','tulka','norga'),'f')
        self.assertEqual(self._use_family(b,('frobla','tulka','norga'),'f')['sentence_results'][-1]['status'],
                         'document_coreference_resolved')
        self._train_family(b,('peka','rula','soma'),'g')
        self.assertEqual(self._use_family(b,('peka','rula','soma'),'g')['sentence_results'][-1]['status'],
                         'document_coreference_resolved')
        return b

    @staticmethod
    def _contrary_episode(bot,prefix,names=('zeta','kora','miva'),source=None,include_confirmation=True):
        p,q,r=names
        tail=f' {prefix}obj activa {prefix}alarm.' if include_confirmation else ''
        return bot.ingest_document_text(
            f'{prefix}obj activa {prefix}old. '
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. '
            f'Eso activa {prefix}alarm.'+tail,
            source=source or f'{prefix}_choice')

    def test_future_explicit_fact_autonomously_revises_first_surprise(self):
        b=self._trained()
        r=self._contrary_episode(b,'x')
        self.assertEqual(r['sentence_results'][4]['status'],'document_coreference_resolved')
        choices=list(b.document_event_choice_hypotheses.values())
        self.assertEqual(len(choices),1)
        self.assertEqual(choices[0]['event_support'],2)
        self.assertEqual(choices[0]['independent_support'],1)
        self.assertEqual(choices[0]['decision'],'abstain')
        self.assertTrue(any(a.get('event')=='document_event_representation_auto_revised' for a in b.kb.audit))
        again=b.ingest_document_text(
            'z zeta zo. z kora zl. z miva zt. Eso activa za.',source='v531_after_surprise')
        self.assertEqual(again['sentence_results'][3]['status'],'document_coreference_unresolved')
        self.assertEqual(again['document_events_materialized'],0)

    def test_repeated_independent_confirmation_can_select_entity_hypothesis(self):
        b=self._trained()
        for prefix,names in zip(('x','y','w','q'),self.META_FAMILIES[:4]):
            self._contrary_episode(b,prefix,names=names)
        choice=next(iter(b.document_event_choice_hypotheses.values()))
        self.assertEqual(choice['event_support'],2)
        self.assertEqual(choice['independent_support'],4)
        self.assertEqual(choice['decision'],'independent')
        target=self._contrary_episode(b,'n',names=self.META_FAMILIES[4],include_confirmation=False)
        row=target['sentence_results'][4]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['args'][0],'nobj')
        self.assertEqual(target['document_events_materialized'],0)

    def test_same_document_content_cannot_manufacture_independent_support(self):
        b=self._trained()
        text=('xobj activa xold. xu zeta xobj. xu kora xloc. xu miva xtime. '
              'Eso activa xalarm. xobj activa xalarm.')
        b.ingest_document_text(text,source='v531_dup_a')
        b.ingest_document_text(text,source='v531_dup_b')
        choice=next(iter(b.document_event_choice_hypotheses.values()))
        self.assertEqual(choice['independent_support'],1)
        self.assertEqual(choice['decision'],'abstain')

    def test_three_contrary_episodes_are_still_insufficient_to_force_entity(self):
        b=self._trained()
        for prefix,names in zip(('x','y','w'),self.META_FAMILIES[:3]):
            self._contrary_episode(b,prefix,names=names)
        choice=next(iter(b.document_event_choice_hypotheses.values()))
        self.assertEqual(choice['independent_support'],3)
        self.assertEqual(choice['decision'],'abstain')
        target=self._contrary_episode(b,'n',names=self.META_FAMILIES[4],include_confirmation=False)
        self.assertEqual(target['sentence_results'][4]['status'],'document_coreference_ambiguous')
        self.assertEqual(target['document_events_materialized'],0)

    def test_choice_state_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            b=self._trained(ScalableBot(db,allow_extensional_grounding=False))
            for prefix,names in zip(('x','y','w','q'),self.META_FAMILIES[:4]):
                self._contrary_episode(b,prefix,names=names)
            self.assertEqual(next(iter(b.document_event_choice_hypotheses.values()))['decision'],'independent')
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                choice=next(iter(loaded.document_event_choice_hypotheses.values()))
                self.assertEqual(choice['independent_support'],4)
                self.assertEqual(choice['decision'],'independent')
                target=self._contrary_episode(loaded,'n',names=self.META_FAMILIES[4],source='v531_after_reload',include_confirmation=False)
                self.assertEqual(target['sentence_results'][4]['args'][0],'nobj')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

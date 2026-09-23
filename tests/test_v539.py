import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot
from test_v538 import V538CrossTypeLatentStrategyTests


class V539GenericLatentCounterevidenceTests(unittest.TestCase):
    def _prepare(self,bot=None):
        helper=V538CrossTypeLatentStrategyTests()
        return helper._prepare(True,bot)

    @staticmethod
    def _surprise(bot,prefix='neo',source='v539_surprise'):
        return bot.ingest_document_text(
            f'{prefix} zeta {prefix}shared. {prefix}shared entrega {prefix}caja a {prefix}luis. '
            f'Eso activa {prefix}alarm. {prefix} activa {prefix}alarm.',source=source)

    @staticmethod
    def _plain_target(bot,prefix='later',source='v539_later'):
        return bot.ingest_document_text(
            f'{prefix} zeta {prefix}shared. {prefix}shared entrega {prefix}caja a {prefix}luis. '
            f'Eso activa {prefix}alarm.',source=source)

    def test_future_explicit_fact_retracts_wrong_generic_bundle_and_withdraws_policy(self):
        bot=self._prepare()
        result=self._surprise(bot)
        first=result['sentence_results'][2]
        self.assertEqual(first['status'],'document_coreference_resolved')
        self.assertEqual(first['references'][0]['criteria'],['latent_document_bundle_meta_v538'])
        bundle_id=first['references'][0]['antecedent'];wrong_fact_id=first['id']
        self.assertIsNone(bot.kb.get_fact(wrong_fact_id))
        self.assertEqual(bot._facts_referencing_entity(bundle_id),[])
        policy=next(iter(bot.document_latent_strategy_hypotheses.values()))
        self.assertTrue(policy['contested'])
        self.assertFalse(policy['promoted'])
        self.assertEqual(len(policy['counterexamples']),1)
        events=[a for a in bot.kb.audit if a.get('event')=='document_latent_strategy_counterexample']
        self.assertEqual(len(events),1)
        self.assertTrue(events[0]['policy_withdrawn'])

    def test_withdrawn_policy_prevents_repeating_same_transfer(self):
        bot=self._prepare();self._surprise(bot)
        later=self._plain_target(bot)
        self.assertEqual(later['sentence_results'][-1]['status'],'document_coreference_unresolved')
        self.assertEqual(later['document_latent_bundles_materialized'],0)

    def test_without_future_confirmation_policy_remains_active(self):
        bot=self._prepare()
        first=self._plain_target(bot,prefix='first',source='v539_no_surprise')
        self.assertEqual(first['sentence_results'][-1]['status'],'document_coreference_resolved')
        policy=next(iter(bot.document_latent_strategy_hypotheses.values()))
        self.assertTrue(policy['promoted']);self.assertFalse(policy['contested'])
        # Fresh equivalent state avoids exact target event learning from repeated
        # documents; the policy itself remains capable of transfer.
        other=self._prepare()
        later=self._plain_target(other,prefix='second',source='v539_no_surprise_2')
        self.assertEqual(later['sentence_results'][-1]['references'][0]['criteria'],
                         ['latent_document_bundle_meta_v538'])

    def test_unrelated_later_fact_does_not_withdraw_policy(self):
        bot=self._prepare()
        result=bot.ingest_document_text(
            'neo zeta shared. shared entrega caja a luis. Eso activa alarm. neo observa otra.',
            source='v539_unrelated')
        self.assertEqual(result['sentence_results'][2]['status'],'document_coreference_resolved')
        policy=next(iter(bot.document_latent_strategy_hypotheses.values()))
        self.assertTrue(policy['promoted']);self.assertFalse(policy['contested'])
        self.assertEqual(policy['counterexamples'],[])

    def test_one_new_exact_event_use_does_not_reactivate_contested_policy(self):
        bot=self._prepare()
        self._surprise(bot)
        policy=next(iter(bot.document_latent_strategy_hypotheses.values()))
        previous_sources={row['schema_id'] for row in policy['source_representations']}
        self.assertTrue(policy['contested'])

        helper=V538CrossTypeLatentStrategyTests()
        for name,prefix in (('trenza','fresh_a'),('sella','fresh_b')):
            helper._teach_binary(bot,name,prefix)
        for i in range(3):
            bot.ingest_document_text(
                f'q{i} trenza qo{i}. q{i} sella ql{i}.',source=f'v539_new_event_{i}')
        used=bot.ingest_document_text(
            'qu trenza qo. qu sella ql. Eso activa qalarm.',source='v539_new_event_use')
        self.assertEqual(used['sentence_results'][-1]['references'][0]['criteria'],
                         ['latent_document_event_v525'])

        policy=next(iter(bot.document_latent_strategy_hypotheses.values()))
        self.assertEqual(len(policy['source_representations']),3)
        self.assertEqual(len({row['schema_id'] for row in policy['source_representations']}
                             -previous_sources),1)
        self.assertTrue(policy['contested'])
        self.assertFalse(policy['promoted'])
        later=self._plain_target(bot,prefix='after_new_exact',source='v539_after_new_exact')
        self.assertEqual(later['sentence_results'][-1]['status'],
                         'document_coreference_unresolved')

    def test_contested_strategy_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            bot=self._prepare(ScalableBot(db,allow_extensional_grounding=False))
            self._surprise(bot,prefix='disk',source='v539_disk_surprise')
            bot.save(side);bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                policy=next(iter(loaded.document_latent_strategy_hypotheses.values()))
                self.assertTrue(policy['contested']);self.assertFalse(policy['promoted'])
                later=self._plain_target(loaded,prefix='after',source='v539_after_reload')
                self.assertEqual(later['sentence_results'][-1]['status'],'document_coreference_unresolved')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

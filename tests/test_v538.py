import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V538CrossTypeLatentStrategyTests(unittest.TestCase):
    BINARIES=('evone','evtwo','stone','sttwo','ruido','zeta','conecta','activa','observa')

    @staticmethod
    def _teach_binary(bot,name,prefix):
        for suffix in ('a','b','c'):
            bot.respond(f'{prefix}{suffix} {name} {prefix}x{suffix}')

    def _ground(self,bot):
        for i,name in enumerate(self.BINARIES):
            self._teach_binary(bot,name,f'g{i}')
        learned=None
        for text in ('ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora'):
            learned=bot.respond(text)
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertEqual(learned['arity'],3)

    @staticmethod
    def _train_event(bot):
        for i in range(3):
            bot.ingest_document_text(
                f'e{i} evone eo{i}. e{i} evtwo el{i}.',source=f'v538_event_train_{i}')
        used=bot.ingest_document_text(
            'eu evone eobj. eu evtwo eloc. Eso activa ealarm.',source='v538_event_use')
        row=used['sentence_results'][-1]
        assert row['status']=='document_coreference_resolved'
        assert row['references'][0]['criteria']==['latent_document_event_v525']

    @staticmethod
    def _train_state(bot):
        for i in range(3):
            bot.ingest_document_text(
                f's{i} stone sx{i}. n{i} ruido m{i}. s{i} sttwo sy{i}.',source=f'v538_state_train_{i}')
        used=bot.ingest_document_text(
            'su stone sx. n ruido m. su sttwo sy. Eso activa salarm.',source='v538_state_use')
        row=used['sentence_results'][-1]
        assert row['status']=='document_coreference_resolved'
        assert row['references'][0]['criteria']==['latent_document_state_v535']

    def _prepare(self,two_types=True,bot=None):
        bot=bot or Bot(allow_extensional_grounding=False)
        self._ground(bot)
        self._train_event(bot)
        if two_types:
            self._train_state(bot)
        return bot

    @staticmethod
    def _target(bot,prefix='neo',source='v538_target',consumer='activa'):
        return bot.ingest_document_text(
            f'{prefix} zeta {prefix}shared. {prefix}shared entrega {prefix}caja a {prefix}luis. '
            f'Eso {consumer} {prefix}alarm.',source=source)

    def test_event_plus_state_promote_type_agnostic_latent_strategy(self):
        bot=self._prepare(True)
        promoted=[x for x in bot.document_latent_strategy_hypotheses.values() if x.get('promoted')]
        self.assertEqual(len(promoted),1)
        row=promoted[0]
        self.assertEqual(row['support'],2)
        self.assertEqual(row['source_families'],['event','state'])
        self.assertEqual(row['constraints']['fact_count'],2)
        self.assertTrue(row['constraints']['connected'])
        self.assertEqual(row['constraints']['shared_role_count'],1)

    def test_strategy_transfers_to_new_arity_and_unknown_representation_family(self):
        bot=self._prepare(True)
        result=self._target(bot)
        row=result['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_bundle_meta_v538'])
        bundle=row['references'][0]['evidence'][0]['bundle_candidate']
        self.assertEqual(bundle['representation_type'],'generic_latent_bundle')
        self.assertEqual(bundle['features']['fact_count'],2)
        # The second member is genuinely ternary; source event/state structures were binary.
        atoms=[bot.kb.get_fact(fid)['atom'] for fid in bundle['member_fact_ids']]
        self.assertEqual(sorted(len(a.args) for a in atoms),[2,3])
        self.assertEqual(result['document_latent_bundles_materialized'],1)
        self.assertEqual(result['document_events_materialized'],0)
        self.assertEqual(result['document_states_materialized'],0)
        self.assertEqual(result['document_dependencies_materialized'],0)

    def test_one_source_representation_family_is_not_enough(self):
        bot=self._prepare(False)
        self.assertFalse(any(x.get('promoted') for x in bot.document_latent_strategy_hypotheses.values()))
        result=self._target(bot,prefix='solo',source='v538_one_source')
        self.assertEqual(result['sentence_results'][-1]['status'],'document_coreference_unresolved')
        self.assertEqual(result['document_latent_bundles_materialized'],0)

    def test_two_matching_bundles_abstain_instead_of_using_recency(self):
        bot=self._prepare(True)
        result=bot.ingest_document_text(
            'a zeta b. b entrega c a d. d conecta e. Eso activa alarma.',source='v538_ambiguous')
        row=result['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_ambiguous')
        evidence=row['candidate_evidence']
        bundle_rows=[r for rows in evidence.values() for r in rows if r.get('bundle_candidate')]
        self.assertEqual(len(bundle_rows),2)
        self.assertEqual(result['document_latent_bundles_materialized'],0)

    def test_consumer_role_is_part_of_learned_strategy_and_transfers_do_not_self_credit(self):
        bot=self._prepare(True)
        policy=next(x for x in bot.document_latent_strategy_hypotheses.values() if x.get('promoted'))
        before=(policy['support'],len(policy['source_representations']))
        row=self._target(bot,prefix='m0',source='v538_meta_use_0')['sentence_results'][-1]
        self.assertEqual(row['status'],'document_coreference_resolved')
        policy=next(x for x in bot.document_latent_strategy_hypotheses.values() if x.get('promoted'))
        self.assertEqual((policy['support'],len(policy['source_representations'])),before)
        # Use a fresh equivalent state for the consumer-role control so repeated
        # target episodes cannot legitimately teach an exact event schema.
        other=self._prepare(True)
        wrong=self._target(other,prefix='wrong',source='v538_wrong_consumer',consumer='observa')
        self.assertEqual(wrong['sentence_results'][-1]['status'],'document_coreference_unresolved')

    def test_strategy_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            bot=self._prepare(True,ScalableBot(db,allow_extensional_grounding=False))
            bot.save(side);bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(x.get('promoted') for x in loaded.document_latent_strategy_hypotheses.values()))
                row=self._target(loaded,prefix='disk',source='v538_disk')['sentence_results'][-1]
                self.assertEqual(row['status'],'document_coreference_resolved')
                self.assertEqual(row['references'][0]['criteria'],['latent_document_bundle_meta_v538'])
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

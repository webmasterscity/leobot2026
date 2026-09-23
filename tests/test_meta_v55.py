import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from tests.test_meta_v54 import teach_late_inversion
from tests.test_meta_v53 import teach_reverse_domain

DEFAULT_INV=[(False,False),(False,True),(True,False),(True,True)]


def train_stationary(bot, n=3):
    rows=[]
    for i in range(n):
        bot.concepts.invention_policy_order=list(DEFAULT_INV)
        rows.append(teach_late_inversion(bot,i))
    return rows


class V55ReplayCoverageTests(unittest.TestCase):
    def test_stationary_policy_does_not_pay_shadow_cost(self):
        bot=Bot(); bot.concepts.max_relation_length=2; bot.concepts.invention_shadow_probe_budget=24
        rows=train_stationary(bot,3)
        self.assertTrue(bot.concepts.invention_candidate_policy.startswith('synth:'))
        self.assertEqual([r['learning'].get('invention_shadow_attempts',0) for r in rows],[0,0,0])

    def test_shadow_expansion_adapts_after_distribution_shift(self):
        bot=Bot(); bot.concepts.max_relation_length=2; bot.concepts.invention_shadow_probe_budget=24
        train_stationary(bot,3)
        before=bot.concepts.invention_candidate_policy
        bot.concepts.invention_policy_order=list(DEFAULT_INV)
        shifted=teach_reverse_domain(bot,50)['learning']
        dream=shifted['dream_replay_policy']
        self.assertEqual(shifted['invention_attempts'],4)
        self.assertGreater(shifted.get('invention_shadow_attempts',0),0)
        self.assertTrue(dream['regime_reset'])
        self.assertNotEqual(bot.concepts.invention_candidate_policy,before)
        bot.concepts.invention_policy_order=list(DEFAULT_INV)
        follow=teach_reverse_domain(bot,51)['learning']
        self.assertEqual(follow['invention_attempts'],1)
        self.assertEqual(follow.get('invention_shadow_attempts',0),0)
        self.assertFalse(any('shadow_for:' in ev for r in bot.kb.rules.values() for ev in r.evidence))

    def test_without_shadow_same_shift_does_not_recover(self):
        bot=Bot(); bot.concepts.max_relation_length=2; bot.concepts.invention_shadow_probe_budget=0
        train_stationary(bot,3)
        before=bot.concepts.invention_candidate_policy
        attempts=[]
        for i in range(50,53):
            bot.concepts.invention_policy_order=list(DEFAULT_INV)
            attempts.append(teach_reverse_domain(bot,i)['learning']['invention_attempts'])
        self.assertEqual(attempts,[4,4,4])
        self.assertEqual(bot.concepts.invention_candidate_policy,before)


    def test_replay_history_and_threshold_persist(self):
        bot=Bot(); bot.concepts.max_relation_length=2; bot.concepts.invention_shadow_probe_budget=24
        train_stationary(bot,3)
        before_worlds=list(bot.concepts.invention_candidate_replay_worlds)
        before_threshold=bot.concepts._shadow_probe_threshold()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            self.assertEqual(loaded.concepts.invention_candidate_replay_worlds,before_worlds)
            self.assertEqual(loaded.concepts._shadow_probe_threshold(),before_threshold)
            self.assertEqual(loaded.concepts.invention_shadow_probe_budget,24)

    def test_stationary_after_restart_does_not_trigger_shadow_probe(self):
        bot=Bot(); bot.concepts.max_relation_length=2; bot.concepts.invention_shadow_probe_budget=24
        train_stationary(bot,3)
        policy=bot.concepts.invention_candidate_policy
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            loaded.concepts.max_relation_length=2
            loaded.concepts.invention_policy_order=list(DEFAULT_INV)
            out=teach_late_inversion(loaded,99)['learning']
            self.assertEqual(out.get('invention_shadow_attempts',0),0)
            self.assertEqual(loaded.concepts.invention_candidate_policy,policy)
            self.assertFalse(out['dream_replay_policy']['regime_reset'])
    def test_shadow_policy_and_budget_persist(self):
        bot=Bot(); bot.concepts.max_relation_length=2; bot.concepts.invention_shadow_probe_budget=24
        train_stationary(bot,3)
        bot.concepts.invention_policy_order=list(DEFAULT_INV)
        teach_reverse_domain(bot,50)
        policy=bot.concepts.invention_candidate_policy
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            self.assertEqual(loaded.concepts.invention_shadow_probe_budget,24)
            self.assertEqual(loaded.concepts.invention_candidate_policy,policy)
            loaded.concepts.max_relation_length=2
            loaded.concepts.invention_policy_order=list(DEFAULT_INV)
            out=teach_reverse_domain(loaded,51)
            self.assertEqual(out['learning']['invention_attempts'],1)


if __name__=='__main__': unittest.main()

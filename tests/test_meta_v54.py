import tempfile
import unittest
from pathlib import Path

from leobot import Bot, Atom


def add_late_inversion_chain(bot, idx, prefix):
    r, s = f'r{idx}', f's{idx}'
    n = [f'{prefix}{i}' for i in range(5)]
    for pred, a, b in [
        (r, n[1], n[0]), (s, n[1], n[2]),
        (r, n[3], n[2]), (s, n[3], n[4]),
    ]:
        bot.kb.add(Atom(pred, (a, b)), 'world')
    return n[0], n[4]


def teach_late_inversion(bot, idx):
    positives = [add_late_inversion_chain(bot, idx, f'd{idx}p{j}_') for j in range(2)]
    negatives = []
    for j in range(2):
        a, b = f'd{idx}n{j}a', f'd{idx}n{j}b'
        bot.kb.add(Atom(f'other{idx}', (a, b)), 'world')
        negatives.append((a, b))
    surface = f'invprofundo{idx}'
    out = None
    for a, b in positives:
        out = bot.observe_concept_statement(f'{a} {surface} {b}')
    for a, b in negatives:
        out = bot.observe_concept_statement(f'{a} no {surface} {b}')
    return out


class V54ReplayPolicySynthesisTests(unittest.TestCase):
    def test_replay_synthesizes_policy_outside_legacy_menu(self):
        bot = Bot(); bot.concepts.max_relation_length = 2
        out = teach_late_inversion(bot, 0)
        self.assertEqual(out['status'], 'concept_learned')
        dream = out['learning']['dream_replay_policy']
        self.assertTrue(bot.concepts.invention_candidate_policy.startswith('synth:'))
        self.assertLess(dream['replay_cost_after'], dream['replay_cost_before'])
        world = bot.concepts.invention_candidate_replay_worlds[-1]
        legacy = [bot.concepts._candidate_world_score(world, p)
                  for p in ('baseline','reverse_first','forward_first','same_first')]
        legacy = [x for x in legacy if x is not None]
        self.assertTrue(legacy)
        self.assertLess(dream['replay_cost_after'], min(legacy))

    def test_synthesized_policy_reduces_next_domain_search(self):
        seed = Bot(); seed.concepts.max_relation_length = 2
        first = teach_late_inversion(seed, 1)
        self.assertEqual(first['status'], 'concept_learned')
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'; seed.save(path)
            treatment = Bot.load(path); control = Bot.load(path)
            treatment.concepts.max_relation_length = 2
            control.concepts.max_relation_length = 2
            default_inv=[(False,False),(False,True),(True,False),(True,True)]
            treatment.concepts.invention_policy_order=list(default_inv)
            control.concepts.invention_policy_order=list(default_inv)
            control.concepts.invention_candidate_policy = 'forward_first'
            t = teach_late_inversion(treatment, 2)['learning']
            c = teach_late_inversion(control, 2)['learning']
        self.assertLessEqual(t['invention_attempts'], 3)
        self.assertGreater(c['invention_attempts'], t['invention_attempts'])
        self.assertLess(t['invention_total_target_candidates'], c['invention_total_target_candidates'])

    def test_synthesized_policy_persists(self):
        bot = Bot(); bot.concepts.max_relation_length = 2
        teach_late_inversion(bot, 3)
        learned = bot.concepts.invention_candidate_policy
        self.assertTrue(learned.startswith('synth:'))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'; bot.save(path); loaded = Bot.load(path)
            self.assertEqual(loaded.concepts.invention_candidate_policy, learned)
            loaded.concepts.max_relation_length = 2
            out = teach_late_inversion(loaded, 4)
            self.assertEqual(out['learning']['invention_attempts'], 1)


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot, Atom


def add_chain(bot, r, s, prefix):
    nodes=[f'{prefix}{i}' for i in range(5)]
    for pred,a,b in [(r,nodes[0],nodes[1]),(s,nodes[1],nodes[2]),
                     (r,nodes[2],nodes[3]),(s,nodes[3],nodes[4])]:
        bot.kb.add(Atom(pred,(a,b)),'world')
    return nodes[0],nodes[4]


def teach_domain(bot, idx):
    r,s=f'r{idx}',f's{idx}'
    positives=[add_chain(bot,r,s,f'd{idx}a_'),add_chain(bot,r,s,f'd{idx}b_')]
    negatives=[]
    for j in range(2):
        a,b=f'd{idx}n{j}a',f'd{idx}n{j}b'
        bot.kb.add(Atom(f'other{idx}',(a,b)),'world');negatives.append((a,b))
    surface=f'vinculo{idx}'
    out=None
    for a,b in positives: out=bot.observe_concept_statement(f'{a} {surface} {b}')
    for a,b in negatives: out=bot.observe_concept_statement(f'{a} no {surface} {b}')
    return out


def add_reverse_chain(bot, r, s, prefix):
    nodes=[f'{prefix}{i}' for i in range(5)]
    for pred,a,b in [(s,nodes[0],nodes[1]),(r,nodes[1],nodes[2]),
                     (s,nodes[2],nodes[3]),(r,nodes[3],nodes[4])]:
        bot.kb.add(Atom(pred,(a,b)),'world')
    return nodes[0],nodes[4]


def teach_reverse_domain(bot, idx):
    r,s=f'r{idx}',f's{idx}'
    positives=[add_reverse_chain(bot,r,s,f'd{idx}a_'),add_reverse_chain(bot,r,s,f'd{idx}b_')]
    negatives=[]
    for j in range(2):
        a,b=f'd{idx}n{j}a',f'd{idx}n{j}b'
        bot.kb.add(Atom(f'other{idx}',(a,b)),'world');negatives.append((a,b))
    surface=f'reverso{idx}'
    out=None
    for a,b in positives: out=bot.observe_concept_statement(f'{a} {surface} {b}')
    for a,b in negatives: out=bot.observe_concept_statement(f'{a} no {surface} {b}')
    return out


class V53DreamReplayTests(unittest.TestCase):
    def test_replay_policy_reduces_future_invention_attempts(self):
        bot=Bot();bot.concepts.max_relation_length=2
        first=teach_domain(bot,0)
        self.assertEqual(first['status'],'concept_learned')
        self.assertEqual(first['learning']['invention_attempts'],2)
        self.assertEqual(bot.concepts.invention_candidate_policy,'forward_first')
        self.assertTrue(first['learning']['dream_replay_policy']['updated'])
        second=teach_domain(bot,1)
        self.assertEqual(second['status'],'concept_learned')
        self.assertEqual(second['learning']['invention_attempts'],1)
        self.assertEqual(second['learning']['invention_candidate_policy'],'forward_first')

    def test_fixed_policy_control_does_not_get_the_reduction(self):
        attempts=[]
        for idx in (0,1):
            bot=Bot();bot.concepts.max_relation_length=2
            out=teach_domain(bot,idx)
            attempts.append(out['learning']['invention_attempts'])
        self.assertEqual(attempts,[2,2])

    def test_distribution_shift_triggers_regret_reset_and_fast_relearning(self):
        bot=Bot();bot.concepts.max_relation_length=2
        teach_domain(bot,0)
        self.assertEqual(bot.concepts.invention_candidate_policy,'forward_first')
        shifted=teach_reverse_domain(bot,50)
        self.assertTrue(shifted['learning']['dream_replay_policy']['regime_reset'])
        self.assertEqual(bot.concepts.invention_candidate_policy,'reverse_first')
        next_one=teach_reverse_domain(bot,51)
        self.assertEqual(next_one['learning']['invention_attempts'],1)
        self.assertEqual(bot.concepts.invention_candidate_regime_resets,1)

    def test_replay_policy_persists_across_restart(self):
        bot=Bot();bot.concepts.max_relation_length=2
        teach_domain(bot,0)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json';bot.save(path);loaded=Bot.load(path)
            loaded.concepts.max_relation_length=2
            self.assertEqual(loaded.concepts.invention_candidate_policy,'forward_first')
            out=teach_domain(loaded,2)
            self.assertEqual(out['learning']['invention_attempts'],1)


if __name__=='__main__': unittest.main()

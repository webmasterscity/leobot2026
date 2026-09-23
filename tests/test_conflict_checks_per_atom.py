"""G-36b: contradiction checks decided per atom, not per predicate."""
import unittest

from leobot import Bot
from leobot.core import Atom, Rule
from tests.test_conflict_checks_scale import chain_bot


class PerAtomConflictTests(unittest.TestCase):
    def test_unrelated_negative_fact_does_not_make_result_incomplete(self):
        # 70 children: more proof atoms than the 64 conflict checks, depth 1.
        bot=chain_bot(0)
        for i in range(70):
            bot.kb.add(Atom('padre',('raiz',f'h{i}')),'prueba')
        bot.kb.add(Atom('!padre',('otro','ajeno')),'prueba')
        result=bot.answer_atom(Atom('ancestro',('raiz','?y')))
        self.assertEqual(result['status'],'bindings')
        self.assertEqual(len(result['proofs']),70)

    def test_explicit_opposite_of_a_proof_atom_contests(self):
        bot=chain_bot(5)
        bot.kb.add(Atom('!padre',('n1','n2')),'prueba')
        self.assertIn(bot.answer_atom(Atom('ancestro',('n0','n3')))['status'],('conflict','contested'))

    def test_rule_derived_negation_is_still_detected(self):
        bot=chain_bot(5)
        bot.kb.add(Atom('bloqueo',('n1','n2')),'prueba')
        bot.kb.add_rule(Rule('neg',Atom('!padre',('?x','?y')),(Atom('bloqueo',('?x','?y')),)))
        self.assertIn(bot.answer_atom(Atom('ancestro',('n0','n3')))['status'],('conflict','contested'))


if __name__=='__main__':
    unittest.main()

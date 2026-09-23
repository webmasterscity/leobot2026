"""Conflict checks only query opposites that some fact or rule could establish."""
import unittest

from leobot import Bot
from leobot.core import Atom, Rule


def chain_bot(length):
    bot=Bot()
    for i in range(length):
        bot.kb.add(Atom('padre',(f'n{i}',f'n{i+1}')),'prueba')
    bot.kb.add_rule(Rule('base',Atom('ancestro',('?x','?y')),(Atom('padre',('?x','?y')),)))
    bot.kb.add_rule(Rule('paso',Atom('ancestro',('?x','?z')),
                         (Atom('padre',('?x','?y')),Atom('ancestro',('?y','?z')))))
    return bot


class ConflictCheckScaleTests(unittest.TestCase):
    def test_many_answers_without_negative_knowledge_are_complete(self):
        result=chain_bot(40).answer_atom(Atom('ancestro',('n0','?y')))
        self.assertEqual(result['status'],'bindings')
        self.assertEqual(len(result['proofs']),40)

    def test_explicit_negation_is_still_detected(self):
        bot=chain_bot(5)
        bot.kb.add(Atom('!ancestro',('n0','n3')),'prueba')
        self.assertIn(bot.answer_atom(Atom('ancestro',('n0','n3')))['status'],('conflict','contested'))


if __name__=='__main__':
    unittest.main()

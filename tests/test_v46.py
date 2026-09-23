import unittest

from leobot.bot import Bot
from leobot.core import KnowledgeBase


def raw_relation_bot():
    bot=Bot(KnowledgeBase())
    for text in [
        'equipo alfa enlaza modulo rojo',
        'grupo beta enlaza pieza azul',
        'unidad gamma enlaza nodo verde',
    ]:
        report=bot.respond(text)
    assert report['status']=='raw_relation_learned'
    return bot


class V46SafeSpeechActCompositionTests(unittest.TestCase):
    def test_yes_no_question_reuses_assertion_semantics_without_storing(self):
        bot=raw_relation_bot(); before=bot.kb.stats()['facts']
        out=bot.respond('¿equipo alfa enlaza modulo rojo?')
        self.assertEqual(out['status'],'supported')
        self.assertEqual(bot.kb.stats()['facts'],before)

    def test_in_situ_wh_question_preserves_learned_role_order(self):
        bot=raw_relation_bot(); before=bot.kb.stats()['facts']
        out=bot.respond('¿equipo alfa enlaza que?')
        self.assertEqual(out['status'],'bindings')
        self.assertTrue(any(p['atom']['args']==['equipo alfa','modulo rojo'] for p in out['proofs']))
        self.assertEqual(bot.kb.stats()['facts'],before)
        self.assertEqual(bot.kb.known_entities({'que'}),set())

    def test_fronted_wh_abstains_instead_of_guessing_role_reordering(self):
        bot=raw_relation_bot(); before=bot.kb.stats()['facts']
        out=bot.respond('¿que enlaza equipo alfa?')
        self.assertEqual(out['status'],'grounding_pending')
        self.assertEqual(bot.kb.stats()['facts'],before)
        self.assertEqual(bot.kb.known_entities({'que'}),set())

    def test_unseen_relation_word_is_not_grounded_by_cooccurrence(self):
        bot=raw_relation_bot(); before=bot.kb.stats()['facts']
        out=bot.respond('¿equipo alfa separa modulo rojo?')
        self.assertEqual(out['status'],'unrecognized')
        self.assertEqual(bot.kb.stats()['facts'],before)


if __name__=='__main__':
    unittest.main()

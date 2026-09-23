import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


class V47SafeGroundingRetirementTests(unittest.TestCase):
    @staticmethod
    def seeded(bot):
        bot.kb.add(Atom('trabaja',('bruno','acme')),'seed')
        bot.kb.add(Atom('trabaja',('eva','globex')),'seed')
        return bot

    def test_default_does_not_equate_arbitrary_word_with_extensional_match(self):
        bot=self.seeded(Bot(KnowledgeBase()))
        bot.respond('Bruno odia Acme.')
        bot.respond('Eva odia Globex.')
        learned=bot.respond('Luis odia Initech.')
        self.assertEqual(learned['status'],'raw_relation_learned')
        self.assertFalse(bot.kb.contains(Atom('trabaja',('luis','initech'))))
        pred=learned['predicate']
        self.assertTrue(bot.kb.contains(Atom(pred,('luis','initech'))))
        self.assertNotEqual(pred,'trabaja')

    def test_legacy_mode_remains_reproducible_but_is_explicit_opt_in(self):
        bot=self.seeded(Bot(KnowledgeBase(),allow_extensional_grounding=True))
        self.assertEqual(bot.respond('Bruno odia Acme.')['status'],'grounding_pending')
        self.assertEqual(bot.respond('Eva odia Globex.')['status'],'stored')
        self.assertEqual(bot.respond('Luis odia Initech.')['status'],'stored')
        self.assertTrue(bot.kb.contains(Atom('trabaja',('luis','initech'))))

    def test_safe_default_and_legacy_flag_persist(self):
        with tempfile.TemporaryDirectory() as td:
            safe=Bot(); legacy=Bot(allow_extensional_grounding=True)
            a=Path(td)/'safe.json'; b=Path(td)/'legacy.json'
            safe.save(a); legacy.save(b)
            self.assertFalse(Bot.load(a).allow_extensional_grounding)
            self.assertTrue(Bot.load(b).allow_extensional_grounding)


if __name__=='__main__':
    unittest.main()

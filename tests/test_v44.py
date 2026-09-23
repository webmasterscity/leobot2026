import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


def bootstrapped_bot():
    bot=Bot(KnowledgeBase(),allow_extensional_grounding=True)
    for i in range(5):
        bot.kb.add(Atom('socio',(f'persona{i}',f'objeto{i}')))
    for text in [
        'persona0 conecta objeto0','persona1 conecta objeto1',
        'persona0 no conecta objeto1','persona1 no conecta objeto0',
    ]:
        bot.observe_schema_statement(text)
    for i in range(2):
        bot.acquire_schema_assertion(f'agente externo {i} conecta modulo experimental {i}')
        bot.respond(f'agente externo {i} se asocia con modulo experimental {i}')
    return bot


class V44BoundaryAmbiguityTests(unittest.TestCase):
    def test_bootstrapped_construction_reports_repeated_anchor_ambiguity(self):
        bot=bootstrapped_bot()
        text='persona alfa se asocia con modulo se asocia con extra'
        parsed=bot.language.parse(text)
        self.assertEqual(parsed['status'],'ambiguous')
        self.assertGreaterEqual(len(parsed['alternatives']),2)
        before=bot.kb.stats()['facts']
        response=bot.respond(text)
        self.assertEqual(response['status'],'ambiguous')
        self.assertEqual(bot.kb.stats()['facts'],before)

    def test_unique_multiword_slots_still_parse_and_store(self):
        bot=bootstrapped_bot()
        text='persona alfa extendida se asocia con modulo azul profundo'
        parsed=bot.language.parse(text)
        self.assertEqual(parsed['status'],'parsed')
        self.assertEqual(parsed['frame']['args'],['persona alfa extendida','modulo azul profundo'])
        response=bot.respond(text)
        self.assertEqual(response['status'],'stored')
        self.assertEqual(bot.query_schema('persona alfa extendida conecta modulo azul profundo')['status'],'entailed')

    def test_ambiguity_detection_persists(self):
        bot=bootstrapped_bot()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bot.json';bot.save(path);loaded=Bot.load(path)
            parsed=loaded.language.parse('x se asocia con y se asocia con z')
            self.assertEqual(parsed['status'],'ambiguous')


if __name__=='__main__':
    unittest.main()

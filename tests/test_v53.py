import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom, KnowledgeBase


class V53ExplicitParaphraseTests(unittest.TestCase):
    def _raw_ternary(self, bot):
        for text in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            report=bot.respond(text)
        self.assertEqual(report['status'],'raw_relation_learned')
        return report['predicate']

    def test_explicit_paraphrase_learns_role_reordering_without_extensional_grounding(self):
        bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
        pred=self._raw_ternary(bot)
        before=len(bot.raw_relation_observations)
        taught=bot.respond('"a luis ana da caja" significa lo mismo que "ana entrega caja a luis".')
        self.assertEqual(taught['status'],'paraphrase_learned')
        self.assertEqual(len(bot.raw_relation_observations),before)
        parsed=bot.language.parse('a oscar dina da llave')
        self.assertEqual(parsed['status'],'parsed')
        self.assertEqual(parsed['frame']['pred'],pred)
        self.assertEqual(parsed['frame']['args'],['dina','llave','oscar'])
        self.assertEqual(bot.respond('a oscar dina da llave')['status'],'stored')
        self.assertEqual(bot.answer_atom(Atom(pred,('dina','llave','oscar')))['status'],'supported')

    def test_two_unknown_surfaces_do_not_create_semantics(self):
        bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
        before=len(bot.language.constructions)
        report=bot.respond('"alfa zumba beta" significa lo mismo que "gamma frena delta".')
        self.assertEqual(report['status'],'paraphrase_unresolved')
        self.assertEqual(len(bot.language.constructions),before)
        self.assertEqual(bot.raw_relation_observations,[])

    def test_conflicting_known_surfaces_are_not_merged(self):
        bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
        for text in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            first=bot.respond(text)
        for text in ['ana guarda caja en luis','bea guarda libro en mario','cora guarda mapa en nora']:
            second=bot.respond(text)
        self.assertNotEqual(first['predicate'],second['predicate'])
        count=len(bot.language.constructions)
        report=bot.respond('"ana entrega caja a luis" significa lo mismo que "ana guarda caja en luis".')
        self.assertEqual(report['status'],'paraphrase_conflict')
        self.assertEqual(len(bot.language.constructions),count)

    def test_explicit_paraphrase_persists(self):
        bot=Bot(KnowledgeBase(),allow_extensional_grounding=False)
        pred=self._raw_ternary(bot)
        bot.respond('«a luis ana da caja» es otra forma de decir «ana entrega caja a luis».')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            self.assertEqual(loaded.respond('a oscar dina da llave')['status'],'stored')
            self.assertEqual(loaded.answer_atom(Atom(pred,('dina','llave','oscar')))['status'],'supported')


if __name__=='__main__': unittest.main()

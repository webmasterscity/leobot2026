import tempfile
import unittest
from pathlib import Path

from leobot import Bot


class V54ExplicitQuestionConstructionTests(unittest.TestCase):
    def _seed(self,bot):
        for text in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            report=bot.respond(text)
        self.assertEqual(report['status'],'raw_relation_learned')
        return report['predicate']

    def test_explicit_equivalence_teaches_fronted_wh_from_grounded_in_situ_question(self):
        bot=Bot(allow_extensional_grounding=False); self._seed(bot)
        baseline=bot.respond('¿ana entrega qué a luis?')
        self.assertEqual(baseline['status'],'bindings')
        self.assertTrue(any(p['atom']['args']==['ana','caja','luis'] for p in baseline['proofs']))
        self.assertEqual(bot.respond('¿qué entrega ana a luis?')['status'],'grounding_pending')
        taught=bot.respond('"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".')
        self.assertEqual(taught['status'],'paraphrase_learned')
        answer=bot.respond('¿qué entrega bea a mario?')
        self.assertEqual(answer['status'],'bindings')
        self.assertTrue(any(p['atom']['args']==['bea','libro','mario'] for p in answer['proofs']))

    def test_fronted_question_learning_does_not_add_facts(self):
        bot=Bot(allow_extensional_grounding=False); self._seed(bot)
        facts=bot.kb.stats()['facts']
        bot.respond('"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".')
        for _ in range(3): bot.respond('¿qué entrega bea a mario?')
        self.assertEqual(bot.kb.stats()['facts'],facts)

    def test_fronted_query_construction_persists(self):
        bot=Bot(allow_extensional_grounding=False); self._seed(bot)
        bot.respond('«¿qué entrega ana a luis?» es otra forma de decir «¿ana entrega qué a luis?».')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; bot.save(path); loaded=Bot.load(path)
            answer=loaded.respond('¿qué entrega bea a mario?')
            self.assertEqual(answer['status'],'bindings')
            self.assertTrue(any(p['atom']['args']==['bea','libro','mario'] for p in answer['proofs']))

if __name__=='__main__': unittest.main()

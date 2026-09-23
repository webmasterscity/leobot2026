import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V57ConjunctiveConditionalTests(unittest.TestCase):
    DELIVERY = ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']
    RESIDENCE = ['luis reside en paris','mario reside en roma','nora reside en lima']
    DESTINATION = ['caja termina en paris','libro termina en roma','mapa termina en lima']
    CONDITIONS = [
        'si dora entrega carta a raul y raul reside en madrid entonces carta termina en madrid',
        'si eva entrega paquete a sara y sara reside en berlin entonces paquete termina en berlin',
        'si fede entrega llave a tomas y tomas reside en quito entonces llave termina en quito',
    ]

    def _ground(self, bot):
        reports=[]
        for group in (self.DELIVERY,self.RESIDENCE,self.DESTINATION):
            for text in group:
                last=bot.respond(text)
            self.assertEqual(last['status'],'raw_relation_learned')
            reports.append(last)
        return [r['predicate'] for r in reports]

    def _learn(self, bot):
        preds=self._ground(bot)
        before=bot.kb.stats()['facts']
        r1=bot.respond(self.CONDITIONS[0]); r2=bot.respond(self.CONDITIONS[1]); r3=bot.respond(self.CONDITIONS[2])
        self.assertEqual([r1['status'],r2['status'],r3['status']],
                         ['conditional_rule_pending','conditional_rule_pending','conditional_rule_learned'])
        self.assertEqual(r3['antecedents'],2)
        self.assertEqual(r3['body_classes'],[0,1,2,2,3])
        self.assertEqual(r3['head_classes'],[1,3])
        self.assertEqual(bot.kb.stats()['facts'],before)
        return preds,r3

    def test_conjunction_learns_shared_variable_rule_and_derives_new_case(self):
        bot=Bot(allow_extensional_grounding=False)
        preds,learned=self._learn(bot)
        rule=bot.kb.rules[learned['rule_id']]
        self.assertEqual([a.pred for a in rule.body],preds[:2])
        self.assertEqual(rule.head.pred,preds[2])
        bot.respond('gina entrega cuaderno a hugo')
        bot.respond('hugo reside en oslo')
        self.assertEqual(bot.respond('¿cuaderno termina en oslo?')['status'],'hypothesis')

    def test_missing_join_prevents_derivation(self):
        bot=Bot(allow_extensional_grounding=False); self._learn(bot)
        bot.respond('gina entrega cuaderno a hugo')
        bot.respond('jorge reside en oslo')
        self.assertEqual(bot.respond('¿cuaderno termina en oslo?')['status'],'unknown')

    def test_two_conjunctive_examples_do_not_promote(self):
        bot=Bot(allow_extensional_grounding=False); self._ground(bot)
        self.assertEqual(bot.respond(self.CONDITIONS[0])['status'],'conditional_rule_pending')
        self.assertEqual(bot.respond(self.CONDITIONS[1])['status'],'conditional_rule_pending')
        bot.respond('gina entrega cuaderno a hugo'); bot.respond('hugo reside en oslo')
        self.assertEqual(bot.respond('¿cuaderno termina en oslo?')['status'],'unknown')

    def test_changed_variable_topology_blocks_promotion(self):
        bot=Bot(allow_extensional_grounding=False); self._ground(bot)
        bot.respond(self.CONDITIONS[0]); bot.respond(self.CONDITIONS[1])
        # The receiver of entrega is no longer the subject of reside.
        conflict=bot.respond('si fede entrega llave a tomas y ulises reside en quito entonces llave termina en quito')
        self.assertEqual(conflict['status'],'conditional_rule_ambiguous')
        self.assertFalse(any(r.id.startswith('conditional_') for r in bot.kb.rules.values()))

    def test_conjunctive_rule_persists_in_memory_bot(self):
        bot=Bot(allow_extensional_grounding=False); _,learned=self._learn(bot)
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json'; bot.save(state); loaded=Bot.load(state)
            self.assertIn(learned['rule_id'],loaded.kb.rules)
            loaded.respond('gina entrega cuaderno a hugo'); loaded.respond('hugo reside en oslo')
            self.assertEqual(loaded.respond('¿cuaderno termina en oslo?')['status'],'hypothesis')

    def test_conjunctive_rule_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False); _,learned=self._learn(bot)
            bot.save(side); bot.close(); loaded=ScalableBot.load(side,db)
            try:
                self.assertIn(learned['rule_id'],loaded.kb.rules)
                loaded.respond('gina entrega cuaderno a hugo'); loaded.respond('hugo reside en oslo')
                self.assertEqual(loaded.respond('¿cuaderno termina en oslo?')['status'],'hypothesis')
            finally:
                loaded.close()


if __name__=='__main__': unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V517GroundedQueryEllipsisTests(unittest.TestCase):
    def _seed_delivery(self, bot):
        last=None
        for text in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            last=bot.respond(text)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def _teach_object_and_recipient_questions(self, bot):
        a=bot.respond('"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".')
        self.assertEqual(a['status'],'paraphrase_learned')
        b=bot.respond('"¿a quién entrega ana caja?" significa lo mismo que "¿ana entrega caja a quién?".')
        self.assertEqual(b['status'],'paraphrase_learned')

    def test_short_wh_questions_reuse_grounded_answer_roles(self):
        bot=Bot(allow_extensional_grounding=False)
        self._seed_delivery(bot); self._teach_object_and_recipient_questions(bot)
        bot.respond('dora entrega carta a raul')
        obj=bot.respond('¿Qué?')
        self.assertEqual(obj['status'],'bindings')
        self.assertTrue(obj['contextual_ellipsis'])
        self.assertEqual(obj['answer_pos'],1)
        self.assertTrue(any(p['atom']['args']==['dora','carta','raul'] for p in obj['proofs']))
        recipient=bot.respond('¿Y a quién?')
        self.assertEqual(recipient['status'],'bindings')
        self.assertTrue(recipient['contextual_ellipsis'])
        self.assertEqual(recipient['answer_pos'],2)
        self.assertTrue(any(p['atom']['args']==['dora','carta','raul'] for p in recipient['proofs']))

    def test_contextual_query_does_not_mutate_facts(self):
        bot=Bot(allow_extensional_grounding=False)
        self._seed_delivery(bot); self._teach_object_and_recipient_questions(bot)
        bot.respond('dora entrega carta a raul')
        before=bot.kb.stats()['facts']
        for text in ['¿qué?','¿a quién?','¿y qué?']:
            self.assertEqual(bot.respond(text)['status'],'bindings')
        self.assertEqual(bot.kb.stats()['facts'],before)

    def test_new_topic_without_compatible_query_grammar_does_not_fall_back_to_older_fact(self):
        bot=Bot(allow_extensional_grounding=False)
        self._seed_delivery(bot); self._teach_object_and_recipient_questions(bot)
        bot.respond('dora entrega carta a raul')
        for text in ['proyecto alfa ocurre lunes','proyecto beta ocurre martes','proyecto gamma ocurre miercoles']:
            learned=bot.respond(text)
        self.assertEqual(learned['status'],'raw_relation_learned')
        bot.respond('proyecto delta ocurre jueves')
        report=bot.respond('¿qué?')
        self.assertEqual(report['status'],'unrecognized')

    def test_same_cue_for_two_answer_positions_is_ambiguous(self):
        bot=Bot(allow_extensional_grounding=False)
        self._seed_delivery(bot)
        first=bot.respond('"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".')
        self.assertEqual(first['status'],'paraphrase_learned')
        second=bot.respond('"¿qué destino tiene ana con caja?" significa lo mismo que "¿ana entrega caja a qué?".')
        self.assertEqual(second['status'],'paraphrase_learned')
        bot.respond('dora entrega carta a raul')
        before=bot.kb.stats()['facts']
        report=bot.respond('¿qué?')
        self.assertEqual(report['status'],'contextual_query_ambiguous')
        self.assertEqual(report['reason'],'multiple_answer_roles')
        self.assertEqual(bot.kb.stats()['facts'],before)

    def test_contextual_query_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            self._seed_delivery(bot); self._teach_object_and_recipient_questions(bot)
            bot.respond('dora entrega carta a raul')
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                report=loaded.respond('¿a quién?')
                self.assertEqual(report['status'],'bindings')
                self.assertTrue(report['contextual_ellipsis'])
                self.assertEqual(report['answer_pos'],2)
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot
from experiments.v59_architecture_freeze import teach_role_set


class V63UnifiedTests(unittest.TestCase):
    """V6.3 = V5.28 language/document line + V6.2 meta line in one engine."""

    def test_scalable_bot_persists_meta_representations(self):
        with tempfile.TemporaryDirectory() as td:
            bot=ScalableBot(Path(td)/'kb.sqlite')
            teach_role_set(bot,0,(0,2))
            rows=bot.meta_representations.rows()
            self.assertTrue(rows)
            bot.save(Path(td)/'state.json'); bot.close()
            loaded=ScalableBot.load(Path(td)/'state.json')
            self.assertEqual(loaded.meta_representations.rows(),rows)
            self.assertTrue(loaded.procedures.external_role_cardinalities or loaded.symbolic.external_role_cardinalities)
            loaded.close()

    def test_both_lines_coexist_in_one_bot(self):
        bot=Bot()
        teach_role_set(bot,0,(0,2))
        self.assertTrue(bot.meta_representations.rows())
        for text in ['alfa florece','beta florece','gamma florece']:
            report=bot.respond(text)
        self.assertEqual(report['status'],'raw_relation_learned')
        doc=bot.respond('delta florece. epsilon florece.')
        self.assertNotEqual(doc.get('status'),'unrecognized')
        with tempfile.TemporaryDirectory() as td:
            bot.save(Path(td)/'b.json'); loaded=Bot.load(Path(td)/'b.json')
        self.assertEqual(loaded.meta_representations.rows(),bot.meta_representations.rows())
        self.assertEqual(loaded.raw_relation_promotions.keys(),bot.raw_relation_promotions.keys())


    def test_splitter_keeps_quoted_terminators_inside_one_utterance(self):
        quoted='"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".'
        self.assertEqual(Bot._split_document(quoted),[quoted])
        self.assertEqual(Bot._split_document('alfa florece. ¿beta florece?'),['alfa florece.','¿beta florece?'])
        self.assertEqual(Bot._split_document('¿Y a quién?'),['¿Y a quién?'])

    def test_discourse_referents_persist_in_bot_and_scalable_bot(self):
        from experiments.v58_document_freeze_experiment import bootstrap
        bot=bootstrap()
        bot.respond('persona p9 enlaza modulo o9')
        self.assertTrue(bot.discourse_referents)
        with tempfile.TemporaryDirectory() as td:
            bot.save(Path(td)/'b.json'); loaded=Bot.load(Path(td)/'b.json')
        self.assertEqual(loaded.discourse_referents,bot.discourse_referents)
        report=loaded.respond('este reposa zona z9')
        self.assertEqual(report['discourse_resolution']['resolved'],'modulo o9 reposa zona z9')
        with tempfile.TemporaryDirectory() as td:
            sb=ScalableBot(Path(td)/'s.sqlite'); sb.discourse_referents=list(bot.discourse_referents)
            sb.save(Path(td)/'state.json'); sb.close()
            again=ScalableBot.load(Path(td)/'state.json')
            self.assertEqual(again.discourse_referents,bot.discourse_referents)
            again.close()


    def test_demonstrative_lookalike_cannot_import_a_predicate(self):
        bot=Bot()
        for text in ['equipo alfa enlaza modulo rojo','grupo beta enlaza pieza azul',
                     'unidad gamma enlaza nodo verde']:
            bot.respond(text)
        report=bot.respond('componente oro reposa area este')
        self.assertNotIn('discourse_resolution',report)
        stored=[a for f in bot.kb.facts.values() for a in f['atom'].args]
        self.assertEqual(len(stored),6)
        self.assertFalse(any('reposa' in a for a in stored))


if __name__=='__main__':
    unittest.main()

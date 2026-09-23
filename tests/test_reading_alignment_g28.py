"""G-28: read sentences are remembered and answered literally after worked examples."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot


EXAMPLES=[
    ('Dorotea vive en Quimper. Tiene dos gatos.','¿Dónde vive Dorotea?','Quimper'),
    ('El tren llegó tarde. Bruno trabaja en Lagos desde hace años.','¿Dónde trabaja Bruno?','Lagos'),
    ('Marta estudia en Oruro con su hermana.','¿Dónde estudia Marta?','Oruro'),
    ('Hace frío. Pablo pinta en Tacna cada verano.','¿Dónde pinta Pablo?','Tacna'),
    ('Rosa canta en Pisco los domingos.','¿Quién canta en Pisco?','Rosa'),
    ('Tomás corre en Ica por la mañana.','¿Quién corre en Ica?','Tomás'),
    ('Ana cocina en Puno para su familia.','¿Quién cocina en Puno?','Ana'),
]


def educated():
    bot=Bot()
    for context,question,answer in EXAMPLES:
        bot.observe_reading_example(context,question,answer)
    return bot


class ReadingAlignmentTests(unittest.TestCase):
    def test_fresh_bot_does_not_answer_from_reading(self):
        bot=Bot()
        bot.ingest_document_text('Julia nada en Arica.',source='doc')
        self.assertNotEqual(bot.respond('¿Dónde nada Julia?').get('status'),'literal')

    def test_educated_bot_answers_new_text_with_source(self):
        bot=educated()
        bot.ingest_document_text('Llovió toda la tarde. Julia nada en Arica con su primo.',source='doc')
        reply=bot.respond('¿Dónde nada Julia?')
        self.assertEqual(reply['status'],'literal')
        self.assertEqual(reply['text'],'Arica')
        self.assertTrue(reply['evidence']['source'].startswith('doc:oración:'))
        who=bot.respond('¿Quién nada en Arica?')
        self.assertEqual((who['status'],who['text']),('literal','Julia'))

    def test_unrelated_text_abstains_and_memory_survives_restart(self):
        bot=educated()
        bot.ingest_document_text('Julia nada en Arica.',source='doc')
        self.assertNotEqual(bot.respond('¿Dónde duerme Ernesto?').get('status'),'literal')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bot.json'
            bot.save(path); bot=Bot.load(path)
        self.assertEqual(bot.respond('¿Dónde nada Julia?')['text'],'Arica')
        self.assertEqual(bot.forget_utterances('doc'),1)
        self.assertNotEqual(bot.respond('¿Dónde nada Julia?').get('status'),'literal')


if __name__=='__main__':
    unittest.main()

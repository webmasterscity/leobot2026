"""Acquire a new question form from grounded facts without semantic labels."""

import unittest
import tempfile
from pathlib import Path

from leobot import Bot


class SafeQuestionGroundingTests(unittest.TestCase):
    def test_questions_with_relation_anchor_learn_without_unsafe_statement_grounding(self):
        bot = Bot()
        for sentence in (
            'La evidencia manda sobre la ambición.',
            'La prudencia manda sobre la prisa.',
            'La paciencia manda sobre el impulso.',
        ):
            bot.ingest_document_text(sentence, source='lectura')
        self.assertEqual(len(bot.raw_relation_promotions), 1)
        self.assertFalse(bot.allow_extensional_grounding)
        before = bot.kb.stats()['facts']

        wrong_relation = bot.respond('¿Qué castiga sobre la ambición?')
        self.assertEqual(wrong_relation['status'], 'unrecognized')
        self.assertEqual(bot.kb.stats()['facts'], before)

        first = bot.respond('¿Qué manda sobre la ambición?')
        self.assertEqual(first['status'], 'grounding_pending')
        repeated = bot.respond('¿Qué manda sobre la ambición?')
        self.assertEqual(repeated['status'], 'grounding_pending')
        second = bot.respond('¿Qué manda sobre la prisa?')
        self.assertEqual(second['status'], 'bindings')
        heldout = bot.respond('¿Qué manda sobre el impulso?')
        self.assertEqual(heldout['status'], 'bindings')
        self.assertTrue(any(proof['atom']['args'] == ['paciencia', 'el impulso']
                            for proof in heldout['proofs']))
        self.assertEqual(bot.kb.stats()['facts'], before)
        self.assertEqual(bot.respond('La paciencia no manda sobre el impulso.')['status'],
                         'stored')
        self.assertEqual(bot.respond('¿Qué manda sobre el impulso?')['status'],
                         'contested')

    def test_three_role_question_form_survives_restart_and_negative_facts_stay_separate(self):
        bot = Bot()
        for sentence in (
            'Ana entrega caja a Luis.',
            'Bea entrega libro a Mario.',
            'Cora entrega mapa a Nora.',
        ):
            bot.ingest_document_text(sentence, source='lectura')
        self.assertEqual(bot.respond('¿Qué entrega Ana a Luis?')['status'], 'grounding_pending')
        self.assertEqual(bot.respond('¿Qué entrega Bea a Mario?')['status'], 'bindings')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bot.json'
            bot.save(path)
            loaded = Bot.load(path)
            answer = loaded.respond('¿Qué entrega Cora a Nora?')
            self.assertEqual(answer['status'], 'bindings')
            self.assertTrue(any(proof['atom']['args'] == ['cora', 'mapa', 'nora']
                                for proof in answer['proofs']))

        negative = Bot()
        for sentence in (
            'Ana no entrega caja a Luis.',
            'Bea no entrega libro a Mario.',
            'Cora no entrega mapa a Nora.',
        ):
            negative.ingest_document_text(sentence, source='lectura')
        self.assertEqual(negative.respond('¿Qué entrega Ana a Luis?')['status'],
                         'unrecognized')

    def test_same_words_with_reversed_roles_cannot_ground_a_question(self):
        bot = Bot()
        for sentence in (
            'Ana entrega caja a Luis.',
            'Bea entrega libro a Mario.',
            'Cora entrega mapa a Nora.',
        ):
            bot.ingest_document_text(sentence, source='lectura')
        for question in (
            '¿Qué entrega Luis a Ana?',
            '¿Qué entrega Mario a Bea?',
            '¿Qué entrega Nora a Cora?',
        ):
            self.assertEqual(bot.respond(question)['status'], 'unrecognized')


if __name__ == '__main__':
    unittest.main()

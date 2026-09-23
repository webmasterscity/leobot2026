import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V55QuestionMetaTransferTests(unittest.TestCase):
    def _seed_ternary(self, bot, rows):
        last = None
        for text in rows:
            last = bot.respond(text)
        self.assertIsNotNone(last)
        self.assertEqual(last['status'], 'raw_relation_learned')
        return last['predicate'], last

    def _teach_fronted(self, bot, fronted, insitu):
        report = bot.respond(f'"{fronted}" significa lo mismo que "{insitu}".')
        self.assertEqual(report['status'], 'paraphrase_learned')
        self.assertIsNotNone(report.get('question_transform'))
        return report

    def _two_supports(self, bot):
        p1, _ = self._seed_ternary(bot, [
            'ana entrega caja a luis',
            'bea entrega libro a mario',
            'cora entrega mapa a nora',
        ])
        first = self._teach_fronted(
            bot, '¿qué entrega ana a luis?', '¿ana entrega qué a luis?'
        )
        self.assertFalse(first['question_transform']['promoted'])
        self.assertEqual(first['question_transform']['support'], 1)

        p2, _ = self._seed_ternary(bot, [
            'dora envia carta hacia raul',
            'eva envia paquete hacia sara',
            'fede envia llave hacia tomas',
        ])
        second = self._teach_fronted(
            bot, '¿qué envia dora hacia raul?', '¿dora envia qué hacia raul?'
        )
        self.assertTrue(second['question_transform']['promoted'])
        self.assertEqual(second['question_transform']['support'], 2)
        self.assertNotEqual(p1, p2)
        return p1, p2, second['question_transform']['transform']

    def test_two_distinct_predicates_promote_and_third_inherits_without_question_example(self):
        bot = Bot(allow_extensional_grounding=False)
        self._two_supports(bot)

        p3, learned = self._seed_ternary(bot, [
            'gina transporta libro hasta hugo',
            'ines transporta mapa hasta jorge',
            'kira transporta llave hasta leo',
        ])
        self.assertEqual(learned.get('question_constructions'), 1)

        answer = bot.respond('¿qué transporta gina hasta hugo?')
        self.assertEqual(answer['status'], 'bindings')
        self.assertTrue(any(p['atom']['pred'] == p3 and p['atom']['args'] == ['gina', 'libro', 'hugo']
                            for p in answer['proofs']))
        # No predicate-specific fronted question was explicitly taught for p3.
        explicit = [r for r in bot.training_reports
                    if r.get('type') == 'explicit_paraphrase' and r.get('frame', {}).get('pred') == p3]
        self.assertEqual(explicit, [])

    def test_one_support_is_not_enough_to_transfer(self):
        bot = Bot(allow_extensional_grounding=False)
        self._seed_ternary(bot, [
            'ana entrega caja a luis', 'bea entrega libro a mario', 'cora entrega mapa a nora'
        ])
        first = self._teach_fronted(bot, '¿qué entrega ana a luis?', '¿ana entrega qué a luis?')
        self.assertFalse(first['question_transform']['promoted'])

        _, learned = self._seed_ternary(bot, [
            'gina transporta libro hasta hugo',
            'ines transporta mapa hasta jorge',
            'kira transporta llave hasta leo',
        ])
        self.assertEqual(learned.get('question_constructions'), 0)
        self.assertEqual(bot.respond('¿qué transporta gina hasta hugo?')['status'], 'grounding_pending')

    def test_different_assertion_topology_does_not_inherit_transform(self):
        bot = Bot(allow_extensional_grounding=False)
        self._two_supports(bot)
        # Binary assertion topology {A0} <F0> {A1} does not match the learned
        # ternary {A0} <F0> {A1} <F1> {A2} topology.
        last = None
        for text in ['alfa enlaza beta', 'gamma enlaza delta', 'epsilon enlaza zeta']:
            last = bot.respond(text)
        self.assertEqual(last['status'], 'raw_relation_learned')
        self.assertEqual(last.get('arity'), 2)
        self.assertEqual(last.get('question_constructions'), 0)
        self.assertEqual(bot.respond('¿qué enlaza alfa?')['status'], 'grounding_pending')

    def test_meta_transform_persists_and_applies_to_relation_learned_after_reload(self):
        bot = Bot(allow_extensional_grounding=False)
        self._two_supports(bot)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            bot.save(path)
            loaded = Bot.load(path)
            promoted = [x for x in loaded.question_transform_hypotheses.values() if x.get('promoted')]
            self.assertEqual(len(promoted), 1)
            p3, learned = self._seed_ternary(loaded, [
                'gina transporta libro hasta hugo',
                'ines transporta mapa hasta jorge',
                'kira transporta llave hasta leo',
            ])
            self.assertEqual(learned.get('question_constructions'), 1)
            answer = loaded.respond('¿qué transporta ines hasta jorge?')
            self.assertEqual(answer['status'], 'bindings')
            self.assertTrue(any(p['atom']['pred'] == p3 and p['atom']['args'] == ['ines', 'mapa', 'jorge']
                                for p in answer['proofs']))

    def test_meta_generated_questions_do_not_mutate_facts_and_wrong_anchor_is_rejected(self):
        bot = Bot(allow_extensional_grounding=False)
        self._two_supports(bot)
        self._seed_ternary(bot, [
            'gina transporta libro hasta hugo',
            'ines transporta mapa hasta jorge',
            'kira transporta llave hasta leo',
        ])
        before = bot.kb.stats()['facts']
        for _ in range(3):
            self.assertEqual(bot.respond('¿qué transporta gina hasta hugo?')['status'], 'bindings')
        self.assertEqual(bot.kb.stats()['facts'], before)
        self.assertEqual(bot.respond('¿qué transporta gina hacia hugo?')['status'], 'unrecognized')

    def test_scalable_meta_transform_persists_and_applies_after_reload(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            side = Path(td) / 'state.json'
            bot = ScalableBot(db, allow_extensional_grounding=False)
            self._two_supports(bot)
            bot.save(side)
            bot.close()
            loaded = ScalableBot.load(side, db)
            try:
                promoted = [x for x in loaded.question_transform_hypotheses.values() if x.get('promoted')]
                self.assertEqual(len(promoted), 1)
                p3, learned = self._seed_ternary(loaded, [
                    'gina transporta libro hasta hugo',
                    'ines transporta mapa hasta jorge',
                    'kira transporta llave hasta leo',
                ])
                self.assertEqual(learned.get('question_constructions'), 1)
                answer = loaded.respond('¿qué transporta kira hasta leo?')
                self.assertEqual(answer['status'], 'bindings')
                self.assertTrue(any(p['atom']['pred'] == p3 and p['atom']['args'] == ['kira', 'llave', 'leo']
                                    for p in answer['proofs']))
            finally:
                loaded.close()


if __name__ == '__main__':
    unittest.main()

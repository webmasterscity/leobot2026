"""Persistence contract for the SQLite-backed cognitive sidecar."""

import json
import tempfile
import unittest
from pathlib import Path

from leobot import ScalableBot
from leobot.core import Atom, Rule
from leobot.diskkb import SQLiteKnowledgeBase


class ScalableStateTests(unittest.TestCase):
    def test_roundtrip_keeps_cognitive_state_without_copying_sqlite_facts(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            sidecar = Path(td) / 'state.json'
            bot = ScalableBot(db)
            try:
                bot.raw_relation_max_arity = 3
                for i in range(128):
                    bot.kb.add(Atom('dato', (f'entidad{i}',)))
                focus = bot.kb.add(Atom('dato', ('actual',)), source='conversación')
                bot.kb.add_rule(Rule('r1', Atom('derivado', ('?x',)),
                                     (Atom('dato', ('?x',)),)))
                bot.kb.add_example('par', ('ana', 'bea'), True)
                bot.last_fact = focus
                bot.discourse_facts = ['f99999', focus]
                bot.discourse_max_referents = 4
                bot.discourse_referents = [{'surface': str(i)} for i in range(6)]
                bot.last_symbolic_state = [('en', 'robot', 'sala')]
                bot.symbolic_entities = {'robot', 'sala'}
                bot.meta_controller.observe('scheduler', (1, 2), 'strategy_a', success=True)
                references = {
                    'document_event_reference_hypotheses': {'event': {'support': 2}},
                    'document_causal_reference_hypotheses': {'causal': {'support': 3}},
                    'document_dependency_reference_hypotheses': {'dependency': {'support': 4}},
                    'document_state_reference_hypotheses': {'state': {'support': 5}},
                    'document_state_meta_reference_hypotheses': {'state_meta': {'support': 6}},
                }
                for name, value in references.items():
                    setattr(bot, name, value)
                bot.save(sidecar)
            finally:
                bot.close()

            payload = json.loads(sidecar.read_text(encoding='utf8'))
            self.assertNotIn('kb', payload)
            self.assertNotIn('facts', payload)
            self.assertLess(sidecar.stat().st_size, db.stat().st_size)
            restored = ScalableBot.load(sidecar)
            try:
                self.assertIsInstance(restored.kb, SQLiteKnowledgeBase)
                self.assertEqual(restored.kb.count_facts(), 129)
                self.assertIn('r1', restored.kb.rules)
                self.assertEqual(restored.kb.examples['par'][('ana', 'bea')], {True})
                self.assertEqual(restored.kb.audit[0]['event'], 'example')
                self.assertEqual(restored.raw_relation_max_arity, 3)
                self.assertEqual(restored.meta_controller.observations, 1)
                self.assertIs(restored.procedures.meta_controller, restored.meta_controller)
                self.assertIs(restored.symbolic.meta_controller, restored.meta_controller)
                self.assertEqual(restored.last_fact, focus)
                self.assertEqual(restored.discourse_facts, [focus])
                self.assertEqual(restored.discourse_referents,
                                 [{'surface': str(i)} for i in range(2, 6)])
                self.assertEqual(restored.last_symbolic_state, [('en', 'robot', 'sala')])
                self.assertEqual(restored.symbolic_entities, {'robot', 'sala'})
                for name, value in references.items():
                    self.assertEqual(getattr(restored, name), value)
            finally:
                restored.close()

    def test_version_one_sidecar_without_later_fields_uses_original_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'facts.db'
            sidecar = Path(td) / 'old.json'
            bot = ScalableBot(db)
            try:
                fact_id = bot.kb.add(Atom('dato', ('antiguo',)))
                bot.save(sidecar)
            finally:
                bot.close()

            old = json.loads(sidecar.read_text(encoding='utf8'))
            for key in (
                'raw_relation_max_arity', 'raw_relation_min_support',
                'allow_extensional_grounding', 'meta_controller',
                'meta_representations', 'schemas', 'discourse_facts',
                'discourse_referents', 'discourse_max_referents',
                'document_event_reference_hypotheses',
                'document_state_meta_reference_hypotheses',
                'last_symbolic_state', 'symbolic_entities',
            ):
                old.pop(key)
            old['last_fact'] = fact_id
            sidecar.write_text(json.dumps(old), encoding='utf8')

            restored = ScalableBot.load(sidecar, db)
            try:
                self.assertEqual(restored.raw_relation_max_arity, 8)
                self.assertEqual(restored.raw_relation_min_support, 3)
                self.assertFalse(restored.allow_extensional_grounding)
                self.assertEqual(restored.discourse_max_referents, 32)
                self.assertEqual(restored.discourse_facts, [fact_id])
                self.assertEqual(restored.document_event_reference_hypotheses, {})
                self.assertEqual(restored.document_state_meta_reference_hypotheses, {})
                self.assertEqual(restored.meta_controller.observations, 0)
                self.assertIs(restored.procedures.meta_controller, restored.meta_controller)
                self.assertIsNotNone(restored.kb.get_fact(fact_id))
            finally:
                restored.close()


if __name__ == '__main__':
    unittest.main()

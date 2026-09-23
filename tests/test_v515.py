import tempfile
import unittest
import json
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot
from leobot.core import Atom


class V515ContextualCorrectionTests(unittest.TestCase):
    def _ground_date(self, bot):
        rows=[
            'proyecto alfa ocurre el lunes',
            'proyecto beta ocurre el martes',
            'proyecto gamma ocurre el miercoles',
        ]
        last=None
        for row in rows:
            last=bot.respond(row)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def _ground_mark(self, bot):
        rows=[
            'proyecto alfa marca lunes',
            'proyecto beta marca martes',
            'proyecto gamma marca miercoles',
        ]
        last=None
        for row in rows:
            last=bot.respond(row)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def test_ellipsis_correction_replaces_unique_slot_without_taught_correction_phrase(self):
        bot=Bot(allow_extensional_grounding=False)
        pred=self._ground_date(bot)
        stored=bot.respond('proyecto delta ocurre el jueves')
        old_id=stored['id']
        report=bot.respond('No, era el viernes.')
        self.assertEqual(report['status'],'corrected_contextually')
        self.assertEqual(report['slot'],1)
        self.assertEqual(report['old_value'],'jueves')
        self.assertEqual(report['new_value'],'viernes')
        self.assertIsNone(bot.kb.get_fact(old_id))
        self.assertTrue(bot.kb.contains(Atom(pred,('delta','viernes'))))
        self.assertFalse(bot.kb.contains(Atom(pred,('delta','jueves'))))
        self.assertFalse(any(ex.get('frame',{}).get('act')=='correct_last' for ex in bot.language.examples))

    def test_correction_recomputes_rule_consequences_without_touching_unrelated_fact(self):
        bot=Bot(allow_extensional_grounding=False)
        occurs=self._ground_date(bot); mark=self._ground_mark(bot)
        conds=[
            'si proyecto uno ocurre el lunes entonces proyecto uno marca lunes',
            'si proyecto dos ocurre el martes entonces proyecto dos marca martes',
            'si proyecto tres ocurre el miercoles entonces proyecto tres marca miercoles',
        ]
        reports=[bot.respond(x) for x in conds]
        self.assertEqual(reports[-1]['status'],'conditional_rule_learned')
        unrelated=bot.kb.add(Atom('otro',('x','y')),'control')
        bot.respond('proyecto omega ocurre el jueves')
        self.assertEqual(bot.answer_atom(Atom(mark,('omega','jueves')))['status'],'hypothesis')
        corrected=bot.respond('No, era el viernes.')
        self.assertEqual(corrected['status'],'corrected_contextually')
        self.assertEqual(bot.answer_atom(Atom(mark,('omega','jueves')))['status'],'unknown')
        self.assertEqual(bot.answer_atom(Atom(mark,('omega','viernes')))['status'],'hypothesis')
        self.assertIsNotNone(bot.kb.get_fact(unrelated))
        self.assertTrue(bot.kb.contains(Atom(occurs,('omega','viernes'))))

    def test_repeated_anchor_is_ambiguous_and_does_not_mutate_memory(self):
        bot=Bot(allow_extensional_grounding=False)
        learned=None
        for i in range(4):
            learned=bot.respond(f'a{i} liga b{i} con c{i} con d{i}')
        self.assertEqual(learned['status'],'raw_relation_learned')
        stored=bot.respond('ax liga bx con cx con dx')
        fid=stored['id']; before=bot.kb.get_fact(fid)['atom']
        report=bot.respond('No, con nuevo.')
        self.assertEqual(report['status'],'correction_ambiguous')
        self.assertEqual(bot.last_fact,fid)
        self.assertEqual(bot.kb.get_fact(fid)['atom'],before)

    def test_unknown_correction_with_no_anchor_abstains_instead_of_becoming_negative_training(self):
        bot=Bot(allow_extensional_grounding=False)
        self._ground_date(bot)
        bot.respond('proyecto delta ocurre el jueves')
        before=len(bot.raw_negative_relation_observations)
        report=bot.respond('No, definitivamente viernes.')
        self.assertEqual(report['status'],'correction_unresolved')
        self.assertEqual(len(bot.raw_negative_relation_observations),before)
        self.assertTrue(bot.kb.contains(next(f['atom'] for f in [bot.kb.get_fact(bot.last_fact)])))

    def test_multiword_replacement_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            pred=self._ground_date(bot)
            bot.respond('proyecto delta ocurre el jueves')
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                report=loaded.respond('No, era el viernes santo.')
                self.assertEqual(report['status'],'corrected_contextually')
                self.assertEqual(report['new_value'],'viernes santo')
                self.assertTrue(loaded.kb.contains(Atom(pred,('delta','viernes santo'))))
                loaded.save(side)
            finally:
                loaded.close()
            again=ScalableBot.load(side,db)
            try:
                self.assertTrue(again.kb.contains(Atom(pred,('delta','viernes santo'))))
            finally:
                again.close()

    def test_change_of_topic_means_correction_targets_most_recent_fact(self):
        bot=Bot(allow_extensional_grounding=False)
        date=self._ground_date(bot)
        # Ground a second relation with an anchor suitable for an elliptical repair.
        for row in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            delivery=bot.respond(row)
        delivery_pred=delivery['predicate']
        bot.respond('proyecto delta ocurre el jueves')
        bot.respond('dora entrega carta a raul')
        report=bot.respond('No, a tomas.')
        self.assertEqual(report['status'],'corrected_contextually')
        self.assertTrue(bot.kb.contains(Atom(delivery_pred,('dora','carta','tomas'))))
        self.assertTrue(bot.kb.contains(Atom(date,('delta','jueves'))))

    def test_promoted_raw_evidence_is_not_reused_for_spurious_coarse_relation(self):
        bot=Bot(allow_extensional_grounding=False)
        occurs=self._ground_date(bot)
        first=bot.respond('proyecto alfa marca lunes')
        self.assertNotEqual(first['status'],'raw_relation_learned')
        second=bot.respond('proyecto beta marca martes')
        self.assertNotEqual(second['status'],'raw_relation_learned')
        third=bot.respond('proyecto gamma marca miercoles')
        self.assertEqual(third['status'],'raw_relation_learned')
        mark=third['predicate']
        self.assertNotEqual(mark,occurs)
        surfaces={row.get('surface') for row in bot.raw_relation_promotions.values()}
        self.assertIn('proyecto {s0} ocurre el {s1}',surfaces)
        self.assertIn('proyecto {s0} marca {s1}',surfaces)
        self.assertNotIn('proyecto {s0}',surfaces)
        explained=[o for o in bot.raw_relation_observations
                   if o.get('text','').startswith('proyecto ') and ' ocurre el ' in o.get('text','')]
        self.assertEqual(len(explained),3)
        self.assertTrue(all(o.get('consumed_by')==occurs for o in explained))

    def test_loading_pre_v515_state_reconstructs_consumed_raw_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'legacy.json'
            bot=Bot(allow_extensional_grounding=False)
            pred=self._ground_date(bot)
            bot.save(path)
            data=json.loads(path.read_text(encoding='utf8'))
            for obs in data['raw_relation_observations']:
                obs.pop('consumed_by',None)
            path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
            loaded=Bot.load(path)
            rows=[o for o in loaded.raw_relation_observations if ' ocurre el ' in o.get('text','')]
            self.assertEqual(len(rows),3)
            self.assertTrue(all(o.get('consumed_by')==pred for o in rows))
            self.assertNotEqual(loaded.respond('proyecto alfa marca lunes')['status'],'raw_relation_learned')


if __name__=='__main__':
    unittest.main()

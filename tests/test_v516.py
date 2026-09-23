import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V516MultiRoleDiscourseRevisionTests(unittest.TestCase):
    def _ground_event(self, bot):
        rows=[
            'evento alfa sera lunes en sala norte',
            'evento beta sera martes en sala azul',
            'evento gamma sera miercoles en salon central',
        ]
        last=None
        for row in rows:
            last=bot.respond(row)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def _ground_delivery(self, bot):
        rows=[
            'ana entrega caja a luis',
            'bea entrega libro a mario',
            'cora entrega mapa a nora',
        ]
        last=None
        for row in rows:
            last=bot.respond(row)
        self.assertEqual(last['status'],'raw_relation_learned')
        return last['predicate']

    def test_elliptical_correction_can_change_two_roles_atomically(self):
        bot=Bot(allow_extensional_grounding=False)
        pred=self._ground_event(bot)
        old=bot.respond('evento delta sera jueves en sala roja')['id']
        report=bot.respond('No, sera viernes en sala verde.')
        self.assertEqual(report['status'],'corrected_contextually')
        self.assertEqual(report['changed_slots'],[1,2])
        self.assertEqual(report['mechanism'],'anchored_multi_slot_revision_v516')
        self.assertIsNone(bot.kb.get_fact(old))
        self.assertTrue(bot.kb.contains(Atom(pred,('delta','viernes','sala verde'))))
        self.assertFalse(bot.kb.contains(Atom(pred,('delta','jueves','sala roja'))))

    def test_complete_correction_can_repair_earlier_topic_using_shared_arguments(self):
        bot=Bot(allow_extensional_grounding=False)
        event=self._ground_event(bot); delivery=self._ground_delivery(bot)
        event_id=bot.respond('evento delta sera jueves en sala roja')['id']
        delivery_id=bot.respond('dora entrega carta a raul')['id']
        report=bot.respond('No, evento delta sera viernes en sala verde.')
        self.assertEqual(report['status'],'corrected_contextually')
        self.assertEqual(report['changed_slots'],[1,2])
        self.assertEqual(report['mechanism'],'grounded_multi_slot_revision_v516')
        self.assertIsNone(bot.kb.get_fact(event_id))
        self.assertIsNotNone(bot.kb.get_fact(delivery_id))
        self.assertTrue(bot.kb.contains(Atom(event,('delta','viernes','sala verde'))))
        self.assertTrue(bot.kb.contains(Atom(delivery,('dora','carta','raul'))))
        self.assertEqual(bot.last_fact,report['id'])
        self.assertEqual(bot.discourse_facts[-1],report['id'])

    def test_complete_correction_can_flip_polarity_without_changing_arguments(self):
        bot=Bot(allow_extensional_grounding=False)
        pred=self._ground_event(bot)
        old=bot.respond('evento delta sera jueves en sala roja')['id']
        report=bot.respond('No, evento delta no sera jueves en sala roja.')
        self.assertEqual(report['status'],'corrected_contextually')
        self.assertEqual(report['changed_slots'],[])
        self.assertTrue(report['polarity_changed'])
        self.assertIsNone(bot.kb.get_fact(old))
        self.assertFalse(bot.kb.contains(Atom(pred,('delta','jueves','sala roja'))))
        self.assertTrue(bot.kb.contains(Atom('!'+pred,('delta','jueves','sala roja'))))

    def test_equally_identified_prior_facts_make_complete_repair_ambiguous(self):
        bot=Bot(allow_extensional_grounding=False)
        for row in [
            'equipo alfa usa llave roja en zona norte',
            'equipo beta usa llave azul en zona sur',
            'equipo gamma usa llave blanca en zona este',
        ]:
            learned=bot.respond(row)
        pred=learned['predicate']
        a=bot.respond('equipo delta usa llave uno en zona uno')['id']
        b=bot.respond('equipo delta usa llave dos en zona dos')['id']
        report=bot.respond('No, equipo delta usa llave nueva en zona nueva.')
        self.assertEqual(report['status'],'correction_ambiguous')
        self.assertEqual(report['reason'],'multiple_grounded_repairs')
        self.assertIsNotNone(bot.kb.get_fact(a)); self.assertIsNotNone(bot.kb.get_fact(b))
        self.assertTrue(bot.kb.contains(Atom(pred,('delta','uno','uno'))))
        self.assertTrue(bot.kb.contains(Atom(pred,('delta','dos','dos'))))

    def test_unresolved_second_negator_and_disjunction_never_mutate_fact(self):
        bot=Bot(allow_extensional_grounding=False)
        pred=self._ground_event(bot)
        fid=bot.respond('evento delta sera jueves en sala roja')['id']
        first=bot.respond('No, no sera jueves en sala roja.')
        self.assertEqual(first['status'],'correction_unresolved')
        self.assertEqual(first['reason'],'unresolved_correction_polarity')
        second=bot.respond('No, sera viernes o sabado.')
        self.assertEqual(second['status'],'correction_ambiguous')
        self.assertEqual(second['reason'],'explicit_disjunction')
        self.assertEqual(bot.last_fact,fid)
        self.assertTrue(bot.kb.contains(Atom(pred,('delta','jueves','sala roja'))))

    def test_revision_audit_preserves_original_source(self):
        bot=Bot(allow_extensional_grounding=False)
        self._ground_event(bot)
        bot.respond('evento delta sera jueves en sala roja')
        report=bot.respond('No, sera viernes en sala verde.')
        audit=[x for x in bot.kb.audit if x.get('event')=='correction' and x.get('new')==report['id']]
        self.assertEqual(len(audit),1)
        self.assertEqual(audit[0]['source'],'conversación')
        self.assertEqual(audit[0]['old_atom']['args'],['delta','jueves','sala roja'])
        self.assertEqual(audit[0]['new_atom']['args'],['delta','viernes','sala verde'])

    def test_discourse_history_persists_and_can_repair_pre_restart_earlier_topic(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            event=self._ground_event(bot); delivery=self._ground_delivery(bot)
            bot.respond('evento delta sera jueves en sala roja')
            bot.respond('dora entrega carta a raul')
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                report=loaded.respond('No, evento delta sera viernes en sala verde.')
                self.assertEqual(report['status'],'corrected_contextually')
                self.assertTrue(loaded.kb.contains(Atom(event,('delta','viernes','sala verde'))))
                self.assertTrue(loaded.kb.contains(Atom(delivery,('dora','carta','raul'))))
                self.assertEqual(loaded.discourse_facts[-1],report['id'])
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

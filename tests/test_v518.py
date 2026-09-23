import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V518DocumentAcquisitionTests(unittest.TestCase):
    DOC='''
Nodo alfa conecta puerto rojo.
Nodo beta conecta puerto azul.
Nodo gamma conecta puerto verde.
Nodo delta conecta puerto negro.
'''

    def test_repeated_document_sentences_induce_relation_and_store_all_facts_with_provenance(self):
        bot=Bot(allow_extensional_grounding=False)
        report=bot.ingest_document_text(self.DOC,source='manual_demo')
        self.assertEqual(report['status'],'document_ingested')
        self.assertEqual(report['sentences'],4)
        self.assertEqual(report['relations_promoted'],1)
        self.assertEqual(report['facts_added'],4)
        pred=report['promoted_predicates'][0]
        self.assertTrue(bot.kb.contains(Atom(pred,('delta','negro'))))
        facts=list(bot.kb.matches(Atom(pred,('?x','?y'))))
        self.assertEqual(len(facts),4)
        self.assertTrue(all(f['source'].startswith('manual_demo:oración:') for f in facts))
        answer=bot.respond('¿nodo delta conecta puerto qué?')
        self.assertEqual(answer['status'],'bindings')
        self.assertTrue(any(p['atom']['args']==['delta','negro'] for p in answer['proofs']))

    def test_questions_and_conditionals_in_document_are_data_boundaries_not_executed_turns(self):
        bot=Bot(allow_extensional_grounding=False)
        text='''
Nodo alfa conecta puerto rojo.
¿Nodo alfa conecta puerto rojo?
Si nodo alfa conecta puerto rojo entonces nodo alfa activa puerto rojo.
Nodo beta conecta puerto azul.
Nodo gamma conecta puerto verde.
'''
        report=bot.ingest_document_text(text,source='doc_safe')
        self.assertEqual(report['questions_skipped'],1)
        self.assertEqual(report['conditionals_skipped'],1)
        self.assertEqual(len(bot.kb.rules),0)
        self.assertIsNone(bot.last_result)
        self.assertIsNone(bot.last_fact)
        self.assertEqual(bot.discourse_facts,[])

    def test_metalinguistic_sentence_in_document_cannot_execute_paraphrase_instruction(self):
        bot=Bot(allow_extensional_grounding=False)
        for row in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
            bot.respond(row)
        before=len(bot.language.examples)
        report=bot.ingest_document_text('"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".',source='quoted_text')
        self.assertEqual(report['document_meta_instructions_executed'],0)
        self.assertEqual(len(bot.language.examples),before)
        self.assertEqual(bot.respond('¿qué entrega bea a mario?')['status'],'grounding_pending')

    def test_learned_surface_supports_one_shot_fact_in_later_document(self):
        bot=Bot(allow_extensional_grounding=False)
        first=bot.ingest_document_text(self.DOC,source='doc_a')
        pred=first['promoted_predicates'][0]
        before=bot.kb.stats()['facts']
        second=bot.ingest_document_text('Nodo epsilon conecta puerto plata.',source='doc_b')
        self.assertEqual(second['facts_added'],1)
        self.assertEqual(bot.kb.stats()['facts'],before+1)
        fact=next(bot.kb.matches(Atom(pred,('epsilon','plata'))),None)
        self.assertIsNotNone(fact)
        self.assertEqual(fact['source'],'doc_b:oración:1')

    def test_document_ingestion_does_not_replace_conversation_focus(self):
        bot=Bot(allow_extensional_grounding=False)
        for row in ['proyecto alfa ocurre lunes','proyecto beta ocurre martes','proyecto gamma ocurre miercoles']:
            bot.respond(row)
        conversational=bot.respond('proyecto delta ocurre jueves')['id']
        bot.ingest_document_text(self.DOC,source='background_doc')
        self.assertEqual(bot.last_fact,conversational)
        self.assertEqual(bot.discourse_facts[-1],conversational)
        corrected=bot.respond('No, ocurre viernes.')
        self.assertEqual(corrected['status'],'corrected_contextually')
        self.assertEqual(corrected['old_id'],conversational)

    def test_document_grammar_and_facts_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            bot=ScalableBot(db,allow_extensional_grounding=False)
            report=bot.ingest_document_text(self.DOC,source='persistent_doc')
            pred=report['promoted_predicates'][0]
            bot.save(side); bot.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(loaded.kb.contains(Atom(pred,('delta','negro'))))
                answer=loaded.respond('¿nodo delta conecta puerto qué?')
                self.assertEqual(answer['status'],'bindings')
            finally:
                loaded.close()

    def test_document_sentence_budget_is_enforced(self):
        bot=Bot(allow_extensional_grounding=False)
        with self.assertRaises(ValueError):
            bot.ingest_document_text('A uno. A dos. A tres.',max_sentences=2)


if __name__=='__main__':
    unittest.main()

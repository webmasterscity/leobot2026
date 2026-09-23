import tempfile
import unittest
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


def grounded_root():
    bot=Bot(KnowledgeBase(),allow_extensional_grounding=True)
    for i in range(6):
        bot.kb.add(Atom('socio',(f'persona{i}',f'objeto{i}')))
    for text in [
        'persona0 conecta objeto0','persona1 conecta objeto1',
        'persona0 no conecta objeto1','persona1 no conecta objeto0',
    ]:
        report=bot.observe_schema_statement(text)
    return bot,report['learning']['target']


class V43BootstrappedLanguageTests(unittest.TestCase):
    def test_acquired_facts_ground_new_paraphrase_then_paraphrase_acquires_more_entities(self):
        bot,target=grounded_root()
        ids=[]
        for i in range(4):
            report=bot.acquire_schema_assertion(f'agente externo {i} conecta modulo experimental {i}')
            self.assertEqual(report['status'],'schema_fact_stored')
            ids.append(report['id'])
        first=bot.respond('agente externo 0 se asocia con modulo experimental 0')
        second=bot.respond('agente externo 1 se asocia con modulo experimental 1')
        self.assertEqual(first['status'],'grounding_pending')
        self.assertEqual(second['status'],'stored')
        examples=[x for x in bot.language.examples if x.get('source')=='grounded_induction']
        self.assertEqual(len(examples),1)  # one generalized construction, supported by two episodes
        self.assertTrue(set(examples[0]['evidence']).issubset(set(ids)))
        promoted=[x for x in bot.grounding_hypotheses.values() if x.get('promoted')]
        self.assertEqual(len(promoted),1)
        self.assertEqual(len(promoted[0]['observations']),2)
        observed_evidence={e for obs in promoted[0]['observations']
                           for detail in obs['candidates'].values() for e in detail['evidence']}
        self.assertTrue(observed_evidence.issubset(set(ids)))
        learned=bot.language.parse('agente externo 2 se asocia con modulo experimental 2')
        self.assertEqual(learned['status'],'parsed')
        self.assertEqual(learned['frame']['pred'],target)

        novel='persona omega nueva se asocia con modulo zeta nuevo'
        before=bot.kb.known_entities({'persona omega nueva','modulo zeta nuevo'})
        self.assertEqual(before,set())
        stored=bot.respond(novel)
        self.assertEqual(stored['status'],'stored')
        self.assertEqual(bot.kb.known_entities({'persona omega nueva','modulo zeta nuevo'}),
                         {'persona omega nueva','modulo zeta nuevo'})
        self.assertEqual(bot.query_schema('persona omega nueva conecta modulo zeta nuevo')['status'],'entailed')

    def test_bootstrapped_paraphrase_persists_and_keeps_open_entity_slots(self):
        bot,_=grounded_root()
        for i in range(2):
            bot.acquire_schema_assertion(f'agente externo {i} conecta modulo experimental {i}')
            bot.respond(f'agente externo {i} se asocia con modulo experimental {i}')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bot.json'; bot.save(path); loaded=Bot.load(path)
            response=loaded.respond('persona persistente se asocia con modulo persistente')
            self.assertEqual(response['status'],'stored')
            self.assertEqual(loaded.query_schema('persona persistente conecta modulo persistente')['status'],'entailed')

    def test_without_acquired_grounding_facts_new_paraphrase_cannot_bootstrap(self):
        bot,_=grounded_root()
        response=bot.respond('agente externo cero se asocia con modulo experimental cero')
        self.assertNotEqual(response['status'],'grounding_pending')
        self.assertEqual(bot.language.parse('agente externo uno se asocia con modulo experimental uno')['status'],
                         'unrecognized')


if __name__=='__main__':
    unittest.main()

"""Unknown wording can request a contrast using roots learned from raw text."""
import unittest

from leobot import Bot
from leobot.core import Atom


class RawRootProbeTests(unittest.TestCase):
    def test_default_bot_requests_evidence_from_two_raw_learned_relations(self):
        bot=Bot()
        roots=[]
        for verb in ('enlaza','sostiene'):
            last=None
            for left,right in (('Ana','Luis'),('Bea','Mario'),('Cora','Nora')):
                last=bot.respond(f'{left} {verb} {right}')
            self.assertEqual(last['status'],'raw_relation_learned')
            roots.append(last['predicate'])
        self.assertFalse(bot.allow_extensional_grounding)
        self.assertEqual(bot.respond('Dana enlaza Ciro')['status'],'stored')
        self.assertEqual(bot.respond('Dana no sostiene Ciro')['status'],'stored')

        self.assertEqual(bot.respond('Ana protege Luis')['status'],'grounding_pending')
        self.assertEqual(bot.respond('Bea protege Mario')['status'],'grounding_pending')
        self.assertEqual(bot.language.parse('Fina protege Teo')['status'],'unrecognized')
        proposal=bot.propose_grounding_probe()
        self.assertEqual(proposal['status'],'epistemic_action')
        self.assertEqual(proposal['probe_text'],'dana protege ciro')
        self.assertEqual(bot.observe_grounding_probe(proposal['probe_id'],True)['status'],
                         'grounding_promoted')
        self.assertEqual(bot.language.parse('Fina protege Teo')['frame']['pred'],roots[0])
        self.assertEqual(bot.respond('Fina protege Teo')['status'],'stored')
        self.assertTrue(bot.kb.contains(Atom(roots[0],('fina','teo'))))
        self.assertEqual(bot.observe_grounding_probe(proposal['probe_id'],False)['status'],
                         'grounding_conflict')
        self.assertFalse(bot.kb.contains(Atom(roots[0],('fina','teo'))))


if __name__=='__main__':
    unittest.main()

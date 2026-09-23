"""Rival meanings keep feeding raw induction; an answer bridges, never collides."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom


def educated() -> tuple[Bot, list[str]]:
    bot=Bot()
    roots=[]
    for verb in ('enlaza','sostiene'):
        last=None
        for left,right in (('Ana','Luis'),('Bea','Mario'),('Cora','Nora')):
            last=bot.respond(f'{left} {verb} {right}')
        roots.append(last['predicate'])
    bot.respond('Dana enlaza Ciro')
    bot.respond('Dana no sostiene Ciro')
    return bot,roots


class RawRootBridgeTests(unittest.TestCase):
    def three_sentences(self, reverse: bool):
        bot,roots=educated()
        pairs=(('Ana','Luis'),('Bea','Mario'),('Cora','Nora'))
        texts=[f'{b} protege {a}' if reverse else f'{a} protege {b}' for a,b in pairs]
        statuses=[bot.respond(text)['status'] for text in texts]
        return bot,roots,statuses

    def test_third_rival_sentence_induces_raw_root_and_keeps_rivals(self):
        bot,roots,statuses=self.three_sentences(reverse=False)
        self.assertEqual(statuses,['grounding_pending','grounding_pending','raw_relation_learned'])
        raw=bot.language.parse('Fina protege Teo')['frame']['pred']
        self.assertNotIn(raw,roots)
        for pair in (('ana','luis'),('bea','mario'),('cora','nora')):
            self.assertTrue(bot.kb.contains(Atom(raw,pair)))
        states=[s for s in bot.grounding_hypotheses.values() if not s.get('conflict')]
        self.assertEqual([len(s['possible']) for s in states],[2])
        self.assertFalse(states[0].get('promoted'))
        self.assertFalse(any(raw in (r.head.pred,*(a.pred for a in r.body))
                             for r in bot.kb.rules.values()))

    def test_answer_bridges_raw_root_without_ambiguity_and_rolls_back(self):
        for reverse in (False,True):
            with self.subTest(reverse=reverse):
                bot,roots,_=self.three_sentences(reverse)
                held='Teo protege Fina' if reverse else 'Fina protege Teo'
                raw=bot.language.parse(held)['frame']['pred']
                proposal=bot.propose_grounding_probe()
                self.assertEqual(proposal['probe_text'],
                                 'ciro protege dana' if reverse else 'dana protege ciro')
                promoted=bot.observe_grounding_probe(proposal['probe_id'],True)
                self.assertEqual(promoted['status'],'grounding_promoted')
                self.assertEqual(promoted['construction_count'],0)
                self.assertEqual(len(promoted['bridge_rule_ids']),2)
                parsed=bot.language.parse(held)
                self.assertEqual(parsed['status'],'parsed')
                self.assertEqual(parsed['frame']['pred'],raw)
                self.assertEqual(bot.respond(held)['status'],'stored')
                self.assertEqual(bot.answer_atom(Atom(roots[0],('fina','teo')))['status'],
                                 'hypothesis')
                self.assertEqual(bot.answer_atom(Atom(roots[0],('teo','fina')))['status'],
                                 'unknown')
                self.assertEqual(bot.answer_atom(Atom(roots[1],('fina','teo')))['status'],
                                 'unknown')
                bot.respond('Gala enlaza Hugo')
                inverse=('hugo','gala') if reverse else ('gala','hugo')
                self.assertEqual(bot.answer_atom(Atom(raw,inverse))['status'],'hypothesis')

                with tempfile.TemporaryDirectory() as directory:
                    path=Path(directory)/'bot.json'
                    bot.save(path); bot=Bot.load(path)
                self.assertEqual(bot.answer_atom(Atom(roots[0],('fina','teo')))['status'],
                                 'hypothesis')
                conflict=bot.observe_grounding_probe(proposal['probe_id'],False)
                self.assertEqual(conflict['status'],'grounding_conflict')
                self.assertEqual(conflict['rules_withdrawn'],2)
                self.assertEqual(bot.answer_atom(Atom(roots[0],('fina','teo')))['status'],
                                 'unknown')
                self.assertEqual(bot.answer_atom(Atom(raw,inverse))['status'],'unknown')
                held_args=('teo','fina') if reverse else ('fina','teo')
                self.assertTrue(bot.kb.contains(Atom(raw,held_args)))
                self.assertTrue(bot.kb.contains(Atom(roots[0],('gala','hugo'))))
                self.assertEqual(bot.language.parse(held)['frame']['pred'],raw)


if __name__=='__main__':
    unittest.main()

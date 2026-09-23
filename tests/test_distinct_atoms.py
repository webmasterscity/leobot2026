"""G-38: prover work grows with distinct atoms, not with repeated sources."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom, Engine, Rule
from leobot.diskkb import SQLiteKnowledgeBase


def fill(kb, n=2000):
    for i in range(n):
        kb.add(Atom('padre', ('a', 'b')), f's{i}')
        kb.add(Atom('padre', ('b', 'c')), f's{i}')
    kb.add_rule(Rule('abuelo_def', Atom('abuelo', ('?x', '?z')),
                     (Atom('padre', ('?x', '?y')), Atom('padre', ('?y', '?z')))))


class DistinctAtomTests(unittest.TestCase):
    def check_small_budget(self, kb):
        engine = Engine(kb, max_work=1000)
        for text, status in (('padre(a,b)', 'supported'), ('!padre(a,b)', 'refuted'),
                             ('padre(a,?x)', 'bindings'), ('abuelo(a,c)', 'supported'),
                             ('abuelo(?x,c)', 'bindings')):
            result = engine.answer(Atom.parse(text))
            self.assertEqual(result['status'], status, text)
            self.assertTrue(result['positive']['complete'], text)
        proof = engine.answer(Atom.parse('padre(a,b)'))['positive']['answers'][0]
        self.assertEqual(proof.id, 'f1')

    def test_memory_repeated_sources_fit_a_small_budget(self):
        bot = Bot(); fill(bot.kb); self.check_small_budget(bot.kb)

    def test_disk_repeated_sources_fit_a_small_budget(self):
        with tempfile.TemporaryDirectory() as d:
            kb = SQLiteKnowledgeBase(Path(d) / 'k.sqlite'); fill(kb); self.check_small_budget(kb); kb.close()

    def distinct(self, kb, pattern):
        return [(f['id'], f['atom']) for f in kb.distinct_matches(Atom.parse(pattern))]

    def check_add_remove(self, kb):
        x, y = Atom('vive', ('ana', 'lima')), Atom('vive', ('ana', 'cusco'))
        f1 = kb.add(x, 'uno'); f2 = kb.add(y, 'uno'); f3 = kb.add(x, 'dos')
        self.assertEqual([f['id'] for f in kb.matches(Atom.parse('vive(ana,?c)'))], [f1, f2, f3])
        self.assertEqual(self.distinct(kb, 'vive(ana,?c)'), [(f1, x), (f2, y)])
        kb.remove(f1)
        self.assertEqual(self.distinct(kb, 'vive(ana,?c)'), [(f2, y), (f3, x)])
        self.assertEqual(self.distinct(kb, 'vive(ana,lima)'), [(f3, x)])
        kb.remove(f3)
        self.assertEqual(self.distinct(kb, 'vive(?p,lima)'), [])
        self.assertFalse(kb.contains(x))
        return f2

    def test_memory_add_remove_and_restart(self):
        bot = Bot(); f2 = self.check_add_remove(bot.kb)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bot.json'; bot.save(path); restored = Bot.load(path)
        self.assertEqual(self.distinct(restored.kb, 'vive(ana,?c)'), [(f2, Atom('vive', ('ana', 'cusco')))])

    def test_disk_add_remove_and_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'k.sqlite'
            kb = SQLiteKnowledgeBase(path); f2 = self.check_add_remove(kb); kb.close()
            kb = SQLiteKnowledgeBase(path)
            self.assertEqual(self.distinct(kb, 'vive(ana,?c)'), [(f2, Atom('vive', ('ana', 'cusco')))])
            kb.close()

    def test_disk_file_from_before_the_atom_table_is_backfilled(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'k.sqlite'
            kb = SQLiteKnowledgeBase(path)
            for i in range(3):
                kb.add(Atom('vive', ('ana', 'lima')), f's{i}')
            kb.db.execute('DROP TABLE atoms'); kb.close()
            kb = SQLiteKnowledgeBase(path)
            self.assertEqual(self.distinct(kb, 'vive(?p,lima)'), [('f1', Atom('vive', ('ana', 'lima')))])
            kb.close()


if __name__ == '__main__':
    unittest.main()

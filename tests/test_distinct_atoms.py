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

    def test_disk_atoms_stay_current_under_direct_sql_writes(self):
        # G-38b: another writer (e.g. an older engine) changes facts without the
        # engine; the triggers inside the file keep the atom table current.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'k.sqlite'
            kb = SQLiteKnowledgeBase(path)
            for source in ('s1', 's2'):
                kb.add(Atom('p', ('a', 'b')), source)
            kb.add(Atom('p', ('c', 'd'))); kb.close()
            import sqlite3
            db = sqlite3.connect(path)
            db.execute("INSERT INTO facts(pred,base_pred,arity,a0,a1,source,fact_key) VALUES('p','p',2,'x','y','s9','k9')")
            db.execute('DELETE FROM facts WHERE id IN (1,3)'); db.commit(); db.close()
            kb = SQLiteKnowledgeBase(path)
            self.assertEqual(self.distinct(kb, 'p(?u,?v)'), [('f2', Atom('p', ('a', 'b'))), ('f4', Atom('p', ('x', 'y')))])
            self.assertEqual(Engine(kb).answer(Atom.parse('p(x,y)'))['status'], 'supported')
            self.assertFalse(kb.contains(Atom('p', ('c', 'd'))))
            kb.close()

    def test_disk_keys_do_not_collide(self):
        with tempfile.TemporaryDirectory() as d:
            kb = SQLiteKnowledgeBase(Path(d) / 'k.sqlite')
            first, second = Atom('p', ('a\x1fb', 'c')), Atom('p', ('a', 'b\x1fc'))
            f1, f2 = kb.add(first, 's1'), kb.add(second, 's1')
            self.assertNotEqual(f1, f2)
            self.assertTrue(kb.contains(first)); self.assertTrue(kb.contains(second))
            self.assertTrue(kb.remove(f1))
            self.assertEqual(self.distinct(kb, 'p(a,?y)'), [(f2, second)])
            kb.close()

    def test_disk_file_in_an_older_format_is_migrated(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'k.sqlite'
            kb = SQLiteKnowledgeBase(path)
            for source in ('s1', 's2'):
                kb.add(Atom('vive', ('ana', 'lima')), source)
            kb.close()
            # Rewrite the file as an estable-G-7 file: no atom table or triggers,
            # separator-joined fact keys, format version 0.
            import hashlib
            db = sqlite3.connect(path)
            for name in ('facts_atoms_insert', 'facts_atoms_delete', 'facts_atoms_update'):
                db.execute(f'DROP TRIGGER {name}')
            db.execute('DROP TABLE atoms'); db.execute('PRAGMA user_version=0')
            for fid, source in db.execute('SELECT id, source FROM facts').fetchall():
                old = hashlib.blake2b('\x1f'.join(('vive', source, 'ana', 'lima')).encode(), digest_size=16).hexdigest()
                db.execute('UPDATE facts SET fact_key=? WHERE id=?', (old, fid))
            db.commit(); db.close()
            kb = SQLiteKnowledgeBase(path)
            self.assertEqual(self.distinct(kb, 'vive(?p,?c)'), [('f1', Atom('vive', ('ana', 'lima')))])
            self.assertEqual(kb.add(Atom('vive', ('ana', 'lima')), 's2'), 'f2')
            kb.remove('f1')
            self.assertEqual(self.distinct(kb, 'vive(ana,lima)'), [('f2', Atom('vive', ('ana', 'lima')))])
            kb.close()


if __name__ == '__main__':
    unittest.main()

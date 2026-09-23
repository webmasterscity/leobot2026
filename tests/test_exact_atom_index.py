"""G-37: an exact-atom index answers whether a ground fact exists."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom


class ExactAtomIndexTests(unittest.TestCase):
    def test_contains_tracks_add_remove_sources_and_restart(self):
        bot=Bot(); kb=bot.kb
        atom=Atom('vive',('ana','lima'))
        self.assertFalse(kb.contains(atom))
        first=kb.add(atom,'uno'); second=kb.add(atom,'dos')
        self.assertTrue(kb.contains(atom))
        kb.remove(first)
        self.assertTrue(kb.contains(atom))
        kb.remove(second)
        self.assertFalse(kb.contains(atom))
        kb.add(atom,'tres')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bot.json'; bot.save(path); restored=Bot.load(path)
        self.assertTrue(restored.kb.contains(atom))
        self.assertFalse(restored.kb.contains(Atom('vive',('ana','cusco'))))
        self.assertTrue(restored.kb.contains(Atom('vive',('ana','?x'))))


if __name__=='__main__':
    unittest.main()

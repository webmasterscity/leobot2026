import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.metacontrol import MetaController


class V67MetaRepresentationInventionTests(unittest.TestCase):
    @staticmethod
    def train_xor(controller: MetaController, family='representation'):
        idx=0
        for rep in range(4):
            for a,b in ((0,0),(0,1),(1,0),(1,1)):
                features=(float(a),float(b),(rep+1)/10.0,(idx+1)/100.0)
                winner='A' if a==b else 'B'
                for strategy in ('A','B'):
                    controller.observe(family,features,strategy,
                                       success=(strategy==winner),
                                       cost=(1 if strategy==winner else 10),
                                       failure_budget=2)
                idx+=1

    def test_invents_conjunctive_view_not_single_feature(self):
        m=MetaController(); self.train_xor(m)
        view=m.invented_views.get('representation')
        self.assertIsNotNone(view)
        self.assertEqual(view['dims'],[0,1])
        self.assertEqual(view['accuracy'],1.0)
        self.assertEqual(view['coverage'],1.0)
        # Neither single dimension can solve XOR; the invented representation
        # must retain their conjunction while dropping irrelevant dimensions.
        self.assertGreaterEqual(view['gain_over_majority'],0.49)

    def test_invented_view_routes_unseen_full_signature(self):
        m=MetaController(); self.train_xor(m)
        # Irrelevant dimensions were never observed at these values.
        for features,winner in [((0,0,.91,.87),'A'),((0,1,.91,.87),'B'),
                                ((1,0,.77,.93),'B'),((1,1,.77,.93),'A')]:
            route=m.rank('representation',features,['A','B'])
            self.assertEqual(route['mode'],'invented_view')
            self.assertEqual(route['order'][0],winner)
            self.assertEqual(route['view']['dims'],[0,1])

    def test_contradictory_regime_withdraws_invalid_view(self):
        m=MetaController(); self.train_xor(m,'x')
        self.assertIsNotNone(m.invented_views.get('x'))
        idx=16
        for rep in range(4,8):
            for a,b in ((0,0),(0,1),(1,0),(1,1)):
                features=(float(a),float(b),(rep+1)/10.0,(idx+1)/100.0)
                winner='B' if a==b else 'A'
                for strategy in ('A','B'):
                    m.observe('x',features,strategy,success=(strategy==winner),
                              cost=(1 if strategy==winner else 10),failure_budget=2)
                idx+=1
        self.assertIsNone(m.invented_views.get('x'))
        self.assertEqual(m.rank('x',(0,1,.99,.88),['A','B'])['mode'] in
                         ('default','rbf','rbf_promote'),True)

    def test_invented_view_persists_at_bot_level(self):
        bot=Bot(); self.train_xor(bot.meta_controller)
        self.assertEqual(bot.meta_controller.invented_views['representation']['dims'],[0,1])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json'; bot.save(p); loaded=Bot.load(p)
        self.assertEqual(loaded.meta_controller.invented_views['representation']['dims'],[0,1])
        route=loaded.meta_controller.rank('representation',(1,0,.88,.99),['A','B'])
        self.assertEqual(route['mode'],'invented_view')
        self.assertEqual(route['order'][0],'B')


if __name__=='__main__':
    unittest.main()

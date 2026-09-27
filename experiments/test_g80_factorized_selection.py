import importlib
import unittest


class FactorizedSelectionContract(unittest.TestCase):
    def module(self):
        return importlib.import_module('experiments.g80_factorized_selection')

    def test_pool_ignores_candidate_order_and_does_not_read_labels(self):
        m = self.module()
        candidates = [{'a': '2', 'b': 'x'}, {'a': '0', 'b': 'y'}, {'a': '1', 'b': 'x'}]
        pooled = m.pool(candidates)
        self.assertEqual(pooled, m.pool(list(reversed(candidates))))
        self.assertEqual((pooled['min:a'], pooled['max:a']), ('0', '2'))
        self.assertEqual((pooled['mode:b'], pooled['diversity:b']), ('x', '2'))

    def test_eligibility_is_learned_separately_and_businesses_do_not_cross(self):
        m = self.module()
        components = m.Components()
        turns = []
        for i in range(240):
            eligible = int(i % 3 != 0)
            # Some eligible turns have no correct candidate; they remain A=1.
            rows = [({'x': str(j), 'seen': str(eligible)}, int(eligible and i % 5 and j == 1))
                    for j in (0, 1)]
            turns.append({'group': 'g'+str(i % 4), 'half': i % 2, 'eligible': eligible,
                          'rows': rows, 'pooled': m.pool([f for f, _ in rows])})
        models, audit = m.educate(turns, components.learner)
        for fold in audit['folds']:
            self.assertFalse(set(fold['taught_groups']) & set(fold['scored_groups']))
        self.assertEqual(audit['eligible_turns'], 160)
        self.assertGreater(audit['eligible_without_correct_candidate'], 0)
        ns = components.learner
        model = models['factorized']['eligibility']
        high, low = (m.pool([{'x': str(j), 'seen': s} for j in (0, 1)]) for s in ('1', '0'))
        self.assertGreater(ns['score'](model, high, sorted(high)), ns['score'](model, low, sorted(low)))
        reversed_turns = [{**t, 'rows': [(t['pooled'], 1-t['eligible'])]} for t in turns]
        reversed_model = ns['fit'](reversed_turns, sorted(high))
        self.assertLess(ns['score'](reversed_model, high, sorted(high)),
                        ns['score'](reversed_model, low, sorted(low)))

    def test_new_document_and_disabled_gate_leave_no_previous_question_state(self):
        m = self.module()
        from leobot import Bot
        bot = Bot()
        original_rank = bot._rank
        components = m.Components()
        reference = components.bind(bot)
        gate = m.GateBinding(bot)
        bot.context_model['selection'] = {'k': 6, 'bias': 0., 'weights': {},
                                          'calibration': [[-999., .8, 100]], 'cite_from': .4}
        bot.context_model['eligibility'] = {'bias': -1., 'weights': {'n=1': 2.},
                                            'calibration': [[-999., .1, 50], [0., 1., 50]], 'mode': 'learned'}
        bot.load_context('u: 11.\nv: 22.', '')
        self.assertEqual(bot.answer('u v?')['status'], 'unknown')
        bot.load_context('u: 11.', '')
        self.assertEqual(bot.answer('u?')['status'], 'closest')
        self.assertIsNone(gate.captured)
        del bot.context_model['eligibility']
        before = bot.answer('u?')
        gate.restore()
        self.assertEqual(before, bot.answer('u?'))
        reference.restore()
        self.assertEqual(bot._rank, original_rank)


if __name__ == '__main__':
    unittest.main()

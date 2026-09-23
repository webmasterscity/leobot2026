import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.scalable import ScalableBot


class V529EventConsumerGateTests(unittest.TestCase):
    RELATIONS=('frobla','tulka','norga','peka','rula','soma','zeta','kora','miva','activa','rechaza')

    def _ground(self, bot):
        lines=[]
        for j,name in enumerate(self.RELATIONS):
            lines += [f'a{j}x {name} b{j}x.', f'a{j}y {name} b{j}y.', f'a{j}z {name} b{j}z.']
        r=bot.ingest_document_text(' '.join(lines),source='v529_grammar')
        self.assertEqual(r['relations_promoted'],len(self.RELATIONS))

    @staticmethod
    def _train_family(bot,names,prefix):
        p,q,r=names
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
                source=f'{prefix}_schema_{i}')

    @staticmethod
    def _use_family(bot,names,prefix,consumer='activa'):
        p,q,r=names
        return bot.ingest_document_text(
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso {consumer} {prefix}alarm.',
            source=f'{prefix}_use')

    def _trained(self, bot=None):
        b=bot or Bot(allow_extensional_grounding=False)
        self._ground(b)
        self._train_family(b,('frobla','tulka','norga'),'f')
        first=self._use_family(b,('frobla','tulka','norga'),'f')
        self.assertEqual(first['sentence_results'][3]['status'],'document_coreference_resolved')
        self._train_family(b,('peka','rula','soma'),'g')
        second=self._use_family(b,('peka','rula','soma'),'g')
        self.assertEqual(second['sentence_results'][3]['status'],'document_coreference_resolved')
        return b

    def test_two_disjoint_exact_uses_promote_consumer_gate(self):
        b=self._trained()
        gates=[g for g in b.document_event_reference_hypotheses.values() if g.get('promoted')]
        self.assertEqual(len(gates),1)
        self.assertEqual(gates[0]['support'],2)
        self.assertFalse(gates[0]['contested'])
        self.assertEqual(len(gates[0]['source_schemas']),2)
        fam=[set(x['predicates']) for x in gates[0]['source_schemas']]
        self.assertTrue(fam[0].isdisjoint(fam[1]))

    def test_meta_transfer_requires_previously_demonstrated_consumer_role(self):
        b=self._trained()
        allowed=b.ingest_document_text(
            'neo zeta objeto. neo kora lugar. neo miva tiempo. Eso activa sirena.',source='v529_allowed')
        self.assertEqual(allowed['sentence_results'][3]['status'],'document_coreference_resolved')
        self.assertEqual(allowed['sentence_results'][3]['references'][0]['criteria'],
                         ['latent_document_event_meta_v527'])
        blocked=b.ingest_document_text(
            'x zeta objeto2. x kora lugar2. x miva tiempo2. Eso rechaza ruido.',source='v529_blocked')
        self.assertEqual(blocked['sentence_results'][3]['status'],'document_coreference_unresolved')
        self.assertEqual(blocked['document_events_materialized'],0)

    def test_one_exact_family_does_not_promote_gate(self):
        b=Bot(allow_extensional_grounding=False);self._ground(b)
        self._train_family(b,('frobla','tulka','norga'),'f')
        self._use_family(b,('frobla','tulka','norga'),'f')
        gates=list(b.document_event_reference_hypotheses.values())
        self.assertEqual(len(gates),1)
        self.assertFalse(gates[0]['promoted'])
        self.assertEqual(gates[0]['support'],1)

    def test_meta_transferred_use_never_self_supports_a_gate(self):
        b=self._trained()
        before={k:g.get('support') for k,g in b.document_event_reference_hypotheses.items()}
        b.ingest_document_text('n zeta o. n kora l. n miva t. Eso activa a.',source='v529_meta_use')
        after={k:g.get('support') for k,g in b.document_event_reference_hypotheses.items()}
        self.assertEqual(after,before)

    def test_gate_persists_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db';side=Path(td)/'state.json'
            b=self._trained(ScalableBot(db,allow_extensional_grounding=False))
            b.save(side);b.close()
            loaded=ScalableBot.load(side,db)
            try:
                self.assertTrue(any(g.get('promoted') for g in loaded.document_event_reference_hypotheses.values()))
                r=loaded.ingest_document_text(
                    'neo zeta obj. neo kora loc. neo miva time. Eso activa alarm.',source='v529_after_reload')
                self.assertEqual(r['sentence_results'][3]['status'],'document_coreference_resolved')
            finally:
                loaded.close()


if __name__=='__main__':
    unittest.main()

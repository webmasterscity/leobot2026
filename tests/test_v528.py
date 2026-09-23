import tempfile
import unittest
from pathlib import Path

from leobot import Bot
from leobot.core import Atom
from leobot.scalable import ScalableBot


class V528EventMetaBootstrapTests(unittest.TestCase):
    BASE_RELATIONS=(
        'frobla','tulka','norga','peka','rula','soma',
        'activa','blen','drak','fesp'
    )

    @staticmethod
    def _ground(bot, names):
        lines=[]
        for j,name in enumerate(names):
            lines += [f'a{j}x {name} b{j}x.', f'a{j}y {name} b{j}y.', f'a{j}z {name} b{j}z.']
        report=bot.ingest_document_text(' '.join(lines), source='v528_grammar')
        return report

    @staticmethod
    def _train_family(bot, names, prefix):
        p,q,r=names
        for i in range(3):
            bot.ingest_document_text(
                f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
                source=f'{prefix}_schema_{i}')
        use=bot.ingest_document_text(
            f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso activa {prefix}alarm.',
            source=f'{prefix}_use')
        return use

    def _meta_trained(self, bot=None):
        b=bot or Bot(allow_extensional_grounding=False)
        # Ground six predicate-disjoint relations with three different surface
        # geometries, plus a query relation whose surface is different again.
        grammar='''
ana frobla caja. bruno frobla carta. cora frobla libro.
en puerto reposa ana. en plaza reposa bruno. en parque reposa cora.
lunes corresponde a ana. martes corresponde a bruno. miercoles corresponde a cora.
dora peka paquete. eva peka archivo. luis peka carpeta.
en norte duerme dora. en sur duerme eva. en centro duerme luis.
jueves asignado a dora. viernes asignado a eva. sabado asignado a luis.
alarma1 ocurre por uno. alarma2 ocurre por dos. alarma3 ocurre por tres.
'''
        g=b.ingest_document_text(grammar,source='v528_grammar')
        self.assertEqual(g['relations_promoted'],7)
        fam1=[('f0 frobla fo0','en fl0 reposa f0','ft0 corresponde a f0'),
              ('f1 frobla fo1','en fl1 reposa f1','ft1 corresponde a f1'),
              ('f2 frobla fo2','en fl2 reposa f2','ft2 corresponde a f2')]
        fam2=[('g0 peka go0','en gl0 duerme g0','gt0 asignado a g0'),
              ('g1 peka go1','en gl1 duerme g1','gt1 asignado a g1'),
              ('g2 peka go2','en gl2 duerme g2','gt2 asignado a g2')]
        for i,rows in enumerate(fam1):
            b.ingest_document_text('. '.join(rows)+'.',source=f'f_schema_{i}')
        r1=b.ingest_document_text(
            'fu frobla fobj. en floc reposa fu. ftime corresponde a fu. alarma ocurre por eso.',
            source='f_use')
        self.assertEqual(r1['sentence_results'][3]['status'],'document_coreference_resolved')
        for i,rows in enumerate(fam2):
            b.ingest_document_text('. '.join(rows)+'.',source=f'g_schema_{i}')
        r2=b.ingest_document_text(
            'gu peka gobj. en gloc duerme gu. gtime asignado a gu. alarma ocurre por eso.',
            source='g_use')
        self.assertEqual(r2['sentence_results'][3]['status'],'document_coreference_resolved')
        self.assertTrue(any(x.get('promoted') for x in b.document_event_meta_hypotheses.values()))
        return b

    def test_two_topology_consistent_raw_episodes_bootstrap_three_relations(self):
        b=self._meta_trained()
        first=b.ingest_document_text(
            'u1 blen objeto1. en lugar1 drak u1. tiempo1 fesp a u1.', source='bootstrap_1')
        self.assertNotEqual(first['document_event_meta_bootstrap']['status'],
                            'document_event_meta_bootstrap_learned')
        second=b.ingest_document_text(
            'u2 blen objeto2. en lugar2 drak u2. tiempo2 fesp a u2.', source='bootstrap_2')
        boot=second['document_event_meta_bootstrap']
        self.assertEqual(boot['status'],'document_event_meta_bootstrap_learned')
        self.assertEqual(len(boot['relations']),3)
        learned=[x for x in boot['relations'] if not x.get('existing')]
        self.assertEqual(len(learned),3)
        for rel in learned:
            promo=next(p for p in b.raw_relation_promotions.values()
                       if p.get('predicate')==rel['predicate'])
            self.assertEqual(promo['support'],2)
            self.assertEqual(promo['mechanism'],'event_topology_constrained_antiunification_v528')
            self.assertTrue(promo['event_meta_bootstrapped'])

    def test_bootstrapped_relations_transfer_to_new_entities_and_event_reference(self):
        b=self._meta_trained()
        b.ingest_document_text('u1 blen o1. en l1 drak u1. t1 fesp a u1.', source='transfer_1')
        learned=b.ingest_document_text('u2 blen o2. en l2 drak u2. t2 fesp a u2.', source='transfer_2')
        by_surface={p['surface']:p['predicate'] for p in b.raw_relation_promotions.values()}
        self.assertEqual(learned['document_event_meta_bootstrap']['status'],
                         'document_event_meta_bootstrap_learned')
        target=b.ingest_document_text(
            'neo blen objeto. en lugar drak neo. tiempo fesp a neo. sirena ocurre por eso.',
            source='transfer_target')
        row=target['sentence_results'][3]
        self.assertEqual(row['status'],'document_coreference_resolved')
        self.assertEqual(row['references'][0]['criteria'],['latent_document_event_meta_v527'])
        event_id=row['references'][0]['antecedent']
        ocurre=by_surface['{s0} ocurre por {s1}']
        self.assertTrue(b.kb.contains(Atom(ocurre,('sirena',event_id))))
        self.assertTrue(b.kb.contains(Atom(by_surface['{s0} blen {s1}'],('neo','objeto'))))
        self.assertTrue(b.kb.contains(Atom(by_surface['en {s0} drak {s1}'],('lugar','neo'))))
        self.assertTrue(b.kb.contains(Atom(by_surface['{s0} fesp a {s1}'],('tiempo','neo'))))

    def test_same_document_renamed_cannot_supply_second_episode(self):
        b=self._meta_trained()
        text='u1 blen objeto1. en lugar1 drak u1. tiempo1 fesp a u1.'
        for i in range(5):
            report=b.ingest_document_text(text,source=f'renamed_{i}')
            self.assertNotEqual(report['document_event_meta_bootstrap']['status'],
                                'document_event_meta_bootstrap_learned')
        self.assertFalse(any(p.get('event_meta_bootstrapped') for p in b.raw_relation_promotions.values()))

    def test_inconsistent_cross_sentence_role_binding_is_rejected(self):
        b=self._meta_trained()
        b.ingest_document_text('u1 blen o1. en l1 drak u1. t1 fesp a u1.', source='role_good')
        report=b.ingest_document_text(
            'v1 blen o2. en l2 drak v2. t2 fesp a v3.', source='role_bad')
        self.assertNotEqual(report['document_event_meta_bootstrap']['status'],
                            'document_event_meta_bootstrap_learned')
        self.assertFalse(any(p.get('event_meta_bootstrapped') for p in b.raw_relation_promotions.values()))

    def test_one_meta_source_family_is_not_enough_to_activate_bootstrap(self):
        b=Bot(allow_extensional_grounding=False)
        grammar='''
ana frobla caja. bruno frobla carta. cora frobla libro.
en puerto reposa ana. en plaza reposa bruno. en parque reposa cora.
lunes corresponde a ana. martes corresponde a bruno. miercoles corresponde a cora.
alarma1 ocurre por uno. alarma2 ocurre por dos. alarma3 ocurre por tres.
'''
        b.ingest_document_text(grammar,source='under_grammar')
        for i in range(3):
            b.ingest_document_text(
                f'f{i} frobla fo{i}. en fl{i} reposa f{i}. ft{i} corresponde a f{i}.',
                source=f'under_schema_{i}')
        b.ingest_document_text(
            'fu frobla fobj. en floc reposa fu. ftime corresponde a fu. alarma ocurre por eso.',
            source='under_use')
        self.assertFalse(any(x.get('promoted') for x in b.document_event_meta_hypotheses.values()))
        b.ingest_document_text('u1 blen o1. en l1 drak u1. t1 fesp a u1.', source='under_1')
        report=b.ingest_document_text('u2 blen o2. en l2 drak u2. t2 fesp a u2.', source='under_2')
        self.assertIn(report['document_event_meta_bootstrap']['status'],
                      ('document_event_meta_bootstrap_inactive','document_event_meta_bootstrap_no_span'))
        self.assertFalse(any(p.get('event_meta_bootstrapped') for p in b.raw_relation_promotions.values()))

    def test_pending_bootstrap_and_promotions_persist_in_scalable_bot(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'facts.db'; side=Path(td)/'state.json'
            b=self._meta_trained(ScalableBot(db,allow_extensional_grounding=False))
            b.ingest_document_text('u1 blen o1. en l1 drak u1. t1 fesp a u1.', source='persist_1')
            b.save(side); b.close()
            loaded=ScalableBot.load(side,db)
            try:
                report=loaded.ingest_document_text(
                    'u2 blen o2. en l2 drak u2. t2 fesp a u2.', source='persist_2')
                self.assertEqual(report['document_event_meta_bootstrap']['status'],
                                 'document_event_meta_bootstrap_learned')
                loaded.save(side)
            finally:
                loaded.close()
            again=ScalableBot.load(side,db)
            try:
                self.assertEqual(sum(bool(p.get('event_meta_bootstrapped'))
                                     for p in again.raw_relation_promotions.values()),3)
            finally:
                again.close()


if __name__=='__main__':
    unittest.main()

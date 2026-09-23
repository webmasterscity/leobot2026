"""V5.28 frozen experiment: learned event topology accelerates raw relation acquisition.

A promoted V5.27 event topology is the only extra information available to the
treatment.  Two structurally consistent raw document episodes must be sufficient
to acquire three previously unknown relation surfaces.  The ordinary raw learner
still requires three supports and the V5.20 lexical meta learner is intentionally
isolated by using three different surface geometries.
"""
from __future__ import annotations
import hashlib, json, tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v528_event_meta_bootstrap.json'


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


class NoEventBootstrapBot(Bot):
    def _observe_document_event_meta_bootstrap(self, sentences, results, source, episode_id):
        return {'status':'document_event_meta_bootstrap_ablated'}


def prepare_meta(bot: Bot) -> Bot:
    grammar='''
ana frobla caja. bruno frobla carta. cora frobla libro.
en puerto reposa ana. en plaza reposa bruno. en parque reposa cora.
lunes corresponde a ana. martes corresponde a bruno. miercoles corresponde a cora.
dora peka paquete. eva peka archivo. luis peka carpeta.
en norte duerme dora. en sur duerme eva. en centro duerme luis.
jueves asignado a dora. viernes asignado a eva. sabado asignado a luis.
alarma1 ocurre por uno. alarma2 ocurre por dos. alarma3 ocurre por tres.
'''
    g=bot.ingest_document_text(grammar,source='v528_grammar')
    assert g['relations_promoted']==7, g
    fam1=[('f0 frobla fo0','en fl0 reposa f0','ft0 corresponde a f0'),
          ('f1 frobla fo1','en fl1 reposa f1','ft1 corresponde a f1'),
          ('f2 frobla fo2','en fl2 reposa f2','ft2 corresponde a f2')]
    fam2=[('g0 peka go0','en gl0 duerme g0','gt0 asignado a g0'),
          ('g1 peka go1','en gl1 duerme g1','gt1 asignado a g1'),
          ('g2 peka go2','en gl2 duerme g2','gt2 asignado a g2')]
    for i,rows in enumerate(fam1):
        bot.ingest_document_text('. '.join(rows)+'.',source=f'v528_f_schema_{i}')
    r=bot.ingest_document_text(
        'fu frobla fobj. en floc reposa fu. ftime corresponde a fu. alarma ocurre por eso.',
        source='v528_f_use')
    assert r['sentence_results'][3]['status']=='document_coreference_resolved',r
    for i,rows in enumerate(fam2):
        bot.ingest_document_text('. '.join(rows)+'.',source=f'v528_g_schema_{i}')
    r=bot.ingest_document_text(
        'gu peka gobj. en gloc duerme gu. gtime asignado a gu. alarma ocurre por eso.',
        source='v528_g_use')
    assert r['sentence_results'][3]['status']=='document_coreference_resolved',r
    promoted=[m for m in bot.document_event_meta_hypotheses.values() if m.get('promoted')]
    assert len(promoted)==1,promoted
    return bot


def bootstrap_pair(bot: Bot, prefix='u'):
    r1=bot.ingest_document_text(
        f'{prefix}1 blen {prefix}o1. en {prefix}l1 drak {prefix}1. {prefix}t1 fesp a {prefix}1.',
        source=f'v528_{prefix}_1')
    r2=bot.ingest_document_text(
        f'{prefix}2 blen {prefix}o2. en {prefix}l2 drak {prefix}2. {prefix}t2 fesp a {prefix}2.',
        source=f'v528_{prefix}_2')
    return r1,r2


def main():
    before=code_hash()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        base=prepare_meta(Bot(allow_extensional_grounding=False))
        base_path=td/'base.json'; base.save(base_path)

        treatment=Bot.load(base_path)
        first,second=bootstrap_pair(treatment,'u')
        boot=second['document_event_meta_bootstrap']
        learned=[x for x in boot.get('relations',[]) if not x.get('existing')]
        treatment_path=td/'treatment.json'; treatment.save(treatment_path)

        control=NoEventBootstrapBot.load(base_path)
        c1,c2=bootstrap_pair(control,'c')
        control_new=[p for p in control.raw_relation_promotions.values()
                     if p.get('surface') in ('{s0} blen {s1}','en {s0} drak {s1}','{s0} fesp a {s1}')]
        control_path=td/'control.json'; control.save(control_path)

        heldout=0; times=[]; mechanism_hits=0
        for i in range(100):
            trial=Bot.load(treatment_path)
            t0=perf_counter()
            r=trial.ingest_document_text(
                f'n{i} blen o{i}. en l{i} drak n{i}. t{i} fesp a n{i}. sirena{i} ocurre por eso.',
                source=f'v528_heldout_{i}')
            times.append((perf_counter()-t0)*1000)
            row=r['sentence_results'][3]
            if row.get('status')=='document_coreference_resolved':
                heldout+=1
                mechanism_hits += row['references'][0].get('criteria')==['latent_document_event_meta_v527']

        control_resolved=0
        for i in range(100):
            trial=NoEventBootstrapBot.load(control_path)
            r=trial.ingest_document_text(
                f'cn{i} blen co{i}. en cl{i} drak cn{i}. ct{i} fesp a cn{i}. cs{i} ocurre por eso.',
                source=f'v528_control_heldout_{i}')
            control_resolved += r['sentence_results'][3].get('status')=='document_coreference_resolved'

        role_mismatch_rejected=0; role_mismatch_promotions=0
        for i in range(50):
            trial=Bot.load(base_path)
            trial.ingest_document_text(
                f'a{i} blen ao{i}. en al{i} drak a{i}. at{i} fesp a a{i}.',
                source=f'v528_role_good_{i}')
            r=trial.ingest_document_text(
                f'b{i} blen bo{i}. en bl{i} drak bx{i}. bt{i} fesp a by{i}.',
                source=f'v528_role_bad_{i}')
            role_mismatch_rejected += r['document_event_meta_bootstrap'].get('status')!='document_event_meta_bootstrap_learned'
            role_mismatch_promotions += sum(bool(p.get('event_meta_bootstrapped')) for p in trial.raw_relation_promotions.values())

        duplicate=Bot.load(base_path)
        duplicate_text='dup blen obj. en loc drak dup. time fesp a dup.'
        duplicate.ingest_document_text(duplicate_text,source='dup_a')
        duplicate_statuses=[]
        for i in range(5):
            r=duplicate.ingest_document_text(duplicate_text,source=f'dup_{i}')
            duplicate_statuses.append(r['document_event_meta_bootstrap'].get('status'))
        duplicate_promotions=sum(bool(p.get('event_meta_bootstrapped')) for p in duplicate.raw_relation_promotions.values())

    after=code_hash()
    report={
      'version':'0.5.28','experiment':'event_topology_accelerated_raw_acquisition',
      'code_hash_before':before,
      'learned':{
        'first_episode_bootstrap_status':first['document_event_meta_bootstrap'].get('status'),
        'second_episode_bootstrap_status':boot.get('status'),
        'new_relations_bootstrapped':len(learned),
        'all_new_relation_support_two':len(learned)==3 and all(
            next(p for p in treatment.raw_relation_promotions.values() if p.get('predicate')==x['predicate']).get('support')==2
            for x in learned),
        'heldout_events_resolved':heldout,'heldout_cases':100,
        'heldout_meta_event_mechanism_hits':mechanism_hits,
        'median_document_ms':median(times),
      },
      'controls':{
        'ordinary_learner_relations_after_two_episodes':len(control_new),
        'ordinary_learner_heldout_events_resolved':control_resolved,
        'ordinary_learner_heldout_cases':100,
        'role_mismatch_rejected':role_mismatch_rejected,'role_mismatch_cases':50,
        'role_mismatch_bootstrap_promotions':role_mismatch_promotions,
        'same_content_reingestion_bootstrap_promotions':duplicate_promotions,
        'same_content_reingestion_statuses':duplicate_statuses,
      },
      'code_hash_after':after,'code_unchanged_during_evaluation':before==after,
    }
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

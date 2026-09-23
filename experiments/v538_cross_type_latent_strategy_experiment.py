"""V5.38 frozen experiment: cross-type proposal strategy for unseen latent bundles."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v538_cross_type_latent_strategy.json'
BINARIES=('evone','evtwo','stone','sttwo','ruido','zeta','conecta','activa','observa')


def core_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def teach_binary(bot,name,prefix):
    for suffix in ('a','b','c'):
        bot.respond(f'{prefix}{suffix} {name} {prefix}x{suffix}')


def ground(bot):
    for i,name in enumerate(BINARIES):
        teach_binary(bot,name,f'g{i}')
    learned=None
    for text in ('ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora'):
        learned=bot.respond(text)
    assert learned['status']=='raw_relation_learned' and learned['arity']==3


def train_event(bot):
    for i in range(3):
        bot.ingest_document_text(f'e{i} evone eo{i}. e{i} evtwo el{i}.',source=f'v538_event_train_{i}')
    r=bot.ingest_document_text('eu evone eobj. eu evtwo eloc. Eso activa ealarm.',source='v538_event_use')
    assert r['sentence_results'][-1]['references'][0]['criteria']==['latent_document_event_v525']


def train_state(bot):
    for i in range(3):
        bot.ingest_document_text(
            f's{i} stone sx{i}. n{i} ruido m{i}. s{i} sttwo sy{i}.',source=f'v538_state_train_{i}')
    r=bot.ingest_document_text('su stone sx. n ruido m. su sttwo sy. Eso activa salarm.',source='v538_state_use')
    assert r['sentence_results'][-1]['references'][0]['criteria']==['latent_document_state_v535']


def prepare(two=True):
    b=Bot(allow_extensional_grounding=False);ground(b);train_event(b)
    if two:train_state(b)
    return b


def target(bot,i,consumer='activa',source_prefix='v538_target'):
    p=f't{i:04d}'
    return bot.ingest_document_text(
        f'{p} zeta {p}shared. {p}shared entrega {p}caja a {p}luis. '
        f'Eso {consumer} {p}alarm.',source=f'{source_prefix}_{i}')


def ambiguous(bot,i):
    p=f'a{i:04d}'
    return bot.ingest_document_text(
        f'{p}x zeta {p}y. {p}y entrega {p}c a {p}d. {p}d conecta {p}e. '
        f'Eso activa {p}alarm.',source=f'v538_ambiguous_{i}')


def main():
    before=core_hash();base=prepare(True);one=prepare(False)
    promoted=[x for x in base.document_latent_strategy_hypotheses.values() if x.get('promoted')]
    assert len(promoted)==1 and promoted[0]['support']==2
    assert promoted[0]['source_families']==['event','state']

    treatment=0;ablation=0;one_source=0;wrong_consumer=0;ambiguities=0
    for i in range(100):
        bt=copy.deepcopy(base);r=target(bt,i);row=r['sentence_results'][-1]
        evidence=row.get('references',[{}])[0].get('evidence',[{}])[0]
        bundle=evidence.get('bundle_candidate') or {}
        arities=[]
        for fid in bundle.get('member_fact_ids') or []:
            fact=bt.kb.get_fact(fid)
            if fact is not None: arities.append(len(fact['atom'].args))
        treatment += (row['status']=='document_coreference_resolved' and
                      row.get('references',[{}])[0].get('criteria')==['latent_document_bundle_meta_v538'] and
                      sorted(arities)==[2,3] and r['document_latent_bundles_materialized']==1 and
                      r['document_events_materialized']==0 and r['document_states_materialized']==0)

        ba=copy.deepcopy(base);ba.document_latent_strategy_hypotheses={}
        ra=target(ba,1000+i,source_prefix='v538_ablation')
        ablation += (ra['sentence_results'][-1]['status']=='document_coreference_unresolved' and
                     ra['document_latent_bundles_materialized']==0)

        bo=copy.deepcopy(one);ro=target(bo,2000+i,source_prefix='v538_one_source')
        one_source += ro['sentence_results'][-1]['status']=='document_coreference_unresolved'

        bw=copy.deepcopy(base);rw=target(bw,3000+i,consumer='observa',source_prefix='v538_wrong_consumer')
        wrong_consumer += rw['sentence_results'][-1]['status']=='document_coreference_unresolved'

    for i in range(50):
        bb=copy.deepcopy(base);r=ambiguous(bb,i);row=r['sentence_results'][-1]
        bundles=[e for rows in (row.get('candidate_evidence') or {}).values() for e in rows if e.get('bundle_candidate')]
        ambiguities += (row['status']=='document_coreference_ambiguous' and len(bundles)==2 and
                        r['document_latent_bundles_materialized']==0)

    noncredit=copy.deepcopy(base)
    policy=next(x for x in noncredit.document_latent_strategy_hypotheses.values() if x.get('promoted'))
    support_before=policy['support'];sources_before=len(policy['source_representations'])
    # One transfer is enough to test non-crediting without letting repeated target
    # documents legitimately promote an exact event schema of their own.
    target(noncredit,9000,source_prefix='v538_noncredit')
    policy=next(x for x in noncredit.document_latent_strategy_hypotheses.values() if x.get('promoted'))
    support_after=policy['support'];sources_after=len(policy['source_representations'])

    after=core_hash();assert before==after
    assert treatment==100 and ablation==100 and one_source==100 and wrong_consumer==100 and ambiguities==50
    assert (support_before,sources_before)==(support_after,sources_after)==(2,2)
    report={
      'version':'0.5.38','experiment':'cross_type_latent_representation_proposal_strategy',
      'code_hash':before,'code_frozen':True,
      'training':{'source_representation_families':['event','state'],'source_family_count':2,
                  'common_constraints':promoted[0]['constraints'],'consumer_role_bound':True},
      'treatment':{'heldout_cases':100,'first_episode_generic_bundle_resolved':treatment,
                   'target_member_arities':[2,3],'target_type_seen_in_sources':False},
      'v537_ablation_without_cross_type_strategy':{'heldout_cases':100,'unresolved':ablation},
      'one_source_family_control':{'heldout_cases':100,'unresolved':one_source},
      'wrong_consumer_control':{'heldout_cases':100,'unresolved':wrong_consumer},
      'ambiguity_control':{'cases':50,'two_candidate_abstentions':ambiguities},
      'non_circular_credit_control':{'support_before':support_before,'support_after':support_after,
                                     'source_records_before':sources_before,'source_records_after':sources_after},
      'claim':'successful exact event and persistent-state uses can teach a family-neutral connected multi-fact proposal policy; that policy transfers once to a structurally compatible binary+ternary target bundle unseen as a representation family. This is bounded learned proposal transfer, not arbitrary ontology invention or AGI/ASI.'
    }
    RESULT.parent.mkdir(exist_ok=True);RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

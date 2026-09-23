"""V5.39 frozen experiment: future evidence retracts a wrong generic latent proposal."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from experiments.v538_cross_type_latent_strategy_experiment import prepare

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v539_generic_latent_counterevidence.json'


def core_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def surprise(bot,i,prefix='v539_surprise'):
    p=f's{i:04d}'
    return bot.ingest_document_text(
        f'{p} zeta {p}shared. {p}shared entrega {p}caja a {p}luis. '
        f'Eso activa {p}alarm. {p} activa {p}alarm.',source=f'{prefix}_{i}')


def later(bot,i,prefix='v539_later'):
    p=f'l{i:04d}'
    return bot.ingest_document_text(
        f'{p} zeta {p}shared. {p}shared entrega {p}caja a {p}luis. '
        f'Eso activa {p}alarm.',source=f'{prefix}_{i}')


def main():
    before=core_hash();base=prepare(True)
    policies=[p for p in base.document_latent_strategy_hypotheses.values() if p.get('promoted')]
    assert len(policies)==1 and policies[0]['support']==2

    treatment=0;retracted=0;removed_nodes=0;ablation_repeat=0;unrelated_safe=0
    for i in range(100):
        bt=copy.deepcopy(base)
        rs=surprise(bt,i);first=rs['sentence_results'][2]
        bid=first.get('references',[{}])[0].get('antecedent');wrong_id=first.get('id')
        policy=next(iter(bt.document_latent_strategy_hypotheses.values()))
        events=[a for a in bt.kb.audit if a.get('event')=='document_latent_strategy_counterexample']
        retracted += (bt.kb.get_fact(wrong_id) is None and bool(events))
        removed_nodes += (bid is not None and bt._facts_referencing_entity(bid)==[])
        rl=later(bt,i)
        treatment += (policy.get('contested') is True and policy.get('promoted') is False and
                      rl['sentence_results'][-1]['status']=='document_coreference_unresolved' and
                      rl['document_latent_bundles_materialized']==0)

        ba=copy.deepcopy(base)
        ba._record_document_latent_bundle_confirmation=lambda *args,**kwargs: None
        surprise(ba,1000+i,'v539_ablation_surprise')
        ra=later(ba,1000+i,'v539_ablation_later')
        policy_a=next(iter(ba.document_latent_strategy_hypotheses.values()))
        ablation_repeat += (policy_a.get('promoted') is True and not policy_a.get('contested') and
                            ra['sentence_results'][-1]['status']=='document_coreference_resolved' and
                            ra['sentence_results'][-1].get('references',[{}])[0].get('criteria')==
                            ['latent_document_bundle_meta_v538'])

    for i in range(50):
        bu=copy.deepcopy(base);p=f'u{i:04d}'
        r=bu.ingest_document_text(
            f'{p} zeta {p}shared. {p}shared entrega {p}caja a {p}luis. '
            f'Eso activa {p}alarm. {p} observa {p}other.',source=f'v539_unrelated_{i}')
        policy=next(iter(bu.document_latent_strategy_hypotheses.values()))
        unrelated_safe += (r['sentence_results'][2]['status']=='document_coreference_resolved' and
                           policy.get('promoted') and not policy.get('contested'))

    after=core_hash();assert before==after
    assert treatment==100 and retracted==100 and removed_nodes==100 and ablation_repeat==100 and unrelated_safe==50
    report={
      'version':'0.5.39','experiment':'future_counterevidence_for_cross_type_latent_strategy',
      'code_hash':before,'code_frozen':True,
      'treatment':{'episodes':100,'wrong_downstream_facts_retracted':retracted,
                   'orphan_latent_nodes_removed':removed_nodes,
                   'later_equivalent_cases_abstained':treatment},
      'ablation_without_v539_confirmation':{'episodes':100,'later_wrong_generic_transfers_repeated':ablation_repeat},
      'unrelated_future_fact_control':{'cases':50,'policy_remained_active':unrelated_safe},
      'credit_rule':'only a later explicit non-coreference assertion matching predicate and all undisputed arguments can contest the V5.38 consumer strategy; generic transfers themselves never add strategy support',
      'claim':'future explicit evidence can autonomously retract a wrong generic latent-bundle consequence and withdraw the concrete cross-type consumer policy before the next equivalent case. This is bounded counterevidence-driven strategy revision, not general self-correction or AGI/ASI.'
    }
    RESULT.parent.mkdir(exist_ok=True);RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

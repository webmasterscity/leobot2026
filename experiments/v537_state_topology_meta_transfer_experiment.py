"""V5.37 frozen experiment: predicate-disjoint meta-transfer of latent persistence."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v537_state_topology_meta_transfer.json'
RELS=('palpha','qbeta','rdelta','sepsilon','zeta','kora','ruido','activa')

def core_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def ground(b):
    lines=[]
    for j,n in enumerate(RELS):
        lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
    r=b.ingest_document_text(' '.join(lines),source='v537_grammar')
    assert r['relations_promoted']==len(RELS)

def train_family(b,p,q,prefix):
    for i in range(3):
        b.ingest_document_text(
            f'{prefix}{i} {p} {prefix}x{i}. {prefix}n{i} ruido {prefix}m{i}. '
            f'{prefix}{i} {q} {prefix}y{i}.',source=f'v537_{prefix}_train_{i}')

def use_family(b,p,q,prefix):
    r=b.ingest_document_text(
        f'{prefix}u {p} {prefix}x. {prefix}n ruido {prefix}m. '
        f'{prefix}u {q} {prefix}y. Eso activa {prefix}alarm.',source=f'v537_{prefix}_use')
    assert r['sentence_results'][-1]['references'][0]['criteria']==['latent_document_state_v535']

def prepare(two=True):
    b=Bot(allow_extensional_grounding=False);ground(b)
    train_family(b,'palpha','qbeta','a');use_family(b,'palpha','qbeta','a')
    if two:
        train_family(b,'rdelta','sepsilon','b');use_family(b,'rdelta','sepsilon','b')
    return b

def target(b,i,source_prefix='v537_target'):
    p=f't{i:04d}'
    return b.ingest_document_text(
        f'{p} zeta {p}obj. {p}n ruido {p}m. {p} kora {p}val. Eso activa {p}alarm.',
        source=f'{source_prefix}_{i}')

def wrong_role(b,i):
    p=f'w{i:04d}'
    return b.ingest_document_text(
        f'{p}obj zeta {p}. {p}n ruido {p}m. {p}val kora {p}. Eso activa {p}alarm.',
        source=f'v537_wrong_role_{i}')

def main():
    before=core_hash();base=prepare(True);one=prepare(False)
    metas=[s for s in base.document_state_meta_hypotheses.values() if s.get('promoted')]
    gates=[g for g in base.document_state_meta_reference_hypotheses.values() if g.get('promoted')]
    assert len(metas)==1 and metas[0]['support']==2
    assert len(gates)==1 and gates[0]['support']==2

    treatment=0;ablation=0;one_source=0;wrong=0
    for i in range(100):
        bt=copy.deepcopy(base);r=target(bt,i);row=r['sentence_results'][-1]
        exact_promoted=sum(1 for s in bt.document_state_schema_hypotheses.values() if s.get('promoted'))
        treatment += (row['status']=='document_coreference_resolved' and
                      row.get('references',[{}])[0].get('criteria')==['latent_document_state_meta_v537'] and
                      r['document_states_materialized']==1 and exact_promoted==2)

        ba=copy.deepcopy(base)
        ba.document_state_meta_hypotheses={};ba.document_state_meta_reference_hypotheses={}
        ra=target(ba,1000+i,'v537_ablation');
        ablation += ra['sentence_results'][-1]['status']=='document_coreference_unresolved'

        bo=copy.deepcopy(one);ro=target(bo,2000+i,'v537_one_source')
        one_source += ro['sentence_results'][-1]['status']=='document_coreference_unresolved'

    for i in range(50):
        bw=copy.deepcopy(base);rw=wrong_role(bw,i)
        wrong += (rw['sentence_results'][-1]['status']=='document_coreference_unresolved' and
                  rw['document_states_materialized']==0)

    # Direct sample-efficiency control on one target lexical family.  Without the
    # meta abstraction, V5.35 must observe three state episodes before promotion.
    exact=copy.deepcopy(base);exact.document_state_meta_hypotheses={};exact.document_state_meta_reference_hypotheses={}
    curve=[]
    for i in range(3):
        r=target(exact,3000+i,'v537_exact_curve')
        curve.append(r['sentence_results'][-1].get('status'))
    assert curve==['document_coreference_unresolved','document_coreference_unresolved','document_coreference_resolved']
    exact_last=r['sentence_results'][-1]['references'][0]['criteria']
    assert exact_last==['latent_document_state_v535']

    # Meta uses cannot boost the cross-family gate that licensed them.
    noncredit=copy.deepcopy(base)
    gate_before=next(g['support'] for g in noncredit.document_state_meta_reference_hypotheses.values() if g.get('promoted'))
    target(noncredit,4000,'v537_noncredit');target(noncredit,4001,'v537_noncredit')
    gate_after=next(g['support'] for g in noncredit.document_state_meta_reference_hypotheses.values() if g.get('promoted'))

    after=core_hash();assert before==after
    assert treatment==100 and ablation==100 and one_source==100 and wrong==50
    assert gate_before==gate_after==2
    report={
      'version':'0.5.37','experiment':'predicate_disjoint_persistent_state_topology_meta_transfer',
      'code_hash':before,'code_frozen':True,
      'training':{'source_families':2,'predicate_disjoint':True,'real_downstream_uses_per_family':1,
                  'meta_topologies_promoted':len(metas),'meta_support':metas[0]['support'],
                  'consumer_gate_support':gates[0]['support']},
      'treatment':{'heldout_cases':100,'third_family_first_episode_meta_resolved':treatment,
                   'exact_state_schemas_still_promoted':2},
      'v535_ablation_without_meta_transfer':{'heldout_cases':100,'first_episode_unresolved':ablation,
                                             'same_family_learning_curve':curve,
                                             'first_exact_resolution_episode':3},
      'one_source_family_control':{'heldout_cases':100,'unresolved':one_source},
      'carrier_role_change_control':{'cases':50,'unresolved':wrong},
      'non_circular_credit_control':{'meta_gate_support_before':gate_before,'after_two_meta_uses':gate_after},
      'claim':'two predicate-disjoint, actually used exact persistence schemas can teach a lexical-identity-free persistence topology that transfers to a third unseen predicate family in one state episode; bounded structural meta-transfer, not unrestricted representation invention or AGI/ASI'
    }
    RESULT.parent.mkdir(exist_ok=True);RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

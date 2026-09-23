"""V5.35 frozen experiment: infer a persistent latent state without an input predicate naming it."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v535_latent_persistent_state.json'
RELS=('palpha','qbeta','ruido','activa')

def core_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()

def ground(b):
    lines=[]
    for j,n in enumerate(RELS):
        lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
    r=b.ingest_document_text(' '.join(lines),source='v535_grammar')
    assert r['relations_promoted']==len(RELS)

def prepare():
    b=Bot(allow_extensional_grounding=False);ground(b)
    for i in range(3):
        b.ingest_document_text(
            f'a{i} palpha x{i}. n{i} ruido m{i}. a{i} qbeta y{i}.',
            source=f'v535_train_{i}')
    promoted=[s for s in b.document_state_schema_hypotheses.values() if s.get('promoted')]
    assert len(promoted)==1 and promoted[0]['support']==3
    assert not any(s.get('promoted') for s in b.document_event_schema_hypotheses.values())
    return b

def target(b,i):
    prefix=f'h{i:03d}';noise_count=1+(i%5)
    middle=' '.join(f'{prefix}n{j} ruido {prefix}m{j}.' for j in range(noise_count))
    return b.ingest_document_text(
        f'{prefix} palpha {prefix}x. {middle} {prefix} qbeta {prefix}y. Eso activa {prefix}alarm.',
        source=f'v535_target_{i}')

def ambiguous(b,i):
    p=f'a{i:03d}';q=f'b{i:03d}'
    return b.ingest_document_text(
        f'{p} palpha {p}x. {p}n ruido {p}m. {p} qbeta {p}y. '
        f'{q} palpha {q}x. {q}n ruido {q}m. {q} qbeta {q}y. Eso activa alarm{i}.',
        source=f'v535_amb_{i}')

def main():
    before=core_hash();base=prepare()
    treatment=ablation=ambiguity=0
    max_event=0;max_dep=0
    for i in range(100):
        bt=copy.deepcopy(base);r=target(bt,i);row=r['sentence_results'][-1]
        ok=(row['status']=='document_coreference_resolved' and
            row.get('references',[{}])[0].get('criteria')==['latent_document_state_v535'] and
            r['document_states_materialized']==1)
        treatment += ok
        max_event=max(max_event,r['document_events_materialized'])
        max_dep=max(max_dep,r['document_dependencies_materialized'])

        ba=copy.deepcopy(base);ba._document_state_candidates=lambda facts: []
        ra=target(ba,1000+i);rowa=ra['sentence_results'][-1]
        ablation += rowa['status']=='document_coreference_unresolved'

    for i in range(50):
        bx=copy.deepcopy(base);rx=ambiguous(bx,i);rowx=rx['sentence_results'][-1]
        ambiguity += rowx['status']=='document_coreference_ambiguous' and rx['document_states_materialized']==0
    after=core_hash();assert before==after
    assert treatment==100 and ablation==100 and ambiguity==50 and max_event==0 and max_dep==0
    report={
        'version':'0.5.35','experiment':'latent_persistent_state_without_named_internal_relation',
        'code_hash':before,'code_frozen':True,
        'training':{'independent_documents':3,'input_predicate_naming_state':False,
                    'promoted_state_schemas':1,'promoted_event_schemas':0},
        'treatment':{'heldout_cases':100,'state_resolved':treatment,
                     'event_materializations_max':max_event,'dependency_materializations_max':max_dep,
                     'intervening_noise_sentences':'1..5'},
        'v534_ablation_without_state_generator':{'heldout_cases':100,'unresolved':ablation},
        'ambiguity_control':{'cases':50,'safe_ambiguity':ambiguity,'state_materializations':0},
        'claim':'a non-contiguous recurrent role can induce a demand-driven persistent-state representation without an explicit input predicate naming that state; bounded exact-schema result, not open ontology invention or AGI/ASI'
    }
    RESULT.parent.mkdir(exist_ok=True);RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

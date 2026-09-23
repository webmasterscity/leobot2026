"""V5.33 frozen experiment: event vs explicit-causal representation types."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v533_representation_type.json'
EVENT=(('epa','eqa'),('epb','eqb'))
CAUSAL=(('c0a','c0b'),('c1a','c1b'),('c2a','c2b'),('c3a','c3b'))
TARGET=('tpa','tpb')

def core_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(path.read_bytes())
    return h.hexdigest()

def relations():
    return tuple(x for fam in EVENT+CAUSAL for x in fam)+TARGET+('activa',)

def ground(b):
    lines=[]
    for j,n in enumerate(relations()):
        lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
    out=b.ingest_document_text(' '.join(lines),source='v533_grammar')
    assert out['relations_promoted']==len(relations())

def train_causal(b,count=4):
    for i,(p,q) in enumerate(CAUSAL[:count]):
        out=b.ingest_document_text(
            f'c{i}u {p} cx{i}. Por eso, c{i}u {q} cy{i}. Eso activa ca{i}.',
            source=f'v533_causal_{i}')
        assert out['sentence_results'][-1]['references'][0]['criteria']==['latent_document_causal_v533']

def train_events(b):
    for fi,(p,q) in enumerate(EVENT):
        for i in range(3):
            b.ingest_document_text(f'e{fi}{i} {p} x{fi}{i}. e{fi}{i} {q} y{fi}{i}.',source=f'v533_event_{fi}_{i}')
        out=b.ingest_document_text(f'e{fi}u {p} xo{fi}. e{fi}u {q} yo{fi}. Eso activa ea{fi}.',source=f'v533_event_use_{fi}')
        assert out['sentence_results'][-1]['status']=='document_coreference_resolved'

def prepare(causal_count=4):
    b=Bot(allow_extensional_grounding=False);ground(b);train_causal(b,causal_count);train_events(b);return b

def target(b,i):
    p,q=TARGET;prefix=f'h{i:03d}'
    return b.ingest_document_text(
        f'{prefix} {p} {prefix}obj. Por eso, {prefix} {q} {prefix}loc. Eso activa {prefix}alarm.',
        source=f'v533_target_{i}')

def main():
    before=core_hash()
    treatment=prepare(4)
    tie=prepare(2)
    causal_wins=event_wins=ablation_event_wins=tie_ambiguous=0
    for i in range(100):
        bt=copy.deepcopy(treatment)
        ba=copy.deepcopy(treatment)
        ba._document_dependency_candidates=lambda facts: []
        rt=target(bt,i);ra=target(ba,1000+i)
        ct=rt['sentence_results'][-1]['references'][0]['criteria']
        ca=ra['sentence_results'][-1]['references'][0]['criteria']
        causal_wins += ct==['latent_document_causal_v533']
        event_wins += any(x.startswith('latent_document_event') for x in ct)
        ablation_event_wins += any(x.startswith('latent_document_event') for x in ca)
        be=copy.deepcopy(tie);rr=target(be,2000+i)
        tie_ambiguous += rr['sentence_results'][-1]['status']=='document_coreference_ambiguous' and rr['document_events_materialized']==0 and rr['document_causal_dependencies_materialized']==0
    after=core_hash();assert before==after
    assert causal_wins==100 and event_wins==0 and ablation_event_wins==100 and tie_ambiguous==100
    report={'version':'0.5.33','experiment':'representation_type_competition_event_vs_explicit_causal',
            'code_hash':before,'code_frozen':True,
            'treatment':{'heldout_cases':100,'causal_dependency_selected':causal_wins,'event_selected':event_wins,
                         'prior_support':{'causal_dependency':4,'event':2}},
            'event_only_ablation':{'heldout_cases':100,'event_selected':ablation_event_wins},
            'equal_support_control':{'heldout_cases':100,'safe_ambiguity':tie_ambiguous},
            'noncausal_connective_control':'covered by tests/test_v533.py: luego never creates a causal candidate',
            'claim':'competition between two qualitatively different representation types using prior non-circular predictive utility; not AGI/ASI'}
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()

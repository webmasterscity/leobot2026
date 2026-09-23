"""V5.36 frozen experiment: latent persistent state competes with an event by prior utility."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v536_latent_state_competition.json'
RELS=('palpha','qbeta','ruido','rgamma','activa')

def core_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()

def ground(b):
    lines=[]
    for j,n in enumerate(RELS):
        lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
    assert b.ingest_document_text(' '.join(lines),source='v536_grammar')['relations_promoted']==len(RELS)

def prepare(state_uses,event_uses):
    b=Bot(allow_extensional_grounding=False);ground(b)
    for i in range(3):
        b.ingest_document_text(f's{i} palpha sx{i}. sn{i} ruido sm{i}. s{i} qbeta sy{i}.',source=f'v536_state_train_{i}')
    for i in range(state_uses):
        out=b.ingest_document_text(
            f'su{i} palpha ux{i}. un{i} ruido um{i}. su{i} qbeta uy{i}. Eso activa sa{i}.',
            source=f'v536_state_use_{i}')
        assert out['sentence_results'][-1]['references'][0]['criteria']==['latent_document_state_v535']
    for i in range(3):
        b.ingest_document_text(f'e{i} qbeta ey{i}. ey{i} rgamma ez{i}.',source=f'v536_event_train_{i}')
    for i in range(event_uses):
        out=b.ingest_document_text(
            f'eu{i} qbeta eyy{i}. eyy{i} rgamma ezz{i}. Eso activa ea{i}.',
            source=f'v536_event_use_{i}')
        assert out['sentence_results'][-1]['references'][0]['criteria']==['latent_document_event_v525']
    return b

def target(b,i,offset=0):
    p=f'h{i+offset:04d}'
    return b.ingest_document_text(
        f'{p} palpha {p}x. {p}n ruido {p}m. {p} qbeta {p}y. '
        f'{p}y rgamma {p}z. Eso activa {p}alarm.',source=f'v536_target_{i+offset}')

def main():
    before=core_hash();base=prepare(4,2);tie=prepare(2,2);low=prepare(1,2)
    state_wins=event_wins_ablation=ties=low_event=0
    for i in range(100):
        bt=copy.deepcopy(base);r=target(bt,i);row=r['sentence_results'][-1]
        state_wins += (row['status']=='document_coreference_resolved' and
                       row.get('references',[{}])[0].get('criteria')==['latent_document_state_v535'] and
                       r['document_states_materialized']==1 and r['document_events_materialized']==0)

        ba=copy.deepcopy(base);ba._document_state_candidates=lambda facts: []
        ra=target(ba,i,1000);rowa=ra['sentence_results'][-1]
        event_wins_ablation += (rowa['status']=='document_coreference_resolved' and
                                rowa.get('references',[{}])[0].get('criteria')==['latent_document_event_v525'])

        bx=copy.deepcopy(tie);rx=target(bx,i,2000);rowx=rx['sentence_results'][-1]
        ties += (rowx['status']=='document_coreference_ambiguous' and
                 rx['document_states_materialized']==0 and rx['document_events_materialized']==0)

        bl=copy.deepcopy(low);rl=target(bl,i,3000);rowl=rl['sentence_results'][-1]
        low_event += (rowl['status']=='document_coreference_resolved' and
                      rowl.get('references',[{}])[0].get('criteria')==['latent_document_event_v525'])
    after=core_hash();assert before==after
    assert state_wins==100 and event_wins_ablation==100 and ties==100 and low_event==100
    report={
        'version':'0.5.36','experiment':'latent_state_vs_event_predictive_competition',
        'code_hash':before,'code_frozen':True,
        'treatment':{'heldout_cases':100,'prior_support':{'latent_persistent_state':4,'event':2},
                     'state_selected':state_wins,'event_selected':0},
        'v534_ablation_without_state_generator':{'heldout_cases':100,'event_selected':event_wins_ablation},
        'equal_support_control':{'heldout_cases':100,'support':{'state':2,'event':2},'safe_ambiguity':ties},
        'under_supported_state_control':{'heldout_cases':100,'support':{'state':1,'event':2},'event_selected':low_event},
        'claim':'a representation induced without an input state predicate can compete against an event using independent downstream utility; bounded exact state schema, not unrestricted ontology invention or AGI/ASI'
    }
    RESULT.parent.mkdir(exist_ok=True);RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

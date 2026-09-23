"""V5.34 frozen experiment: generated explicit document-dependency types compete with events."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v534_generated_representation_types.json'
CAUSAL=(('caa','cab'),('cba','cbb'))
TEMPORAL=(('taa','tab'),('tba','tbb'),('tca','tcb'),('tda','tdb'))
EVENT=(('epa','eqa','era'),('epb','eqb','erb'))
TARGET=('npa','nqa','nra')

def core_hash():
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(path.read_bytes())
    return h.hexdigest()

def relations():
    return tuple(x for fam in CAUSAL+TEMPORAL+EVENT for x in fam)+TARGET+('activa',)

def ground(b):
    lines=[]
    for j,n in enumerate(relations()):
        lines += [f'g{j}a {n} h{j}a.',f'g{j}b {n} h{j}b.',f'g{j}c {n} h{j}c.']
    out=b.ingest_document_text(' '.join(lines),source='v534_grammar')
    assert out['relations_promoted']==len(relations())

def use_dependency(b,names,prefix,temporal):
    p,q=names;connector='Luego' if temporal else 'Por eso'
    out=b.ingest_document_text(
        f'{prefix} {p} {prefix}x. {connector}, {prefix} {q} {prefix}y. Eso activa {prefix}alarm.',
        source=f'v534_dep_{prefix}')
    assert out['sentence_results'][-1]['status']=='document_coreference_resolved'

def train_dependencies(b):
    for i,fam in enumerate(CAUSAL): use_dependency(b,fam,f'C{i}',False)
    for i,fam in enumerate(TEMPORAL): use_dependency(b,fam,f'T{i}',True)

def train_events(b):
    for fi,(p,q,r) in enumerate(EVENT):
        for i in range(3):
            b.ingest_document_text(
                f'E{fi}{i} {p} E{fi}x{i}. E{fi}{i} {q} E{fi}y{i}. E{fi}x{i} {r} E{fi}z{i}.',
                source=f'v534_event_train_{fi}_{i}')
        out=b.ingest_document_text(
            f'E{fi}u {p} E{fi}obj. E{fi}u {q} E{fi}loc. E{fi}obj {r} E{fi}time. Eso activa E{fi}alarm.',
            source=f'v534_event_use_{fi}')
        assert out['sentence_results'][-1]['status']=='document_coreference_resolved'

def prepare():
    b=Bot(allow_extensional_grounding=False);ground(b);train_dependencies(b);train_events(b);return b

def target(b,i):
    p,q,r=TARGET;prefix=f'h{i:03d}'
    return b.ingest_document_text(
        f'{prefix} {p} {prefix}obj. Por eso, {prefix} {q} {prefix}loc. '
        f'Luego, {prefix}obj {r} {prefix}time. Eso activa {prefix}alarm.',
        source=f'v534_target_{i}')

def prepare_tie():
    b=Bot(allow_extensional_grounding=False);ground(b)
    for i,fam in enumerate(CAUSAL): use_dependency(b,fam,f'EC{i}',False)
    for i,fam in enumerate(TEMPORAL[:2]): use_dependency(b,fam,f'ET{i}',True)
    return b

def main():
    before=core_hash();base=prepare();tie=prepare_tie()
    temporal=event=causal_only_same=event_only=ties=0
    for i in range(100):
        bt=copy.deepcopy(base);r=target(bt,i);row=r['sentence_results'][-1]
        crit=row['references'][0]['criteria'] if row.get('references') else []
        if crit==['latent_document_dependency_v534']:
            dep=row['references'][0]['evidence'][0]['dependency_candidate']
            temporal += dep.get('link_predicate')=='_doc_precedes'
        event += any(x.startswith('latent_document_event') for x in crit)

        bc=copy.deepcopy(base)
        original=bc._document_dependency_candidates
        bc._document_dependency_candidates=lambda facts,orig=original:[x for x in orig(facts) if x.get('link_predicate')=='_doc_causes']
        rc=target(bc,1000+i);rowc=rc['sentence_results'][-1]
        causal_only_same += (rowc['status']=='document_coreference_resolved' and rowc.get('references',[{}])[0].get('criteria')==['latent_document_dependency_v534'])

        be=copy.deepcopy(base);be._document_dependency_candidates=lambda facts: []
        re=target(be,2000+i);rowe=re['sentence_results'][-1]
        event_only += rowe['status']=='document_coreference_resolved' and any(x.startswith('latent_document_event') for x in rowe['references'][0]['criteria'])

        bx=copy.deepcopy(tie);rx=target(bx,3000+i);rowx=rx['sentence_results'][-1]
        ties += rowx['status']=='document_coreference_ambiguous' and rx['document_events_materialized']==0 and rx['document_dependencies_materialized']==0
    after=core_hash();assert before==after
    assert temporal==100 and event==0 and causal_only_same==0 and event_only==100 and ties==100
    report={
        'version':'0.5.34','experiment':'generated_document_dependency_representation_types',
        'code_hash':before,'code_frozen':True,
        'treatment':{'heldout_cases':100,'temporal_dependency_selected':temporal,'event_selected':event,
                     'prior_support':{'document_dependency:_doc_precedes':4,'document_dependency:_doc_causes':2,'event':2}},
        'causal_only_v533_ablation':{'heldout_cases':100,'selected_same_temporal_type':causal_only_same},
        'event_only_v532_ablation':{'heldout_cases':100,'event_selected':event_only},
        'equal_best_dependency_control':{'heldout_cases':100,'safe_ambiguity':ties},
        'safety':'only _doc_* atoms with document_discourse_v524 provenance can generate dependency types',
        'claim':'generic reification/competition of explicit document dependency types plus events; not autonomous arbitrary ontology invention and not AGI/ASI'}
    RESULT.parent.mkdir(exist_ok=True);RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

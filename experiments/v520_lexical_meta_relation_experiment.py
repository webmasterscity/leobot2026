from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()


TRAIN='''
a1 frobla b1.
a2 frobla b2.
a3 frobla b3.
c1 norga d1.
c2 norga d2.
c3 norga d3.
e1 kima f1.
e2 kima f2.
e3 kima f3.
'''
CONTROL='''
a1 frobla b1.
a2 frobla b2.
a3 frobla b3.
c1 norga d1.
c2 norga d2.
c3 norga d3.
'''


def main():
    frozen=code_hash(); start=time.perf_counter()
    treatment=Bot(allow_extensional_grounding=False)
    ttrain=treatment.ingest_document_text(TRAIN,source='meta_train')
    frames=treatment._raw_lexical_meta_frames()
    assert ttrain['relations_promoted']==3 and len(frames)==1 and frames[0]['support']==3
    stored=queries=0
    for i in range(100):
        report=treatment.ingest_document_text(f'x{i} rel{i} y{i}.',source=f'one_{i}')
        row=report['sentence_results'][0]
        if row.get('status')=='raw_relation_meta_transferred' and report['facts_added']==1:
            stored+=1
        if treatment.respond(f'¿x{i} rel{i} y{i}?').get('status')=='supported':
            queries+=1
    support_after=treatment._raw_lexical_meta_frames()[0]['support']

    control=Bot(allow_extensional_grounding=False)
    control.ingest_document_text(CONTROL,source='meta_control')
    control_stored=control_queries=0
    for i in range(100):
        report=control.ingest_document_text(f'x{i} rel{i} y{i}.',source=f'one_{i}')
        control_stored += int(report['facts_added']>0)
        control_queries += int(control.respond(f'¿x{i} rel{i} y{i}?').get('status')=='supported')

    # Each ambiguity probe uses an equivalent fresh learner. Repeating fifty
    # similarly shaped ambiguous sentences in one learner would legitimately
    # become new anti-unification evidence and answer a different question.
    ambiguous=0
    for i in range(50):
        probe=Bot(allow_extensional_grounding=False)
        probe.ingest_document_text(TRAIN,source='meta_train')
        before=probe.kb.stats()['facts']
        report=probe.ingest_document_text(f'equipo {i} amb{i} modulo azul{i}.',source=f'amb_{i}')
        if report['facts_added']==0 and probe.kb.stats()['facts']==before:
            ambiguous+=1

    result={
        'version':'V5.20',
        'mechanism':'non_self_amplifying_lexical_relation_meta_transfer',
        'frozen_code_sha256':frozen,
        'final_code_sha256':code_hash(),
        'direct_meta_support':frames[0]['support'],
        'treatment_one_shot_relations_stored':stored,
        'treatment_one_shot_queries_supported':queries,
        'meta_support_after_100_transfers':support_after,
        'control_direct_relations':2,
        'control_one_shot_relations_stored':control_stored,
        'control_one_shot_queries_supported':control_queries,
        'ambiguous_multiword_boundaries_rejected':ambiguous,
        'elapsed_ms':round((time.perf_counter()-start)*1000,3),
    }
    assert stored==100 and queries==100 and support_after==3
    assert control_stored==0 and control_queries==0 and ambiguous==50
    assert frozen==result['final_code_sha256']
    (ROOT/'results_v3'/'v520_lexical_meta_relation.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

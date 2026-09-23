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


RULE_DOC='''
Si ana frobla caja a luis entonces ana glorp luis.
Si bea frobla libro a mario entonces bea glorp mario.
Si cora frobla mapa a nora entonces cora glorp nora.
'''


def main():
    frozen=code_hash(); start=time.perf_counter()

    treatment=Bot(allow_extensional_grounding=False)
    learned=treatment.ingest_document_text(RULE_DOC,source='rule_doc',learn_conditionals=True)
    assert learned['facts_added']==0 and learned['rules_learned']==1
    assert treatment.kb.stats()['facts']==0 and len(treatment.kb.rules)==1
    sources=[o.get('source') for o in treatment.conditional_bootstrap_observations]
    assert sources==['rule_doc:oración:1','rule_doc:oración:2','rule_doc:oración:3']

    treatment_hits=0; provenance=0
    for i in range(100):
        row=treatment.ingest_document_text(f'actor{i} frobla objeto{i} a destino{i}.',source=f'heldout_doc_{i}')
        assert row['facts_added']==1
        ans=treatment.respond(f'¿actor{i} glorp destino{i}?')
        if ans.get('status')=='hypothesis':
            treatment_hits+=1
            children=(ans.get('proofs') or [{}])[0].get('children') or []
            if children and children[0].get('source')==f'heldout_doc_{i}:oración:1':
                provenance+=1

    control=Bot(allow_extensional_grounding=False)
    skipped=control.ingest_document_text(RULE_DOC,source='rule_doc',learn_conditionals=False)
    assert skipped['conditionals_skipped']==3 and len(control.kb.rules)==0
    for i in range(100):
        control.ingest_document_text(f'actor{i} frobla objeto{i} a destino{i}.',source=f'heldout_doc_{i}')
    control_hits=sum(control.respond(f'¿actor{i} glorp destino{i}?').get('status')=='hypothesis'
                     for i in range(100))

    result={
        'version':'V5.19',
        'mechanism':'opt_in_document_hypothetical_rule_acquisition',
        'frozen_code_sha256':frozen,
        'final_code_sha256':code_hash(),
        'training_conditionals_processed':learned['conditionals_processed'],
        'training_rules_learned':learned['rules_learned'],
        'training_hypothetical_facts_added':learned['facts_added'],
        'training_sources_preserved':sources,
        'treatment_heldout_hypotheses':treatment_hits,
        'treatment_provenance_preserved':provenance,
        'control_conditionals_skipped':skipped['conditionals_skipped'],
        'control_rules_learned':len(control.kb.rules),
        'control_heldout_hypotheses':control_hits,
        'document_instruction_execution_path_used':False,
        'elapsed_ms':round((time.perf_counter()-start)*1000,3),
    }
    assert treatment_hits==100 and provenance==100
    assert control_hits==0
    assert frozen==result['final_code_sha256']
    (ROOT/'results_v3'/'v519_document_conditionals.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

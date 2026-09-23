from __future__ import annotations
import hashlib, json
from pathlib import Path
from leobot import Bot
from leobot.core import KnowledgeBase

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v58_document_freeze.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def bootstrap():
    b=Bot(KnowledgeBase(),allow_extensional_grounding=False)
    A=['persona ana enlaza modulo rojo','persona beto enlaza modulo azul','persona carla enlaza modulo verde']
    B=['modulo rojo reposa zona norte','modulo azul reposa zona sur','modulo verde reposa zona este']
    ra=[b.respond(x) for x in A]; rb=[b.respond(x) for x in B]
    assert ra[-1]['status']=='raw_relation_learned' and rb[-1]['status']=='raw_relation_learned'
    train=[
      'persona ana coordina modulo rojo en zona norte',
      'persona beto coordina modulo azul en zona sur',
      'persona ana no coordina modulo rojo en zona sur',
      'persona ana no coordina modulo azul en zona sur',
      'persona ana no coordina modulo azul en zona norte',
    ]
    rr=[b.observe_schema_statement(x) for x in train]
    assert rr[-1]['status']=='schema_learned', rr[-1]
    return b

def entailed(b,p,o,z):
    return b.query_schema(f'persona {p} coordina modulo {o} en zona {z}').get('status')=='entailed'

def main():
    h0=code_hash(); b=bootstrap()
    N=40
    sequential=paragraph=anaphora=0
    paragraph_status={}; anaphora_status={}
    # A. Same information as two ordinary utterances: should measure information acquisition itself.
    for i in range(N):
        p,o,z=f'seqp{i}',f'seqo{i}',f'seqz{i}'
        b.respond(f'persona {p} enlaza modulo {o}')
        b.respond(f'modulo {o} reposa zona {z}')
        sequential += entailed(b,p,o,z)
    # B. Same two sentences, but delivered as one natural paragraph/message.
    for i in range(N):
        p,o,z=f'parp{i}',f'paro{i}',f'parz{i}'
        r=b.respond(f'persona {p} enlaza modulo {o}. modulo {o} reposa zona {z}.')
        paragraph_status[r.get('status')]=paragraph_status.get(r.get('status'),0)+1
        paragraph += entailed(b,p,o,z)
    # C. Anaphora, still delivered sentence-by-sentence to isolate reference from segmentation.
    for i in range(N):
        p,o,z=f'anap{i}',f'anao{i}',f'anaz{i}'
        b.respond(f'persona {p} enlaza modulo {o}')
        r=b.respond(f'este reposa zona {z}')
        anaphora_status[r.get('status')]=anaphora_status.get(r.get('status'),0)+1
        anaphora += entailed(b,p,o,z)
    # D. Persistence / retention of the direct path.
    tmp=ROOT/'results_v3'/'v58_freeze_state.json'; b.save(tmp); b2=Bot.load(tmp)
    retention=sum(entailed(b2,f'seqp{i}',f'seqo{i}',f'seqz{i}') for i in range(N))
    report={
      'version':'V5.8-freeze-on-V5.7','experiment':'document_acquisition_freeze',
      'code_hash_before':h0,'code_hash_after':code_hash(),'code_unchanged':h0==code_hash(),
      'cases_per_level':N,
      'separate_sentences':{'entailed':sequential,'total':N},
      'single_paragraph_same_information':{'entailed':paragraph,'total':N,'statuses':paragraph_status},
      'anaphora_sentence_by_sentence':{'entailed':anaphora,'total':N,'statuses':anaphora_status},
      'retention_after_restart':{'entailed':retention,'total':N},
      'interpretation':{
        'segmentation_gap': sequential==N and paragraph<N,
        'reference_gap': sequential==N and anaphora<N,
      },
      'limits':['Synthetic Spanish relations; internal freeze test; no AGI/ASI claim.']
    }
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()

import json
from pathlib import Path
from leobot import Bot
from leobot.core import Atom

TRAIN='''
a1 frobla x1. a2 frobla x2. a3 frobla x3.
b1 norga y1. b2 norga y2. b3 norga y3.
'''

def main():
    b=Bot(allow_extensional_grounding=False); b.ingest_document_text(TRAIN,source='v524_train')
    temporal=causal=0
    for i in range(100):
        r=b.ingest_document_text(f'a{i} frobla x{i}. Luego b{i} norga y{i}. Por eso c{i} frobla z{i}.',source=f'v524_case_{i}')
        r1,r2,r3=r['sentence_results']
        temporal += bool(b.kb.contains(Atom('_doc_precedes',(r1['id'],r2['id']))))
        causal += bool(b.kb.contains(Atom('_doc_causes',(r2['id'],r3['id']))))
    control=0
    for i in range(50):
        r=b.ingest_document_text(f'¿a{i} frobla x{i}? Luego q{i} norga w{i}.',source=f'v524_control_{i}')
        control += r['sentence_results'][1].get('discourse_link',{}).get('status')=='document_discourse_unresolved'
    out={'temporal_links':temporal,'causal_links':causal,'missing_antecedent_abstentions':control,
         'causal_rules_invented':sum(1 for r in b.kb.rules.values() if '_doc_causes' in str(r))}
    Path('results_v3/v524_document_discourse.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(out)

if __name__=='__main__': main()

import json
from pathlib import Path
from leobot import Bot


def build():
    b=Bot(allow_extensional_grounding=False)
    b.ingest_document_text('''
a1 frobla x1. a2 frobla x2. a3 frobla x3.
b1 norga y1. b2 norga y2. b3 norga y3.
c1 tulka z1. c2 tulka z2. c3 tulka z3.
''',source='v523_train')
    for i,(obj,a,c) in enumerate([('uno','aa','bb'),('dos','cc','dd'),('tres','ee','ff')],1):
        b.ingest_document_text(f'{a} frobla {obj}. {c} norga {obj}.',source=f'v523_fn_{i}')
    for i,(obj,a,c) in enumerate([('rojo','gg','hh'),('azul','ii','jj'),('verde','kk','ll')],1):
        b.ingest_document_text(f'{a} norga {obj}. {c} tulka {obj}.',source=f'v523_nt_{i}')
    return b


def main():
    b=build(); success=0
    before={k:s.get('support') for k,s in b.document_role_bridge_hypotheses.items() if s.get('promoted')}
    for i in range(100):
        r=b.ingest_document_text(f'd{i} frobla p{i}. r{i} norga eso. z{i} tulka eso.',source=f'v523_case_{i}')
        success += (r['sentence_results'][1].get('args')==[f'r{i}',f'p{i}'] and
                    r['sentence_results'][2].get('args')==[f'z{i}',f'p{i}'])
    after={k:s.get('support') for k,s in b.document_role_bridge_hypotheses.items() if s.get('promoted')}
    ambiguous=0
    for i in range(50):
        r=b.ingest_document_text(f'a{i} frobla x{i}. b{i} frobla y{i}. c{i} norga eso. d{i} tulka eso.',source=f'v523_amb_{i}')
        ambiguous += (r['sentence_results'][2].get('status')=='document_coreference_ambiguous' and
                      r['sentence_results'][3].get('status')=='document_coreference_unresolved')
    out={'two_hop_reference_chains':success,'bridge_support_unchanged':before==after,
         'ambiguous_chain_stopped':ambiguous,'bridge_support_before':before,'bridge_support_after':after}
    Path('results_v3').mkdir(exist_ok=True)
    Path('results_v3/v523_reference_chain.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(out)

if __name__=='__main__': main()

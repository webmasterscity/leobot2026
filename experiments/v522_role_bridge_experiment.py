import json
from pathlib import Path
from leobot import Bot
from leobot.core import Atom

TRAIN='''
ana frobla caja.
bea frobla libro.
cora frobla mapa.
dario norga puerto.
eva norga nodo.
fabio norga zona.
gina tulka lima.
hugo tulka quito.
iris tulka bogota.
'''

def teach(bot,left,right,prefix):
    for i,(a,obj,b) in enumerate([('a','caja','l'),('b','libro','m'),('c','mapa','n')],1):
        bot.ingest_document_text(f'{a}{prefix}{i} {left} {obj}{prefix}{i}. {b}{prefix}{i} {right} {obj}{prefix}{i}.',source=f'{prefix}_{i}')

def main():
    bot=Bot(allow_extensional_grounding=False); bot.ingest_document_text(TRAIN,source='v522_train')
    by={p['surface']:p['predicate'] for p in bot.raw_relation_promotions.values()}; norga=by['{s0} norga {s1}']
    teach(bot,'frobla','norga','bridge')
    success=wrong=0
    for i in range(100):
        r=bot.ingest_document_text(f'x{i} frobla objetivo{i}. d{i} tulka distractor{i}. y{i} norga eso.',source=f'target_{i}')
        row=r['sentence_results'][2]
        success += row.get('status')=='document_coreference_resolved' and row.get('args')==[f'y{i}',f'objetivo{i}']
        wrong += bot.kb.contains(Atom(norga,(f'y{i}',f'distractor{i}')))
    control=Bot(allow_extensional_grounding=False); control.ingest_document_text(TRAIN,source='control_train')
    for i,(a,obj,b) in enumerate([('a','u','l'),('b','v','m')],1):
        control.ingest_document_text(f'{a}{i} frobla {obj}{i}. {b}{i} norga {obj}{i}.',source=f'control_bridge_{i}')
    control_hits=0
    for i in range(100):
        r=control.ingest_document_text(f'x{i} frobla z{i}. y{i} norga eso.',source=f'control_target_{i}')
        control_hits += r['sentence_results'][1].get('status')=='document_coreference_resolved'
    out={'cross_predicate_resolved':success,'wrong_distractor_facts':wrong,
         'two_support_control_resolved':control_hits,
         'promoted_bridges':sum(bool(s.get('promoted')) for s in bot.document_role_bridge_hypotheses.values())}
    Path('results_v3').mkdir(exist_ok=True)
    Path('results_v3/v522_role_bridge.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(out)

if __name__=='__main__': main()

import json
from pathlib import Path
from leobot import Bot
from leobot.core import Atom


def train(bot):
    bot.ingest_document_text('''
ana frobla caja.
bea frobla libro.
cora frobla mapa.
dario norga puerto.
eva norga nodo.
fabio norga zona.
''', source='v521_train')
    return {p['surface']:p['predicate'] for p in bot.raw_relation_promotions.values()}


def main():
    bot=Bot(allow_extensional_grounding=False); preds=train(bot); p=preds['{s0} frobla {s1}']
    resolved=wrong_last=0
    for i in range(100):
        r=bot.ingest_document_text(
            f'sujeto{i} frobla objeto{i}. distractor{i} norga ruido{i}. consulta{i} frobla eso.',
            source=f'v521_case_{i}')
        row=r['sentence_results'][2]
        resolved += row.get('status')=='document_coreference_resolved' and row.get('args')==[f'consulta{i}',f'objeto{i}']
        wrong_last += bot.kb.contains(Atom(p,(f'consulta{i}',f'ruido{i}')))
    ambiguous=0
    for i in range(50):
        r=bot.ingest_document_text(
            f'a{i} frobla x{i}. b{i} frobla y{i}. c{i} frobla eso.', source=f'v521_amb_{i}')
        ambiguous += r['sentence_results'][2].get('status')=='document_coreference_ambiguous'
    clean=Bot(allow_extensional_grounding=False)
    pollution=0
    for i in range(60):
        r=clean.ingest_document_text(f'a{i} zenda eso.',source=f'v521_unknown_{i}')
        pollution += r['facts_added']
    out={'resolved':resolved,'wrong_last_reference_facts':wrong_last,
         'ambiguous_rejected':ambiguous,'unknown_reference_facts_added':pollution,
         'unknown_raw_observations':len(clean.raw_relation_observations)}
    Path('results_v3').mkdir(exist_ok=True)
    Path('results_v3/v521_document_coreference.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(out)

if __name__=='__main__': main()

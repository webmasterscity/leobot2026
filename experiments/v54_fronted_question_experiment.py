from __future__ import annotations
import hashlib,json
from pathlib import Path
from statistics import median
from time import perf_counter

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v54_fronted_question.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def seed(bot):
    for t in ['ana entrega caja a luis','bea entrega libro a mario','cora entrega mapa a nora']:
        r=bot.respond(t)
    assert r['status']=='raw_relation_learned'
    for i in range(100):
        assert bot.respond(f'p{i} entrega o{i} a r{i}')['status']=='stored'

def main():
    before=code_hash(); bot=Bot(allow_extensional_grounding=False); seed(bot)
    facts=bot.kb.stats()['facts']
    pre=bot.respond('¿qué entrega p0 a r0?')
    teach=bot.respond('"¿qué entrega ana a luis?" significa lo mismo que "¿ana entrega qué a luis?".')
    correct=wrong_anchor=0;times=[]
    for i in range(100):
        t=perf_counter();res=bot.respond(f'¿qué entrega p{i} a r{i}?');times.append((perf_counter()-t)*1000)
        correct += res.get('status')=='bindings' and any(p['atom']['args']==[f'p{i}',f'o{i}',f'r{i}'] for p in res.get('proofs',[]))
        wrong_anchor += bot.respond(f'¿qué separa p{i} a r{i}?').get('status')=='unrecognized'
    fact_delta=bot.kb.stats()['facts']-facts
    ctl=Bot(allow_extensional_grounding=False);seed(ctl)
    control=sum(ctl.respond(f'¿qué entrega p{i} a r{i}?').get('status')=='unrecognized' for i in range(100))
    after=code_hash()
    report={
      'version':'0.5.4-candidate','experiment':'explicit_fronted_wh_from_grounded_query',
      'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
      'pre_instruction_status':pre.get('status'),'instruction_status':teach.get('status'),
      'heldout':{'cases':100,'correct_bindings':correct,'median_ms':median(times)},
      'control_without_instruction':{'cases':100,'fronted_wh_unrecognized':control},
      'safety':{'wrong_anchor_unrecognized':wrong_anchor,'cases':100,'fact_delta_from_questions':fact_delta},
      'limits':[
        'Fronted WH is learned from explicit equivalence to an already grounded in-situ question; it is supervised instruction, not autonomous syntax induction.',
        'The mechanism remains predicate/surface specific and does not yet infer Spanish question transformations globally.',
        'Internal synthetic evaluation does not demonstrate AGI/ASI.'
      ]
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

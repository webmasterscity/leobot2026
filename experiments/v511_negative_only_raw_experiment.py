"""V5.11 internal experiment: discover an opaque relation from negative evidence only."""
from __future__ import annotations
import hashlib, json, statistics
from pathlib import Path
from time import perf_counter
from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def run():
    before=code_hash(); bot=Bot(allow_extensional_grounding=False)
    train=['ana no frobla caja a luis','bea no frobla libro a mario','cora no frobla mapa a nora']
    reports=[bot.respond(x) for x in train]
    learned=reports[-1]; pred=learned['predicate']
    assert [r['status'] for r in reports]==['raw_negative_relation_pending','raw_negative_relation_pending','raw_negative_relation_learned']
    assert bot.raw_relation_observations==[] and bot.kb.stats()['facts']==3
    correct=0; lat=[]
    for i in range(100):
        a=f'a{i:03d}'; o=f'o{i:03d}'; d=f'd{i:03d}'
        stored=bot.respond(f'{a} no frobla {o} a {d}')
        t0=perf_counter(); ans=bot.respond(f'¿{a} frobla {o} a {d}?'); lat.append((perf_counter()-t0)*1000)
        if stored.get('status')=='stored' and ans.get('status')=='refuted' and bot.kb.contains(Atom('!'+pred,(a,o,d))):
            correct+=1
    control=Bot(allow_extensional_grounding=False)
    control.respond(train[0]); control.respond(train[1]); control.respond('cora frobla mapa a nora')
    mixed={'promotions':len(control.raw_relation_promotions),'facts':control.kb.stats()['facts'],
           'positive_raw':len(control.raw_relation_observations),'negative_raw':len(control.raw_negative_relation_observations)}
    noise=Bot(allow_extensional_grounding=False)
    for i in range(60): noise.respond(f'sujeto{i} no verbo{i} objeto{i}')
    after=code_hash()
    result={'version':'0.5.11','train_statuses':[r['status'] for r in reports],
            'negative_only_heldout':{'correct':correct,'total':100,'p50_ms':statistics.median(lat),
                                     'p95_ms':sorted(lat)[int(.95*(len(lat)-1))]},
            'mixed_polarity_control':mixed,
            'noise_control':{'promotions':len(noise.raw_relation_promotions),'facts':noise.kb.stats()['facts']},
            'code_hash_before':before,'code_hash_after':after,'code_unchanged':before==after,
            'claim_boundary':'Opaque base-relation acquisition from explicit negative evidence only; not general semantic understanding.'}
    assert correct==100, result
    assert mixed=={'promotions':0,'facts':0,'positive_raw':1,'negative_raw':2}, result
    assert result['noise_control']=={'promotions':0,'facts':0}, result
    assert before==after, result
    return result
if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False,indent=2))

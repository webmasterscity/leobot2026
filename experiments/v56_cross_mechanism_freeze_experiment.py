from __future__ import annotations
import hashlib, json, random, time
from pathlib import Path
from leobot import Bot, Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v56_cross_mechanism_freeze.json'
F=lambda *x: tuple(x)
S=lambda *x: set(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def teach_raw_ternary(bot, prefix='r'):
    rows=[
        f'agente {prefix}alfa vincula recurso {prefix}rojo mediante canal {prefix}norte',
        f'agente {prefix}beta vincula recurso {prefix}azul mediante canal {prefix}sur',
        f'agente {prefix}gamma vincula recurso {prefix}verde mediante canal {prefix}este',
    ]
    reps=[bot.respond(x) for x in rows]
    return reps[-1]

def raw_heldout(bot, learned, n=100):
    pred=learned.get('predicate'); ok=0
    if not pred: return 0
    for i in range(n):
        text=f'agente hx{i} vincula recurso hr{i} mediante canal hc{i}'
        out=bot.respond(text)
        ok += out.get('status')=='stored' and bot.answer_atom(Atom(pred,(f'hx{i}',f'hr{i}',f'hc{i}')))['status']=='supported'
    return ok

def teach_numeric(bot):
    bot.procedures.min_support=3
    train=[('Incrementa 3 al valor.',(10,),(13,)),('Incrementa 5 al valor.',(7,),(12,)),('Incrementa 8 al valor.',(-2,),(6,))]
    reps=[bot.observe_transition(*r) for r in train]
    return reps[-1]

def numeric_heldout(bot,n=100):
    rng=random.Random(5601);ok=0
    for _ in range(n):
        x=rng.randint(-1000,1000);k=rng.randint(20,200)
        out=bot.execute_transition(f'Incrementa {k} al valor.',(x,))
        ok += out.get('result')==(x+k,)
    return ok

def move_episode(bot, phrase, p,s,d, success=True, missing=None):
    facts={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
    if missing=='road': facts.discard(F('road',s,d))
    if missing=='at': facts.discard(F('at',p,s))
    after=set(facts)
    if success:
        after.discard(F('at',p,s)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(phrase.format(p=p,s=s,d=d),facts,after)

def teach_move(bot, phrase='Desplaza a {p} desde {s} hasta {d}.', tag='m'):
    bot.symbolic.min_support=3
    reports=[]; first_learned=None
    for i,(p,s,d) in enumerate([(tag+'a','s1','d1'),(tag+'b','s2','d2'),(tag+'c','s3','d3')],1):
        r=move_episode(bot,phrase,p,s,d,True); reports.append(r)
        if r.get('status')=='operator_learned' and first_learned is None: first_learned=i
    reports.append(move_episode(bot,phrase,tag+'x','s4','d4',False,'road'))
    reports.append(move_episode(bot,phrase,tag+'y','s5','d5',False,'at'))
    return {'reports':reports,'successes_to_first_learned':first_learned}

def move_heldout(bot, phrase='Desplaza a {p} desde {s} hasta {d}.',n=100):
    ok=0
    for i in range(n):
        p,s,d=f'hp{i}',f'hs{i}',f'hd{i}'
        state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
        out=bot.execute_symbolic_transition(phrase.format(p=p,s=s,d=d),state)
        ok += out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',()))
    return ok

def compare_cross_mechanism():
    educated=Bot(); fresh=Bot()
    raw=teach_raw_ternary(educated,'e')
    raw_score=raw_heldout(educated,raw)
    num=teach_numeric(educated)
    num_score=numeric_heldout(educated)
    e=teach_move(educated,tag='em')
    f=teach_move(fresh,tag='fm')
    return {
        'prior_capabilities':{'raw_status':raw.get('status'),'raw_heldout':raw_score,
                              'numeric_status':num.get('status'),'numeric_heldout':num_score},
        'new_symbolic_action':{
            'educated_successes_to_first_learned':e['successes_to_first_learned'],
            'fresh_successes_to_first_learned':f['successes_to_first_learned'],
            'educated_heldout':move_heldout(educated),
            'fresh_heldout':move_heldout(fresh),
            'educated_meta_schemas':len(getattr(educated.symbolic,'meta_schemas',{})),
            'fresh_meta_schemas':len(getattr(fresh.symbolic,'meta_schemas',{})),
        }
    }

def accumulation_retention():
    b=Bot(); stages=[]
    raw=teach_raw_ternary(b,'a'); stages.append({'stage':'raw','raw':raw_heldout(b,raw,40)})
    teach_numeric(b); stages.append({'stage':'numeric','raw':raw_heldout(b,raw,40),'numeric':numeric_heldout(b,40)})
    teach_move(b,tag='am'); stages.append({'stage':'symbolic','raw':raw_heldout(b,raw,40),'numeric':numeric_heldout(b,40),'symbolic':move_heldout(b,n=40)})
    return stages

def main():
    h0=code_hash();t=time.perf_counter()
    out={'version':'V5.6-freeze-diagnostic','experiment':'cross_mechanism_architecture_freeze',
         'code_hash_before':h0,'cross_mechanism':compare_cross_mechanism(),
         'accumulation_retention':accumulation_retention()}
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-t)*1000
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()

from __future__ import annotations
import hashlib,json,statistics,time,tempfile
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
F=lambda *x:tuple(x);S=lambda *x:set(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()

def obs_move(bot,idx,n=0):
    pos=f'pos{idx}';edge=f'edge{idx}';phrase=f'Accion{idx} a {{p}} de {{s}} a {{d}}.'
    p=f'p{idx}_{n}';s=f's{idx}_{n}';d=f'd{idx}_{n}'
    before=S(F(pos,p,s),F(edge,s,d),F('person',p),F('place',s),F('place',d))
    after=(before-{F(pos,p,s)})|{F(pos,p,d)}
    t=time.perf_counter_ns();r=bot.observe_symbolic_transition(phrase.format(p=p,s=s,d=d),before,after);us=(time.perf_counter_ns()-t)/1000
    return r,us,phrase,(pos,edge)

def fail_move(bot,idx,missing):
    pos=f'pos{idx}';edge=f'edge{idx}';phrase=f'Accion{idx} a {{p}} de {{s}} a {{d}}.'
    p=f'f{idx}_{missing}';s=f'fs{idx}_{missing}';d=f'fd{idx}_{missing}'
    facts=[F(pos,p,s),F(edge,s,d),F('person',p),F('place',s),F('place',d)];facts.pop(missing);before=set(facts)
    return bot.observe_symbolic_transition(phrase.format(p=p,s=s,d=d),before,before)

def heldout_move(bot,idx):
    pos=f'pos{idx}';edge=f'edge{idx}';phrase=f'Accion{idx} a {{p}} de {{s}} a {{d}}.'
    p=f'hp{idx}';s=f'hs{idx}';d=f'hd{idx}';st=S(F(pos,p,s),F(edge,s,d),F('person',p),F('place',s),F('place',d))
    r=bot.execute_symbolic_transition(phrase.format(p=p,s=s,d=d),st)
    return r.get('status')=='executed_symbolic_action' and F(pos,p,d) in r.get('result',())

def build_scale(n_domains=300,persist_at=150):
    b=Bot();b.symbolic.min_support=3
    for n in range(3):obs_move(b,0,n)
    fail_move(b,0,0);fail_move(b,0,1)
    obs_move(b,1,0);r,_,_,_=obs_move(b,1,1)
    assert r.get('status')=='operator_learned'
    records=[];persisted=False
    for idx in range(2,n_domains+2):
        r,us,_,_=obs_move(b,idx,0)
        assert r.get('status')=='operator_learned',r
        records.append({'domain':idx+1,'learn_us':us,'source_count':r.get('analogy_source_count'),
                        'source_evidence':len(r.get('analogy_sources',[])),'heldout':heldout_move(b,idx)})
        if idx==persist_at:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'state.json';b.save(p);b=Bot.load(p);persisted=True
                assert len(b.symbolic.structural_schemas())==1
    return b,records,persisted

def family_freeze():
    # Reuse the external frozen-code evaluator; it modifies no engine code.
    import experiments.v40_architecture_freeze_meta_transfer as exp
    # Run its helpers directly so this result is tied to the current frozen hash.
    move_base=('Mueve a {p} de {s} a {d}.',('at','road'))
    move_variants=[('Navega a {p} de {s} a {d}.',('located','link')),('Desplaza a {p} desde {s} hasta {d}.',('positioned','path')),('Traslada a {p} entre {s} y {d}.',('situated','route'))]
    pick_base=('{p} toma {i} en {l}.',('at','item_at','holding'))
    pick_variants=[('{p} recolecta {i} en {l}.',('positioned','token_at','possesses')),('{p} adquiere {i} dentro de {l}.',('located','object_at','carries')),('{p} obtiene {i} desde {l}.',('situated','asset_at','owns'))]
    swap_base=('{a} intercambia {x} con {b} por {y}.',('owns','connected'))
    swap_variants=[('{a} permuta {x} con {b} y {y}.',('holds','linked')),('{a} canjea {x} con {b} por {y}.',('possesses','peer')),('{a} cambia {x} con {b} y recibe {y}.',('controls','adjacent'))]
    _,m=exp.run_family('move',*move_base,move_variants)
    _,p=exp.run_family('pick',*pick_base,pick_variants)
    _,s=exp.run_family('swap',*swap_base,swap_variants)
    return {'move':m,'pickup':p,'swap':s}

def summary(records):
    out={}
    for n in [10,25,50,100,200,300]:
        arr=[r['learn_us'] for r in records if r['domain']<=n+2]
        if arr:out[str(n)]={'median_us':statistics.median(arr),'last_us':arr[-1]}
    return out

def main():
    h0=code_hash();t0=time.perf_counter()
    families=family_freeze()
    b,records,persisted=build_scale()
    schemas=b.symbolic.structural_schemas()
    baseline_path=ROOT/'results_v3'/'baseline_v40_analogy_scale.json'
    baseline=None
    if baseline_path.exists():
        raw=json.loads(baseline_path.read_text());vals=raw.get('records',[])
        if vals:
            baseline={'domain_300_last_us':vals[-1][1], 'domains':len(vals)}
    out={'version':'0.4.1','experiment':'explicit_persistent_meta_schema_scaling','code_hash_before':h0,
         'architecture_freeze_families':{k:{'success_curve':v['success_curve'],'heldout_correct':[x['heldout']['correct'] for x in v['domains']]} for k,v in families.items()},
         'scale':{'domains':len(records),'all_heldout':all(r['heldout'] for r in records),'checkpoints':summary(records),
                  'final_source_count':records[-1]['source_count'],'final_source_evidence':records[-1]['source_evidence'],
                  'schema_count':len(schemas),'schema_support':schemas[0]['support'] if schemas else 0,
                  'persisted_midway':persisted},'v40_baseline':baseline,'elapsed_ms':(time.perf_counter()-t0)*1000}
    out['code_hash_after']=code_hash();out['code_unchanged_during_evaluation']=out['code_hash_before']==out['code_hash_after']
    path=ROOT/'results_v3'/'v41_meta_schema.json';path.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=='__main__':main()

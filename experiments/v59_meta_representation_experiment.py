from __future__ import annotations
import hashlib, json, random, tempfile, time
from pathlib import Path
from leobot import Bot, Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v59_meta_representation.json'
F=lambda *x: tuple(x)


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()


def sentence(vals, positive=True):
    core=' '.join(f'rol{i} {v}' for i,v in enumerate(vals))
    if positive:return 'relacion '+core
    return 'relacion no '+core


def teach_schema_projection(bot: Bot, n: int, mapping: tuple[int,...], tag: str):
    positives=[]
    for j in range(2):
        vals=tuple(f'{tag}p{j}r{i}' for i in range(n)); positives.append(vals)
        for v in vals: bot.kb.add(Atom('known_'+tag,(v,)),'v59-known')
        bot.kb.add(Atom('base_'+tag,tuple(vals[i] for i in mapping)),'v59-base')
    negatives=[]
    if len(mapping)==1:
        for j in range(2):
            vals=list(positives[j]); bad=f'{tag}neg{j}'; bot.kb.add(Atom('known_'+tag,(bad,)),'v59-known')
            vals[mapping[0]]=bad; negatives.append(tuple(vals))
    else:
        a=list(positives[0]); a[mapping[0]]=positives[1][mapping[0]]; negatives.append(tuple(a))
        b=list(positives[1]); b[mapping[-1]]=positives[0][mapping[-1]]; negatives.append(tuple(b))
    reps=[]
    for vals in positives: reps.append(bot.observe_schema_statement(sentence(vals,True)))
    for vals in negatives: reps.append(bot.observe_schema_statement(sentence(vals,False)))
    return reps[-1], positives, negatives


def numeric_projection(bot: Bot, n: int, mapping: tuple[int,...], tag: str, support=2):
    reps=[]
    for j in range(support):
        row=tuple(100*(j+1)+i for i in range(n))
        reps.append(bot.observe_transition(f'Proyecta estructura {tag}.',row,tuple(row[i] for i in mapping)))
    return reps


def numeric_heldout(bot,n,mapping,tag,count=100):
    rng=random.Random(5900+n+sum(mapping));ok=0
    for _ in range(count):
        row=tuple(rng.randint(-9999,9999) for _ in range(n)); exp=tuple(row[i] for i in mapping)
        ok += bot.execute_transition(f'Proyecta estructura {tag}.',row).get('result')==exp
    return ok


def symbolic_episode(bot,p,s,d,success=True,missing=None):
    state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
    if missing=='road':state.discard(F('road',s,d))
    aft=set(state)
    if success:aft.discard(F('at',p,s));aft.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state,aft)


def one_projection(n,mapping,idx):
    tag=f'm{idx}'
    treatment=Bot(); control=Bot()
    schema,_,_=teach_schema_projection(treatment,n,mapping,tag)
    tr=numeric_projection(treatment,n,mapping,tag,2)
    cr=numeric_projection(control,n,mapping,tag,2)
    return {
        'input_arity':n,'mapping':list(mapping),'schema_status':schema.get('status'),
        'meta_schema':schema.get('meta_representation',{}).get('meta',{}).get('schema'),
        'treatment_status':tr[-1].get('status'),'control_status':cr[-1].get('status'),
        'treatment_correct':numeric_heldout(treatment,n,mapping,tag),
        'control_correct':numeric_heldout(control,n,mapping,tag),
    }


def symbolic_transfer():
    t=Bot();c=Bot();teach_schema_projection(t,3,(0,2),'sym')
    tr=[];cr=[]
    for row in [('personaA','sitioA','destinoA',True,None),('personaB','sitioB','destinoB',True,None),('personaX','sitioX','destinoX',False,'road')]:
        tr.append(symbolic_episode(t,*row));cr.append(symbolic_episode(c,*row))
    ok=0
    for i in range(100):
        p,s,d=f'hp{i}',f'hs{i}',f'hd{i}';state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
        out=t.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state)
        ok += out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',()))
    return {'treatment_status':tr[-1].get('status'),'control_status':cr[-1].get('status'),
            'treatment_mode':tr[-1].get('precondition_mode'),'heldout_correct':ok}


def incompatible_control():
    b=Bot();teach_schema_projection(b,3,(0,2),'bad')
    reps=[]
    for row in [(2,7,3),(5,9,4)]:
        reps.append(b.observe_transition('Combina extremos.',row,(row[0]+row[2],)))
    return {'status_after_two':reps[-1].get('status'),
            'meta_rows':len(b.meta_representations.rows())}


def withdrawal_and_persistence():
    b=Bot();learned,_,_=teach_schema_projection(b,3,(0,2),'wd')
    source='schema_surface:'+str(learned.get('surface'))
    before=b.meta_representations.has_source(source)
    contradictory=b.observe_schema_statement(sentence(('wdp0r0','wdp0r1','wdp0r2'),False))
    after=b.meta_representations.has_source(source)
    # persistence on an independent valid source
    p=Bot();teach_schema_projection(p,3,(2,0),'persist')
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'state.json';p.save(path);q=Bot.load(path)
        reps=numeric_projection(q,3,(2,0),'persist_num',2)
        persist_status=reps[-1].get('status')
        persist_ok=numeric_heldout(q,3,(2,0),'persist_num',40)
    return {'source_present_before':before,'contradictory_status':contradictory.get('status'),
            'source_present_after':after,'persistence_status':persist_status,'persistence_correct':persist_ok}


def main():
    h0=code_hash();start=time.perf_counter()
    mappings=[(3,(1,)),(3,(2,0)),(3,(1,0)),(3,(2,1))]
    rows=[one_projection(n,m,i) for i,(n,m) in enumerate(mappings)]
    out={'version':'V5.9-development','mechanism':'central_cross_mechanism_meta_representation',
         'code_hash_before':h0,'projection_families':rows,'symbolic_transfer':symbolic_transfer(),
         'incompatible_arithmetic':incompatible_control(),'withdrawal_persistence':withdrawal_and_persistence()}
    out['all_treatments_learned']=all(r['treatment_status']=='procedure_learned' for r in rows)
    out['all_controls_pending']=all(r['control_status']=='procedure_pending' for r in rows)
    out['heldout_total']=sum(r['treatment_correct'] for r in rows)
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-start)*1000
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

from __future__ import annotations
import hashlib,json,random,time,tempfile
from pathlib import Path
from leobot import Bot
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v57_cross_representation_projection.json'
F=lambda *x:tuple(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def train_numeric_projection(bot):
    rows=[];bot.procedures.min_support=3
    for v in [(1,2,3),(4,5,6),(7,8,9)]:rows.append(bot.observe_transition('Conserva primero y tercero.',v,(v[0],v[2])))
    return rows

def move(bot,p,s,d,success=True,missing=None):
    st={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
    if missing=='road':st.discard(F('road',s,d))
    aft=set(st)
    if success:aft.discard(F('at',p,s));aft.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Traslada a {p} de {s} a {d}.',st,aft)

def target_evidence(bot,extra_positive=False):
    rows=[move(bot,'ana','casa','oficina'),move(bot,'bruno','plaza','tienda'),move(bot,'carla','patio','taller',False,'road')]
    if extra_positive:rows.append(move(bot,'diego','garaje','parque'))
    return rows

def heldout_move(bot,n=200):
    good=reject=0
    for i in range(n):
        p,s,d=f'p{i}',f's{i}',f'd{i}';st={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
        out=bot.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',st);res=set(out.get('result',()))
        good += out.get('status')=='executed_symbolic_action' and F('at',p,d) in res
        broken=set(st);broken.discard(F('road',s,d));bad=bot.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',broken)
        reject += bad.get('status')!='executed_symbolic_action'
    return {'cases':n,'valid_correct':good,'invalid_rejected':reject}

def reverse_transfer():
    t=Bot();c=Bot();t.symbolic.min_support=3
    source=[]
    for row in [('ana','casa','oficina'),('bruno','plaza','tienda'),('carla','patio','taller')]:source.append(move(t,*row))
    tr=[];cr=[]
    for before in [(10,99,20),(5,77,9)]:
        tr.append(t.observe_transition('Elige extremos.',before,(before[0],before[2])))
        cr.append(c.observe_transition('Elige extremos.',before,(before[0],before[2])))
    rng=random.Random(5701);ts=cs=0
    for _ in range(200):
        a,b,cx=[rng.randint(-10000,10000) for _ in range(3)];exp=(a,cx)
        ts+=t.execute_transition('Elige extremos.',(a,b,cx)).get('result')==exp
        cs+=c.execute_transition('Elige extremos.',(a,b,cx)).get('result')==exp
    return {'source_last':source[-1],'treatment_reports':tr,'control_reports':cr,'heldout':200,
            'treatment_correct':ts,'control_correct':cs,'schemas':t.procedures.external_projection_schemas}

def main():
    h0=code_hash();start=time.perf_counter()
    t=Bot();c=Bot();robust=Bot();source=train_numeric_projection(t)
    tr=target_evidence(t);cr=target_evidence(c);rr=target_evidence(robust,True)
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'s.json';t.save(p);loaded=Bot.load(p);persist=heldout_move(loaded,40)
    out={'version':'V5.7-development','mechanism':'cross_representation_role_projection','code_hash_before':h0,
         'numeric_source_last':source[-1],
         'numeric_to_symbolic':{'treatment_reports':tr,'control_reports':cr,'fresh_robust_reports':rr,
                                'treatment_heldout':heldout_move(t),'control_heldout':heldout_move(c),
                                'fresh_robust_heldout':heldout_move(robust)},
         'symbolic_to_numeric':reverse_transfer(),'persistence_heldout':persist}
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-start)*1000
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

from __future__ import annotations
import hashlib, json, statistics, time
from pathlib import Path
from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
F=lambda *x:tuple(x)
S=lambda *x:set(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def observe_move(bot, phrase, preds, p,s,d, success=True, distractors=()):
    pos,edge=preds
    before=S(F(pos,p,s),F(edge,s,d),F('person',p),F('place',s),F('place',d),*distractors)
    after=(before-{F(pos,p,s)})|{F(pos,p,d)} if success else before
    return bot.observe_symbolic_transition(phrase.format(p=p,s=s,d=d),before,after)

def observe_pick(bot, phrase, preds, p,item,loc, success=True, distractors=()):
    pos,objat,own=preds
    before=S(F(pos,p,loc),F(objat,item,loc),F('person',p),F('item',item),F('place',loc),*distractors)
    after=(before-{F(objat,item,loc)})|{F(own,p,item)} if success else before
    return bot.observe_symbolic_transition(phrase.format(p=p,i=item,l=loc),before,after)

def observe_swap(bot, phrase, preds, a,b,x,y, success=True, distractors=()):
    own,edge=preds
    before=S(F(own,a,x),F(own,b,y),F(edge,a,b),F('person',a),F('person',b),F('item',x),F('item',y),*distractors)
    after=(before-{F(own,a,x),F(own,b,y)})|{F(own,a,y),F(own,b,x)} if success else before
    return bot.observe_symbolic_transition(phrase.format(a=a,b=b,x=x,y=y),before,after)

def exec_move(bot, phrase, preds, p,s,d):
    pos,edge=preds
    st=S(F(pos,p,s),F(edge,s,d),F('person',p),F('place',s),F('place',d))
    r=bot.execute_symbolic_transition(phrase.format(p=p,s=s,d=d),st)
    return r.get('status')=='executed_symbolic_action' and F(pos,p,d) in r.get('result',())

def exec_pick(bot, phrase, preds, p,item,loc):
    pos,objat,own=preds
    st=S(F(pos,p,loc),F(objat,item,loc),F('person',p),F('item',item),F('place',loc))
    r=bot.execute_symbolic_transition(phrase.format(p=p,i=item,l=loc),st)
    return r.get('status')=='executed_symbolic_action' and F(own,p,item) in r.get('result',())

def exec_swap(bot, phrase, preds, a,b,x,y):
    own,edge=preds
    st=S(F(own,a,x),F(own,b,y),F(edge,a,b),F('person',a),F('person',b),F('item',x),F('item',y))
    r=bot.execute_symbolic_transition(phrase.format(a=a,b=b,x=x,y=y),st)
    return r.get('status')=='executed_symbolic_action' and F(own,a,y) in r.get('result',()) and F(own,b,x) in r.get('result',())

def teach_robust_move(bot, phrase, preds, tag):
    succ=[(f'{tag}a','s1','d1'),(f'{tag}b','s2','d2'),(f'{tag}c','s3','d3')]
    reports=[]
    for row in succ: reports.append(observe_move(bot,phrase,preds,*row,True,(F('licensed',row[0]),)))
    # failures isolate edge and position preconditions
    # Construct failures manually, one missing each relevant fact.
    pos,edge=preds
    p=f'{tag}f2'; s='s5';d='d5';before=S(F(pos,p,s),F('licensed',p),F('person',p),F('place',s),F('place',d));reports.append(bot.observe_symbolic_transition(phrase.format(p=p,s=s,d=d),before,before))
    p=f'{tag}f3'; s='s6';d='d6';before=S(F(edge,s,d),F('licensed',p),F('person',p),F('place',s),F('place',d));reports.append(bot.observe_symbolic_transition(phrase.format(p=p,s=s,d=d),before,before))
    return reports

def teach_robust_pick(bot, phrase, preds, tag):
    reports=[]
    for idx,(p,i,l) in enumerate([(f'{tag}a','i1','l1'),(f'{tag}b','i2','l2'),(f'{tag}c','i3','l3')]):
        reports.append(observe_pick(bot,phrase,preds,p,i,l,True,(F('certified',p),)))
    pos,objat,own=preds
    p=f'{tag}f1';i='i4';l='l4';before=S(F(pos,p,l),F('certified',p),F('person',p),F('item',i),F('place',l));reports.append(bot.observe_symbolic_transition(phrase.format(p=p,i=i,l=l),before,before))
    p=f'{tag}f2';i='i5';l='l5';before=S(F(objat,i,l),F('certified',p),F('person',p),F('item',i),F('place',l));reports.append(bot.observe_symbolic_transition(phrase.format(p=p,i=i,l=l),before,before))
    return reports

def teach_robust_swap(bot, phrase, preds, tag):
    reports=[]
    rows=[(f'{tag}a',f'{tag}b','x1','y1'),(f'{tag}c',f'{tag}d','x2','y2'),(f'{tag}e',f'{tag}f','x3','y3')]
    for row in rows:reports.append(observe_swap(bot,phrase,preds,*row,True,(F('approved',row[0]),)))
    own,edge=preds
    a=f'{tag}g';b=f'{tag}h';x='x4';y='y4';before=S(F(own,a,x),F(own,b,y),F('approved',a),F('person',a),F('person',b),F('item',x),F('item',y));reports.append(bot.observe_symbolic_transition(phrase.format(a=a,b=b,x=x,y=y),before,before))
    a=f'{tag}i';b=f'{tag}j';x='x5';y='y5';before=S(F(edge,a,b),F(own,b,y),F('approved',a),F('person',a),F('person',b),F('item',x),F('item',y));reports.append(bot.observe_symbolic_transition(phrase.format(a=a,b=b,x=x,y=y),before,before))
    a=f'{tag}k';b=f'{tag}l';x='x6';y='y6';before=S(F(edge,a,b),F(own,a,x),F('approved',a),F('person',a),F('person',b),F('item',x),F('item',y));reports.append(bot.observe_symbolic_transition(phrase.format(a=a,b=b,x=x,y=y),before,before))
    return reports

def promote_target(bot, family, phrase, preds, tag, max_success=3):
    reports=[]
    for n in range(1,max_success+1):
        if family=='move':r=observe_move(bot,phrase,preds,f'{tag}p{n}',f'{tag}s{n}',f'{tag}d{n}',True,(F(f'noise{n}',f'{tag}p{n}'),))
        elif family=='pick':r=observe_pick(bot,phrase,preds,f'{tag}p{n}',f'{tag}i{n}',f'{tag}l{n}',True,(F(f'noise{n}',f'{tag}p{n}'),))
        else:r=observe_swap(bot,phrase,preds,f'{tag}a{n}',f'{tag}b{n}',f'{tag}x{n}',f'{tag}y{n}',True,(F(f'noise{n}',f'{tag}a{n}'),))
        reports.append(r)
        if r.get('status')=='operator_learned':return n,reports
    return None,reports

def heldout(bot,family,phrase,preds,N=100):
    ok=0
    for n in range(N):
        if family=='move': good=exec_move(bot,phrase,preds,f'hp{n}',f'hs{n}',f'hd{n}')
        elif family=='pick': good=exec_pick(bot,phrase,preds,f'hp{n}',f'hi{n}',f'hl{n}')
        else: good=exec_swap(bot,phrase,preds,f'ha{n}',f'hb{n}',f'hx{n}',f'hy{n}')
        ok+=bool(good)
    return {'cases':N,'correct':ok}

def run_family(family, base_phrase, base_preds, variants):
    b=Bot();b.symbolic.min_support=3
    if family=='move':teach_robust_move(b,base_phrase,base_preds,'m0')
    elif family=='pick':teach_robust_pick(b,base_phrase,base_preds,'p0')
    else:teach_robust_swap(b,base_phrase,base_preds,'s0')
    curve=[3];details=[]
    for idx,(phrase,preds) in enumerate(variants,1):
        needed,reports=promote_target(b,family,phrase,preds,f'{family}{idx}')
        ho=heldout(b,family,phrase,preds)
        curve.append(needed)
        details.append({'domain':idx,'successes_to_promote':needed,'reports':reports,'heldout':ho})
    return b,{'success_curve':curve,'domains':details}

def main():
    h0=code_hash();t0=time.perf_counter()
    move_base=('Mueve a {p} de {s} a {d}.',('at','road'))
    move_variants=[('Navega a {p} de {s} a {d}.',('located','link')),('Desplaza a {p} desde {s} hasta {d}.',('positioned','path')),('Traslada a {p} entre {s} y {d}.',('situated','route'))]
    pick_base=('{p} toma {i} en {l}.',('at','item_at','holding'))
    pick_variants=[('{p} recolecta {i} en {l}.',('positioned','token_at','possesses')),('{p} adquiere {i} dentro de {l}.',('located','object_at','carries')),('{p} obtiene {i} desde {l}.',('situated','asset_at','owns'))]
    swap_base=('{a} intercambia {x} con {b} por {y}.',('owns','connected'))
    swap_variants=[('{a} permuta {x} con {b} y {y}.',('holds','linked')),('{a} canjea {x} con {b} por {y}.',('possesses','peer')),('{a} cambia {x} con {b} y recibe {y}.',('controls','adjacent'))]
    bm,m=run_family('move',*move_base,move_variants)
    bp,p=run_family('pick',*pick_base,pick_variants)
    bs,s=run_family('swap',*swap_base,swap_variants)

    # Cross-family negative control: two prior move schemas must not teach a pickup-shape in one example.
    bc=Bot();bc.symbolic.min_support=3;teach_robust_move(bc,*move_base,'cm0')
    promote_target(bc,'move',move_variants[0][0],move_variants[0][1],'cm1',2)
    r_cross=observe_pick(bc,'{p} recolecta {i} en {l}.',('positioned','token_at','possesses'),'cx','ci','cl',True)
    cross_ho=heldout(bc,'pick','{p} recolecta {i} en {l}.',('positioned','token_at','possesses'),20)

    # Fresh controls for the third variants: one success should not be enough.
    fresh={}
    for family,phrase,preds in [('move',move_variants[2][0],move_variants[2][1]),('pick',pick_variants[2][0],pick_variants[2][1]),('swap',swap_variants[2][0],swap_variants[2][1])]:
        b=Bot();b.symbolic.min_support=3
        n,reps=promote_target(b,family,phrase,preds,'fresh',1)
        fresh[family]={'report':reps[-1],'heldout':heldout(b,family,phrase,preds,50)}

    out={'version':'0.4.0','experiment':'architecture_freeze_cross_family_meta_transfer','code_hash_before':h0,'families':{'move':m,'pickup':p,'swap':s},
         'cross_family_negative':{'report':r_cross,'heldout':cross_ho},'fresh_one_success_controls':fresh,'elapsed_ms':(time.perf_counter()-t0)*1000}
    out['code_hash_after']=code_hash();out['code_unchanged']=out['code_hash_before']==out['code_hash_after']
    path=ROOT/'results_v3'/'v40_architecture_freeze_meta_transfer.json';path.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=='__main__':main()

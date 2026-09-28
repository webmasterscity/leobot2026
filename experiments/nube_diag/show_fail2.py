import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep import *
from sweep2 import soft_bm25
import random
DEV=['results_v3/kiosco/desarrollo/'+c for c in 'ABCDEF']
bot=Bot.load(BASE); rows=[]
for name,text,ins,convs in businesses(DEV):
    bot.load_context(text,ins); ctx=Ctx(bot)
    for conv in convs:
        for t in conv:
            if t.get('accion','responder')!='responder' or t.get('tipo') not in ('directa','si_no'): continue
            keys=[k for k in t.get('claves') or [] if plain(k)]
            if not keys: continue
            gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
            if not gold: continue
            q=list(dict.fromkeys(bot.context_terms(t['cliente']))); sc=soft_bm25(ctx,q,4,0.6,0.5,True)
            order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
            first=min(order.index(g) for g in gold)
            if first>0:
                g=order[first]; top=order[0]
                def m(i): return [x for x in q if x in ctx.seq[i] or x in ctx.inh[i]]
                rows.append((t['cliente'],q,ctx.units[top]['text'][:110],m(top),ctx.units[g]['text'][:110],m(g),first,t['claves']))
random.Random(11).shuffle(rows)
for r in rows[:30]:
    print('Q:',r[0]); print('  qterms',r[1]); print('  TOP :',r[2],r[3]); print('  GOLD:',r[4],r[5],'rank',r[6],'keys',r[7]); print()

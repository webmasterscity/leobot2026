import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep import *
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
            q=bot.context_terms(t['cliente']); sc=bm25(ctx,q,0.5)
            order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
            first=min(order.index(g) for g in gold)
            if 0<first<5:
                rows.append((name,t['cliente'],q,[ctx.units[order[0]]['text'][:150],ctx.units[order[0]]['heading']],[(ctx.units[g]['text'][:150],ctx.units[g]['heading']) for g in list(gold)[:1]],first))
random.Random(5).shuffle(rows)
for r in rows[:22]:
    print('Q:',r[1]); print('  TOP1:',r[3]); print('  GOLD(rank %d):'%r[5],r[4]); print()

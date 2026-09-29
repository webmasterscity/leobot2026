import sys; sys.path.insert(0,'experiments/nube_diag')
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    from sweep6 import *
def top_of(sc,ctx):
    order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
    return order
def run_hist(folders, mode, w=0.5, kinds=('seguimiento',)):
    bot=Bot.load(BASE); res=[0,0,0,0]; 
    for name,text,ins,convs in businesses(folders):
        bot.load_context(text,ins); ctx=Ctx(bot)
        for conv in convs:
            prev_terms=[]; prev_top=None
            for t in conv:
                q=bot.context_terms(t['cliente'])
                sc0=mix2(ctx,q,t['cliente'],soft=(3,0.5,1.0))
                order0=top_of(sc0,ctx)
                keys=[k for k in t.get('claves') or [] if plain(k)]
                if t.get('accion','responder')=='responder' and keys and t.get('tipo') in kinds:
                    gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                    if gold:
                        sc=dict(sc0)
                        if mode in ('terms','both') and prev_terms:
                            extra=[x for x in prev_terms if x not in q]
                            sp=mix2(ctx,extra,'',soft=(3,0.5,1.0),heading_prior=True)
                            for i,v in sp.items(): sc[i]=sc.get(i,0)+w*v
                        if mode in ('section','both') and prev_top is not None:
                            h=ctx.units[prev_top]['heading']
                            for i in ctx.valid:
                                if h and ctx.units[i]['heading']==h: sc[i]=sc.get(i,0)+w*3
                                if i==prev_top: pass
                        order=top_of(sc,ctx)
                        first=min(order.index(g) for g in gold)
                        res[0]+=1; res[1]+=first<1; res[2]+=first<3; res[3]+=first<5
                prev_terms=q; prev_top=order0[0] if order0 and sc0 else None
    return res

import sys
for kinds in (('directa','si_no'),('combinada',),('instruccion','sin_respuesta')):
    for mode,w in (('none',0),('both',0.5),('terms',0.3)):
        out=[]
        for label,fs in (('dev',DEV),('val3',VAL3)):
            r=run_hist(fs,mode,w,kinds=kinds)
            out.append(f'{label} n={r[0]} top1={r[1]/max(1,r[0]):.3f} top3={r[2]/max(1,r[0]):.3f} top5={r[3]/max(1,r[0]):.3f}')
        print(f'{kinds} {mode:8s} w={w}: '+' | '.join(out),flush=True)

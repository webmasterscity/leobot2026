import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep import *
import glob,os
DEV=['results_v3/kiosco/desarrollo/'+c for c in 'ABCDEF']
def leaves(bank): return sorted({os.path.dirname(os.path.dirname(f)) for f in glob.glob(f'results_v3/kiosco/{bank}/**/conversaciones.json',recursive=True)})
VAL=[l for b in ('congelado','congelado_g58','congelado_g59','congelado_g60') for l in leaves(b)]
def show(name,sc):
    a=run(sc,DEV); b=run(sc,VAL)
    print(f'{name:38s} dev n={a[0]} top1={a[1][0]:.3f} top3={a[1][1]:.3f} top5={a[1][2]:.3f} | val n={b[0]} top1={b[1][0]:.3f} top3={b[1][1]:.3f} top5={b[1][2]:.3f}',flush=True)

def lcp(a,b):
    n=0
    for x,y in zip(a,b):
        if x!=y: break
        n+=1
    return n

class Soft:
    """vocabulario del documento y semejanza de prefijo"""
    cache={}
def related(ctx,t,minp,ratio):
    key=(id(ctx),t,minp,ratio)
    if key in Soft.cache: return Soft.cache[key]
    out=[]
    for r in ctx.df:
        if r==t: continue
        p=lcp(t,r)
        if p>=minp and p/max(len(t),len(r))>=ratio: out.append((r,p/max(len(t),len(r))))
    Soft.cache[key]=out
    return out

def soft_bm25(ctx,q,minp=4,ratio=0.6,w_inh=0.5,exclude_heading=False,soft_w=1.0):
    sc={}
    for t in dict.fromkeys(q):
        if t in ctx.title: continue
        variants=[(t,1.0)]+[(r,s*soft_w) for r,s in related(ctx,t,minp,ratio)]
        for r,wt in variants:
            idf=ctx.idf(r)
            if ctx.df.get(r,0)==0: continue
            for i in ctx.valid:
                if exclude_heading and ctx.units[i]['kind']=='heading': continue
                tf=ctx.seq[i].count(r)+(w_inh if r in ctx.inh[i] and r not in ctx.seq[i] else 0)
                if tf:
                    sc[i]=sc.get(i,0)+wt*idf*tf*(K1+1)/(tf+K1*(1-B+B*ctx.len[i]/ctx.avg))
    return sc
show('bm25 inh=.5',lambda c,q:bm25(c,q,0.5))
show('bm25 inh=.5 sin encabezados',lambda c,q:soft_bm25(c,q,99,1.0,0.5,True))
show('soft p>=4 r>=.6',lambda c,q:soft_bm25(c,q,4,0.6,0.5,False))
show('soft p>=4 r>=.6 sin enc',lambda c,q:soft_bm25(c,q,4,0.6,0.5,True))
show('soft p>=3 r>=.5 sin enc',lambda c,q:soft_bm25(c,q,3,0.5,0.5,True))
show('soft p>=4 r>=.5 w.5 sin enc',lambda c,q:soft_bm25(c,q,4,0.5,0.5,True,0.5))

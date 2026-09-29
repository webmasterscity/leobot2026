import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep import *
from sweep2 import lcp, related, soft_bm25, leaves, DEV, VAL, show
import collections
def sections(ctx):
    key='_sec'
    if hasattr(ctx,key): return getattr(ctx,key)
    groups=collections.defaultdict(list)
    for i in ctx.valid:
        h=ctx.units[i]['heading']
        if h: groups[h].append(i)
    sec={}
    for h,ids in groups.items():
        terms=[]
        for i in ids: terms+=ctx.seq[i]
        terms+=ctx.bot.context_terms(h)*2
        sec[h]=(ids,terms)
    df=collections.Counter()
    for h,(ids,terms) in sec.items():
        for t in set(terms): df[t]+=1
    avg=sum(len(t) for _,t in sec.values())/max(1,len(sec))
    res=(sec,df,avg); setattr(ctx,key,res); return res
def sec_scores(ctx,q):
    sec,df,avg=sections(ctx)
    out={}
    n=len(sec)
    for h,(ids,terms) in sec.items():
        s=0
        L=max(1,len(terms))
        for t in dict.fromkeys(q):
            if t in ctx.title: continue
            c=terms.count(t)
            if not c: continue
            idf=math.log(1+(n-df[t]+0.5)/(df[t]+0.5))
            s+=idf*c*(K1+1)/(c+K1*(1-B+B*L/avg))
        out[h]=s
    return out
def hier(ctx,q,lam=0.5,soft=True):
    u=soft_bm25(ctx,q,4,0.6,0.5,True) if soft else bm25(ctx,q,0.5)
    ss=sec_scores(ctx,q)
    mx=max(u.values(),default=1) or 1
    sm=max(ss.values(),default=1) or 1
    sc={}
    for i in ctx.valid:
        if ctx.units[i]['kind']=='heading': continue
        h=ctx.units[i]['heading']
        v=u.get(i,0)/mx + lam*(ss.get(h,0)/sm if h else 0)
        if v>0: sc[i]=v
    return sc
if __name__=='__main__':
    for lam in (0.0,0.25,0.5,1.0):
        show(f'jerarquico lam={lam}',lambda c,q,l=lam:hier(c,q,l))

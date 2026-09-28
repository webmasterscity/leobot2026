import sys, json, math, collections, itertools
sys.path.insert(0,'.')
from experiments.g57_kiosco import businesses, plain
from experiments.nube_recuperacion import containing
from leobot import Bot

BASE='/home/user/leobot2026/.leobot-data/base_general_nube.json'
K1,B=1.2,0.75

class Ctx:
    def __init__(s, bot):
        s.bot=bot; s.units=bot.context_units
        s.seq=[bot.context_terms(u['text']) for u in s.units]
        s.inh=[list(u.get('inherited',())) for u in s.units]
        s.valid=[i for i,u in enumerate(s.units) if u['kind']!='question']
        s.N=len(s.units)
        s.df=collections.Counter()
        for i in s.valid:
            for t in set(s.seq[i])|set(s.inh[i]): s.df[t]+=1
        s.len=[max(1,len(s.seq[i])) for i in range(s.N)]
        s.avg=sum(s.len[i] for i in s.valid)/max(1,len(s.valid))
        s.title=set(getattr(bot,'context_title',()))
    def idf(s,t):
        n=s.df.get(t,0)
        return math.log(1+(len(s.valid)-n+0.5)/(n+0.5))

def bm25(ctx,q,w_inh=1.0,k1=K1,b=B):
    sc={}
    for t in dict.fromkeys(q):
        if t in ctx.title: continue
        idf=ctx.idf(t)
        for i in ctx.valid:
            tf=ctx.seq[i].count(t)+w_inh*(1 if t in ctx.inh[i] and t not in ctx.seq[i] else 0)
            if tf:
                sc[i]=sc.get(i,0)+idf*tf*(k1+1)/(tf+k1*(1-b+b*ctx.len[i]/ctx.avg))
    return sc

def coverage(ctx,q,i):
    tot=0;hit=0
    for t in dict.fromkeys(q):
        if t in ctx.title: continue
        w=ctx.idf(t) if ctx.df.get(t,0)>0 else 0
        # weight also terms absent from doc? they can't be matched; count with mean idf
        tot+=w if w else 0
        if t in ctx.seq[i] or t in ctx.inh[i]: hit+=w
    return hit/tot if tot else 0

def bigram_bonus(ctx,q,i):
    s=ctx.seq[i]; c=0
    pairs=set(zip(q,q[1:]))
    for a,b in zip(s,s[1:]):
        if (a,b) in pairs: c+=1
    return c

def window(ctx,q,i):
    qs=set(q)&(set(ctx.seq[i]))
    if len(qs)<2: return 0
    pos=[k for k,t in enumerate(ctx.seq[i]) if t in qs]
    # minimal span containing all distinct matched
    need=len(qs); best=10**9; cnt=collections.Counter(); l=0
    for r,k in enumerate(pos):
        cnt[ctx.seq[i][k]]+=1
        while len(cnt)==need:
            best=min(best,k-pos[l]+1)
            t=ctx.seq[i][pos[l]]; cnt[t]-=1
            if cnt[t]==0: del cnt[t]
            l+=1
    return need/best if best<10**9 else 0

def run(scorer, folders, kinds=('directa','si_no')):
    bot=Bot.load(BASE)
    res=collections.defaultdict(lambda:[0,0,0,0])
    for name,text,ins,convs in businesses(folders):
        bot.load_context(text,ins); ctx=Ctx(bot)
        for conv in convs:
            for t in conv:
                if t.get('accion','responder')!='responder': continue
                keys=[k for k in t.get('claves') or [] if plain(k)]
                if not keys or t.get('tipo') not in kinds: continue
                gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                if not gold: continue
                q=bot.context_terms(t['cliente'])
                sc=scorer(ctx,q)
                order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
                first=min(order.index(g) for g in gold)
                r=res[t['tipo']]; r[0]+=1; r[1]+=first<1; r[2]+=first<3; r[3]+=first<5
    n=sum(r[0] for r in res.values())
    return n, [sum(r[j] for r in res.values())/n for j in (1,2,3)]

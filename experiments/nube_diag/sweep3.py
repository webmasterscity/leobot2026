import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep import *
from sweep2 import lcp, related, soft_bm25, leaves, DEV, VAL, show
import collections
bot0=Bot.load(BASE)
syn=collections.defaultdict(set); members=collections.defaultdict(set)
for line in open('/home/user/leobot2026/.leobot-data/wn-data-spa.tab',encoding='utf8'):
    if line.startswith('#'): continue
    f=line.rstrip('\n').split('\t')
    if len(f)<3 or f[1]!='spa:lemma': continue
    lemma=f[2]
    if '_' in lemma or ' ' in lemma: continue
    t=bot0._term(lemma)
    syn[t].add(f[0]); members[f[0]].add(t)
print('lemmas',len(syn),'synsets',len(members))
def synonyms(t):
    out=collections.Counter()
    for s in syn.get(t,()):
        n=len(members[s])
        for m in members[s]:
            if m!=t: out[m]+=1.0/ (1+0.0*n)
    return out
def wn_bm25(ctx,q,wsyn=0.4,w_inh=0.5,soft=True,minp=4,ratio=0.6,maxsyn=8):
    base=soft_bm25(ctx,q,minp if soft else 99,ratio,w_inh,True)
    sc=dict(base)
    for t in dict.fromkeys(q):
        if t in ctx.title: continue
        sy=synonyms(t)
        for r,_ in list(sy.items())[:maxsyn]:
            if ctx.df.get(r,0)==0 or r in q: continue
            idf=ctx.idf(r)
            for i in ctx.valid:
                if ctx.units[i]['kind']=='heading': continue
                tf=ctx.seq[i].count(r)+(w_inh if r in ctx.inh[i] and r not in ctx.seq[i] else 0)
                if tf: sc[i]=sc.get(i,0)+wsyn*idf*tf*(K1+1)/(tf+K1*(1-B+B*ctx.len[i]/ctx.avg))
    return sc
if __name__=='__main__':
    show('soft (referencia)',lambda c,q:soft_bm25(c,q,4,0.6,0.5,True))
    for w in (0.2,0.4,0.7):
        show(f'soft + wordnet sinónimos w={w}',lambda c,q,w=w:wn_bm25(c,q,w))

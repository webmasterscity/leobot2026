import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep5 import *
from sweep2 import lcp
def mix2(ctx,q,question='',soft=(4,0.6,1.0),heading_prior=True,inherit=True,bridge_on=True,cls=True,titlefix=True):
    bot=ctx.bot; units=ctx.units
    postings=bot._index(); total=len(units); bridge=bot._bridge() if bridge_on else {}; title=ctx.title
    vocab=list(postings.keys())
    gains={}
    for t in dict.fromkeys(q):
        delta=min(max(bot._delta(t),0.0),1-1e-4)
        p0=(len(postings.get(t,()))+0.5)/(total+1)
        absent=0.0 if t in title else math.log(1-delta)
        best={}
        for i in postings.get(t,()):
            best[i]=math.log(delta/p0+1-delta)-absent
        if soft:
            minp,ratio,w=soft
            if t not in title:
                for r in vocab:
                    if r==t: continue
                    p=lcp(t,r)
                    if p>=minp and p/max(len(t),len(r))>=ratio:
                        d=delta*w*(p/max(len(t),len(r)))
                        pr=(len(postings.get(r,()))+0.5)/(total+1)
                        g=math.log(d/pr+1-d)-absent
                        for i in postings[r]:
                            if i not in best or best[i]<g: best[i]=g
        for a,d_a in bridge.get(t,()):
            pa0=(len(postings.get(a,()))+0.5)/(total+1)
            g=math.log(d_a/pa0+1-d_a)
            for i in postings.get(a,()):
                if i not in best or best[i]<g: best[i]=g
        for i,g in best.items(): gains[i]=gains.get(i,0.0)+g
    asked=bot._asked_class(question) if (question and cls) else None
    if asked is not None:
        c,share=asked; share=min(share,1-1e-4)
        having=[i for i,u in enumerate(units) if c in u.get('classes',()) and u['kind'] not in ('question','heading')]
        p0=(len(having)+0.5)/(total+1); absent=math.log(1-share)
        for i in having: gains[i]=gains.get(i,0.0)+math.log(share/p0+1-share)-absent
    if heading_prior:
        for i in list(gains):
            if units[i]['kind']=='heading': del gains[i]
    return gains
if __name__=='__main__':
    def runq(scorer, folders, kinds=('directa','si_no')):
        bot=Bot.load(BASE); res=collections.defaultdict(lambda:[0,0,0,0])
        for name,text,ins,convs in businesses(folders):
            bot.load_context(text,ins); ctx=Ctx(bot)
            for conv in convs:
                for t in conv:
                    if t.get('accion','responder')!='responder': continue
                    keys=[k for k in t.get('claves') or [] if plain(k)]
                    if not keys or t.get('tipo') not in kinds: continue
                    gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                    if not gold: continue
                    q=bot.context_terms(t['cliente']); sc=scorer(ctx,q,t['cliente'])
                    order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
                    first=min(order.index(g) for g in gold)
                    r=res[t['tipo']]; r[0]+=1; r[1]+=first<1; r[2]+=first<3; r[3]+=first<5
        n=sum(r[0] for r in res.values())
        return n,[sum(r[j] for r in res.values())/n for j in (1,2,3)]
    def show2(name,sc):
        out=[]
        for label,fs in (('dev',DEV),('val3',VAL3)):
            n,(a,b,c)=runq(sc,fs); out.append(f'{label} n={n} top1={a:.3f} top3={b:.3f} top5={c:.3f}')
        print(f'{name:34s} '+' | '.join(out),flush=True)
    show2('mezcla real',lambda c,q,qq:mix2(c,q,qq,soft=None,heading_prior=False))
    show2('sin encabezados',lambda c,q,qq:mix2(c,q,qq,soft=None,heading_prior=True))
    show2('+prefijo 4/.6',lambda c,q,qq:mix2(c,q,qq,soft=(4,0.6,1.0),heading_prior=True))
    show2('+prefijo 3/.5',lambda c,q,qq:mix2(c,q,qq,soft=(3,0.5,1.0),heading_prior=True))
    show2('+prefijo 4/.6 w.7',lambda c,q,qq:mix2(c,q,qq,soft=(4,0.6,0.7),heading_prior=True))

import sys; sys.path.insert(0,'experiments/nube_diag')
import sweep
sweep.BASE='/home/user/leobot2026/.leobot-data/base_kiosco_nube.json'
from sweep import *
import glob,os
def leaves(banks): return sorted({os.path.dirname(os.path.dirname(f)) for b in banks for f in glob.glob(f'results_v3/kiosco/{b}/**/conversaciones.json',recursive=True)})
DEV=['results_v3/kiosco/desarrollo/'+c for c in 'ABCDEF']
VAL3=leaves(['congelado_g62','congelado_g63','congelado_g64'])
def show(name,sc,sets=(('dev',DEV),('val3',VAL3))):
    out=[]
    for label,fs in sets:
        n,(a,b,c)=run(sc,fs); out.append(f'{label} n={n} top1={a:.3f} top3={b:.3f} top5={c:.3f}')
    print(f'{name:36s} '+' | '.join(out),flush=True)

def mixture_full(ctx,q,question=''):
    bot=ctx.bot; units=ctx.units
    postings=bot._index(); total=len(units); bridge=bot._bridge(); title=ctx.title
    gains={}
    for t in dict.fromkeys(q):
        delta=min(max(bot._delta(t),0.0),1-1e-4)
        p0=(len(postings.get(t,()))+0.5)/(total+1)
        absent=0.0 if t in title else math.log(1-delta)
        best={}
        for i in postings.get(t,()):
            best[i]=math.log(delta/p0+1-delta)-absent
        for a,d_a in bridge.get(t,()):
            pa0=(len(postings.get(a,()))+0.5)/(total+1)
            g=math.log(d_a/pa0+1-d_a)
            for i in postings.get(a,()):
                if i not in best or best[i]<g: best[i]=g
        for i,g in best.items(): gains[i]=gains.get(i,0.0)+g
    asked=bot._asked_class(question) if question else None
    if asked is not None:
        cls,share=asked; share=min(share,1-1e-4)
        having=[i for i,u in enumerate(units) if cls in u.get('classes',()) and u['kind'] not in ('question','heading')]
        p0=(len(having)+0.5)/(total+1); absent=math.log(1-share)
        for i in having: gains[i]=gains.get(i,0.0)+math.log(share/p0+1-share)-absent
    return gains
if __name__=='__main__':
    import sweep as S
    # run() passes only (ctx,q); need question text for class -> wrap
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
    for label,fs in (('dev',DEV),('val3',VAL3)):
        for name,sc in (('mezcla real (delta+puente+clase)',lambda c,q,qq:mixture_full(c,q,qq)),
                        ('mezcla sin clase',lambda c,q,qq:mixture_full(c,q,'')),
                        ('bm25 crudo',lambda c,q,qq:bm25(c,q,0.5))):
            n,(a,b,cc)=runq(sc,fs); print(f'{label} {name:34s} n={n} top1={a:.3f} top3={b:.3f} top5={cc:.3f}',flush=True)

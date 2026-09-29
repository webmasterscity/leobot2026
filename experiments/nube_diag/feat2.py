import sys; sys.path.insert(0,'experiments/nube_diag')
import io, contextlib, pickle
with contextlib.redirect_stdout(io.StringIO()):
    from sweep6 import *
K=8
def extract(folders, tag):
    bot=Bot.load(BASE); rows=[]
    for name,text,ins,convs in businesses(folders):
        bot.load_context(text,ins); ctx=Ctx(bot)
        for ci,conv in enumerate(convs):
            for ti,t in enumerate(conv):
                act=t.get('accion','responder')
                if act!='responder' or t.get('tipo') not in ('directa','si_no'): continue
                keys=[k for k in t.get('claves') or [] if plain(k)]
                if not keys: continue
                gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                if not gold: continue
                _,qtext=bot._question_part(t['cliente'])
                q=list(dict.fromkeys(bot.context_terms(qtext)))
                if not q: continue
                sc=mix2(ctx,q,qtext,soft=(3,0.5,1.0))
                order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))[:K]
                deltas={x:min(max(bot._delta(x),0),1) for x in q}
                mass=sum(deltas.values()) or 1e-9
                bm=bm25(ctx,q,0.5)
                bmax=max(bm.values(),default=1) or 1
                cands=[]
                for r,i in enumerate(order):
                    u=ctx.units[i]
                    own=[x for x in q if x in ctx.seq[i]]; inh=[x for x in q if x in ctx.inh[i] and x not in ctx.seq[i]]
                    unm=[deltas[x] for x in q if x not in own and x not in inh]
                    f=dict(rank=r,s=sc.get(i,0),gap0=sc.get(order[0],0)-sc.get(i,0),bm=bm.get(i,0)/bmax,
                           nown=len(own),ninh=len(inh),fown=len(own)/len(q),
                           mown=sum(deltas[x] for x in own)/mass,minh=sum(deltas[x] for x in inh)/mass,
                           unmax=max(unm,default=0),unsum=sum(unm),
                           ulen=len(u['text'].split()),kind={'line':0,'sentence':1,'item':2,'row':3,'heading':4}.get(u['kind'],5),
                           ndig=sum(c.isdigit() for c in u['text']),hashead=int(bool(u['heading'])),
                           pos=i/len(ctx.units),nq=len(q))
                    cands.append((f,int(i in gold)))
                rows.append((tag+'/'+name,cands))
    return rows
if __name__=='__main__':
    banks=['desarrollo','congelado','congelado_g58','congelado_g59','congelado_g60','congelado_g61','congelado_g62','congelado_g63','congelado_g64']
    allrows=[]
    for b in banks:
        fs=DEV if b=='desarrollo' else leaves([b])
        allrows+=extract(fs,b); print(b,len(allrows),flush=True)
    pickle.dump(allrows,open('experiments/nube_diag/feat2.pkl','wb'))

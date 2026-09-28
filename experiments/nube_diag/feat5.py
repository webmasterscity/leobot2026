import sys; sys.path.insert(0,'experiments/nube_diag')
import io, contextlib, pickle
with contextlib.redirect_stdout(io.StringIO()):
    from sweep6 import *
K=8
import re
def shapes(text):
    out=set()
    for w in text.split():
        if any(c.isdigit() for c in w) or any(c in '$€@%+:/#' for c in w):
            sh=re.sub(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]+','a',re.sub(r'\d+','d',w.strip('.,;()')))
            out.add('SH:'+sh[:8])
    return sorted(out)
KIND={'line':0,'sentence':1,'item':2,'row':3,'heading':4}
def extract(folders, tag):
    bot=Bot.load(BASE); rows=[]
    for name,text,ins,convs in businesses(folders):
        bot.load_context(text,ins); ctx=Ctx(bot)
        for ci,conv in enumerate(convs):
            prev=None
            for ti,t in enumerate(conv):
                act=t.get('accion','responder')
                _,qtext=bot._question_part(t['cliente'])
                q=list(dict.fromkeys(bot.context_terms(qtext)))
                if act=='charla' or not q: prev=q or prev; continue
                keys=[k for k in t.get('claves') or [] if plain(k)]
                gold=set()
                if act=='responder' and keys:
                    gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                sc=mix2(ctx,q,qtext,soft=(3,0.5,1.0))
                order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))[:K]
                deltas={x:min(max(bot._delta(x),0),1) for x in q}
                mass=sum(deltas.values()) or 1e-9
                bm=bm25(ctx,q,0.5); bmax=max(bm.values(),default=1) or 1
                ranked=bot._rank(q,qtext)
                top=sc.get(order[0],0) if order else 0
                cands=[]
                for r,i in enumerate(order):
                    u=ctx.units[i]
                    own=[x for x in q if x in ctx.seq[i]]; inh=[x for x in q if x in ctx.inh[i] and x not in ctx.seq[i]]
                    unm=[deltas[x] for x in q if x not in own and x not in inh]
                    f=dict(rank=r,s=sc.get(i,0),gap0=top-sc.get(i,0),bm=bm.get(i,0)/bmax,
                           nown=len(own),ninh=len(inh),fown=len(own)/len(q),
                           mown=sum(deltas[x] for x in own)/mass,minh=sum(deltas[x] for x in inh)/mass,
                           unmax=max(unm,default=0),unsum=sum(unm),
                           ulen=len(u['text'].split()),kind=KIND.get(u['kind'],5),
                           ndig=sum(c.isdigit() for c in u['text']),hashead=int(bool(u['heading'])),
                           pos=i/len(ctx.units),nq=len(q),mass=mass,
                           s2=(sc.get(order[1],0) if len(order)>1 else 0),
                           old_useful=(ranked['useful'] or 0) if (ranked and r==0) else 0)
                    cands.append((f,int(i in gold),sorted(set(ctx.seq[i])|set(ctx.inh[i])),q,shapes(u['text']),u['kind']))
                rows.append(dict(biz=tag+'/'+name,tipo=t.get('tipo'),act=act,ans=int(act=='responder' and bool(gold)),
                                 unans=int(act in ('abstenerse','derivar')),cands=cands))
                prev=q
    return rows
if __name__=='__main__':
    banks=['desarrollo','congelado','congelado_g58','congelado_g59','congelado_g60','congelado_g61','congelado_g62','congelado_g63','congelado_g64']
    allrows=[]
    for b in banks:
        fs=DEV if b=='desarrollo' else leaves([b])
        allrows+=extract(fs,b); print(b,len(allrows),flush=True)
    pickle.dump(allrows,open('experiments/nube_diag/feat5.pkl','wb'))

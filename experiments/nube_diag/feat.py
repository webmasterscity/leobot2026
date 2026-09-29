import sys; sys.path.insert(0,'experiments/nube_diag')
import io, contextlib, pickle, os
with contextlib.redirect_stdout(io.StringIO()):
    from sweep6 import *
def extract(folders, tag):
    bot=Bot.load(BASE); rows=[]
    for name,text,ins,convs in businesses(folders):
        bot.load_context(text,ins); ctx=Ctx(bot)
        for ci,conv in enumerate(convs):
            for ti,t in enumerate(conv):
                act=t.get('accion','responder')
                if act=='charla': continue
                keys=[k for k in t.get('claves') or [] if plain(k)]
                _,qtext=bot._question_part(t['cliente'])
                q=list(dict.fromkeys(bot.context_terms(qtext)))
                if not q: continue
                ranked=bot._rank(q,qtext)
                if ranked is None or ranked['unit'] is None: continue
                sc=mix2(ctx,q,qtext,soft=(3,0.5,1.0))
                order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
                gold=set()
                if act=='responder' and keys:
                    gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                s=[sc.get(i,0) for i in order[:3]]+[0,0,0]
                u=ctx.units[order[0]]
                deltas=[min(max(bot._delta(x),0),1) for x in q]
                matched=[x for x in q if x in ctx.seq[order[0]] or x in ctx.inh[order[0]]]
                unm=[min(max(bot._delta(x),0),1) for x in q if x not in matched]
                mass=sum(deltas) or 1e-9
                f=dict(
                  s1=s[0], s2=s[1], s3=s[2], gap12=s[0]-s[1], gap13=s[0]-s[2], rel12=(s[0]-s[1])/(abs(s[0])+1e-9),
                  useful=ranked['useful'] or 0, un=ranked['unaddressed'], cov=ranked['covered'], mar=ranked['margin'],
                  nq=len(q), nmatch=len(matched), fmatch=len(matched)/len(q), mass=mass, mmass=sum(deltas[i] for i,x in enumerate(q) if x in matched)/mass,
                  unmax=max(unm,default=0), unsum=sum(unm), nunm=len(unm),
                  ulen=len(u['text'].split()), ukind={'line':0,'sentence':1,'item':2,'row':3,'heading':4}.get(u['kind'],5),
                  ndig=sum(c.isdigit() for c in u['text']), hasHead=int(bool(u['heading'])),
                  same12=int(ctx.units[order[0]]['heading']==ctx.units[order[1]]['heading']) if len(order)>1 else 0,
                  wh=int(ranked['features']['form']=='wh'), cls_hit=int(ranked['features']['cls'].endswith((':1',':2'))),
                  nunits=len(ctx.valid))
                rows.append(dict(f=f,y1=int(bool(order and order[0] in gold)),y3=int(bool(gold&set(order[:3]))),
                                 ans=int(act=='responder' and bool(gold)),unans=int(act in ('abstenerse','derivar')),
                                 tipo=t.get('tipo'),biz=tag+'/'+name))
    return rows
if __name__=='__main__':
    import glob
    banks=['desarrollo']+['congelado','congelado_g58','congelado_g59','congelado_g60','congelado_g61','congelado_g62','congelado_g63','congelado_g64']
    allrows=[]
    for b in banks:
        fs=DEV if b=='desarrollo' else leaves([b])
        r=extract(fs,b); allrows+=r; print(b,len(r),flush=True)
    pickle.dump(allrows,open('experiments/nube_diag/feat.pkl','wb'))

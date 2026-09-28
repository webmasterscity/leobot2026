import sys; sys.path.insert(0,'experiments/nube_diag')
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    from sweep6 import *
import json
def collect(folders):
    bot=Bot.load(BASE); rows=[]
    for name,text,ins,convs in businesses(folders):
        bot.load_context(text,ins); ctx=Ctx(bot)
        for conv in convs:
            for t in conv:
                act=t.get('accion','responder')
                if act=='charla': continue
                keys=[k for k in t.get('claves') or [] if plain(k)]
                _,qtext=bot._question_part(t['cliente'])
                q=bot.context_terms(qtext)
                if not q: continue
                ranked=bot._rank(q,qtext)
                if ranked is None: continue
                sc=mix2(ctx,q,qtext,soft=(3,0.5,1.0))
                order=sorted(ctx.valid,key=lambda i:(-sc.get(i,0),i))
                gold=set()
                if act=='responder' and keys:
                    gold={i for i in ctx.valid if containing(ctx.units[i]['text'],keys)}
                rows.append({'tipo':t.get('tipo'),'act':act,'has_gold':bool(gold),
                             'top1':bool(order and order[0] in gold),'top3':bool(gold & set(order[:3])),
                             'useful':ranked['useful'],'un':ranked['unaddressed'],'cov':ranked['covered'],'mar':ranked['margin'],
                             'score':sc.get(order[0],0) if order else 0})
    return rows
def auc(pos,neg):
    # pos, neg lists of scores
    allv=sorted([(v,1) for v in pos]+[(v,0) for v in neg]); 
    rank=0; s=0.0; i=0
    n=len(allv)
    ranks=[0]*n
    while i<n:
        j=i
        while j<n and allv[j][0]==allv[i][0]: j+=1
        for k in range(i,j): ranks[k]=(i+j+1)/2
        i=j
    sp=sum(r for r,(v,l) in zip(ranks,allv) if l==1)
    return (sp-len(pos)*(len(pos)+1)/2)/(len(pos)*len(neg))
for label,fs in (('val3',VAL3),):
    rows=collect(fs)
    ans=[r for r in rows if r['act']=='responder' and r['has_gold']]
    unans=[r for r in rows if r['act'] in ('abstenerse','derivar')]
    print(label,'answerable',len(ans),'top1 ok',sum(r['top1'] for r in ans),'top3 ok',sum(r['top3'] for r in ans),'unans',len(unans))
    for feat in ('useful','score','cov','mar'):
        pos=[r[feat] or 0 for r in ans if r['top1']]; neg=[r[feat] or 0 for r in unans]
        neg2=[r[feat] or 0 for r in ans if not r['top1']]
        print(f' AUC {feat}: top1-correct vs unanswerable {auc(pos,neg):.3f} | top1-correct vs top1-wrong {auc(pos,neg2):.3f}')
    # TPR at FPR on unanswerable
    for feat in ('useful','score'):
        negs=sorted([r[feat] or 0 for r in unans],reverse=True)
        for fpr in (0.02,0.05,0.10,0.20):
            thr=negs[int(fpr*len(negs))] if int(fpr*len(negs))<len(negs) else -1
            tpr1=sum(1 for r in ans if r['top1'] and (r[feat] or 0)>thr)/len(ans)
            tpr3=sum(1 for r in ans if r['top3'] and (r[feat] or 0)>thr)/len(ans)
            print(f' {feat} fpr={fpr:.2f}: answerable quoted correct(top1)={tpr1:.3f}  gold-in-top3 shown={tpr3:.3f}')

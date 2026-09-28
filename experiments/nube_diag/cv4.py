import sys; sys.path.insert(0,'./pylibs')
import pickle, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
rows=pickle.load(open('feat3.pkl','rb'))
rows=[r for r in rows if (r['ans'] or r['unans']) and r['cands']]
names=[n for n in rows[0]['cands'][0][0].keys() if n!='old_useful']
X=[];y=[];q=[]
for qi,r in enumerate(rows):
    for f,l in r['cands']:
        X.append([f[n] for n in names]); y.append(l); q.append(qi)
X=np.array(X,float); y=np.array(y); q=np.array(q)
qb=np.array([r['biz'] for r in rows]); cg=qb[q]
first=np.array([qi for qi in range(len(rows))])
def evaluate(P, label):
    # P per candidate; per query pick argmax
    n=len(rows); top_ok=np.zeros(n,bool); conf=np.zeros(n)
    idx=np.searchsorted(q,np.arange(n)); 
    for qi in range(n):
        m=np.where(q==qi)[0]
        j=m[np.argmax(P[m])]; conf[qi]=P[j]; top_ok[qi]=y[j]==1
    ans=np.array([r['ans'] for r in rows],bool); un=np.array([r['unans'] for r in rows],bool)
    negs=np.sort(conf[un])[::-1]; out=[]
    for fpr in (0.02,0.05,0.10,0.20):
        thr=negs[int(fpr*len(negs))]; out.append(f'{fpr:.2f}: {((conf>thr)&top_ok&ans).sum()/ans.sum():.3f}')
    from sklearn.metrics import roc_auc_score
    m=(top_ok&ans)|un; auc=roc_auc_score((top_ok&ans)[m],conf[m])
    print(f'{label:26s} top1(answerable)={top_ok[ans].mean():.3f} AUC={auc:.3f} | útiles/respondibles a FPR '+' | '.join(out))
# baseline: rank0 candidate + old NB confidence
oldconf=np.array([[f['old_useful'] for f,l in r['cands']] for r in rows],dtype=object)
Pold=np.array([f['old_useful'] if f['rank']==0 else -1 for r in rows for f,l in r['cands']],float)
evaluate(Pold,'actual: mezcla + NB')
gkf=GroupKFold(5)
def cv(fn):
    P=np.zeros(len(y))
    for tr,te in gkf.split(X,y,cg):
        m=fn(); m.fit(X[tr],y[tr]); P[te]=m.predict_proba(X[te])[:,1]
    return P
evaluate(cv(lambda:make_pipeline(StandardScaler(),LogisticRegression(max_iter=5000,C=0.3))),'LR unificado')
evaluate(cv(lambda:GradientBoostingClassifier(n_estimators=150,max_depth=3,learning_rate=0.05,subsample=0.8,random_state=0)),'GBM unificado')

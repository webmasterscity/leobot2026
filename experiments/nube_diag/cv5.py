import sys; sys.path.insert(0,'experiments/nube_diag/pylibs')
import pickle, numpy as np, scipy.sparse as sp
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction import FeatureHasher
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
rows=pickle.load(open('feat4.pkl','rb'))
rows=[r for r in rows if (r['ans'] or r['unans']) and r['cands']]
names=[n for n in rows[0]['cands'][0][0].keys() if n!='old_useful']
X=[];y=[];q=[];pairs=[]
for qi,r in enumerate(rows):
    for f,l,ut,qt in r['cands']:
        X.append([f[n] for n in names]); y.append(l); q.append(qi)
        us=set(ut)
        pairs.append([a+'|'+b for a in qt if a not in us for b in ut if b!=a])
X=np.array(X,float); y=np.array(y); q=np.array(q); cg=np.array([r['biz'] for r in rows])[q]
H=FeatureHasher(n_features=2**18,input_type='string',alternate_sign=False)
XP=H.transform(pairs); XP.data[:]=1.0
print('pair nnz mean',XP.getnnz()/XP.shape[0])
ans=np.array([r['ans'] for r in rows],bool); un=np.array([r['unans'] for r in rows],bool)
def evaluate(P,label):
    n=len(rows); top_ok=np.zeros(n,bool); conf=np.zeros(n)
    order=np.argsort(q,kind='stable'); bounds=np.searchsorted(q[order],np.arange(n+1))
    for qi in range(n):
        m=order[bounds[qi]:bounds[qi+1]]; j=m[np.argmax(P[m])]; conf[qi]=P[j]; top_ok[qi]=y[j]==1
    negs=np.sort(conf[un])[::-1]; out=[]
    for fpr in (0.02,0.05,0.10,0.20):
        thr=negs[int(fpr*len(negs))]; out.append(f'{fpr:.2f}: {((conf>thr)&top_ok&ans).sum()/ans.sum():.3f}')
    m=(top_ok&ans)|un; auc=roc_auc_score((top_ok&ans)[m],conf[m])
    print(f'{label:30s} top1(answerable)={top_ok[ans].mean():.3f} AUC={auc:.3f} | '+' | '.join(out),flush=True)
gkf=GroupKFold(5)
sc=StandardScaler()
def cv(use_pairs,C=0.3,Cp=1.0):
    P=np.zeros(len(y))
    for tr,te in gkf.split(X,y,cg):
        s=StandardScaler().fit(X[tr]); Xa=sp.csr_matrix(s.transform(X))
        if use_pairs:
            # column filter: pairs seen in >=3 training candidates
            cnt=np.asarray((XP[tr]>0).sum(0)).ravel(); keep=np.where(cnt>=3)[0]
            Z=sp.hstack([Xa,XP[:,keep]*0.5]).tocsr()
        else: Z=Xa
        m=LogisticRegression(max_iter=3000,C=C); m.fit(Z[tr],y[tr]); P[te]=m.predict_proba(Z[te])[:,1]
    return P
evaluate(cv(False),'LR densas')
evaluate(cv(True,0.3),'LR densas + pares (C=.3)')
evaluate(cv(True,0.1),'LR densas + pares (C=.1)')

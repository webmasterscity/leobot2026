import sys; sys.path.insert(0,'experiments/nube_diag/pylibs')
import pickle, numpy as np, scipy.sparse as sp
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction import FeatureHasher
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
rows=pickle.load(open('feat5.pkl','rb'))
rows=[r for r in rows if (r['ans'] or r['unans']) and r['cands']]
names=[n for n in rows[0]['cands'][0][0].keys() if n!='old_useful']
X=[];y=[];q=[];P1=[];P2=[];P3=[]
for qi,r in enumerate(rows):
    for f,l,ut,qt,sh,kind in r['cands']:
        X.append([f[n] for n in names]); y.append(l); q.append(qi)
        us=set(ut)
        P1.append([a+'|'+b for a in qt if a not in us for b in ut if b!=a])
        P2.append([a+'|'+b for a in qt for b in sh])
        P3.append([a+'|K'+str(kind) for a in qt]+['K'+str(kind)+'|'+b for b in ut])
X=np.array(X,float); y=np.array(y); q=np.array(q); cg=np.array([r['biz'] for r in rows])[q]
def hm(lst):
    H=FeatureHasher(n_features=2**18,input_type='string',alternate_sign=False); M=H.transform(lst); M.data[:]=1.0; return M
M1,M2,M3=hm(P1),hm(P2),hm(P3)
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
    print(f'{label:34s} top1={top_ok[ans].mean():.3f} AUC={auc:.3f} | '+' | '.join(out),flush=True)
gkf=GroupKFold(5)
def cv(mats,C=0.3,w=0.5):
    P=np.zeros(len(y))
    for tr,te in gkf.split(X,y,cg):
        s=StandardScaler().fit(X[tr]); parts=[sp.csr_matrix(s.transform(X))]
        for M in mats:
            cnt=np.asarray((M[tr]>0).sum(0)).ravel(); keep=np.where(cnt>=3)[0]; parts.append(M[:,keep]*w)
        Z=sp.hstack(parts).tocsr()
        m=LogisticRegression(max_iter=3000,C=C); m.fit(Z[tr],y[tr]); P[te]=m.predict_proba(Z[te])[:,1]
    return P
evaluate(cv([M1]),'densas + pares léxicos')
evaluate(cv([M1,M2]),'+ pares con formas')
evaluate(cv([M1,M2,M3]),'+ pares con tipo de unidad')

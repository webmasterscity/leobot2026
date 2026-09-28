import sys; sys.path.insert(0,'./pylibs')
import pickle, numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
rows=pickle.load(open('feat.pkl','rb'))
# target: top1 correct answer (positive) vs unanswerable or wrong (negative) among answerable+unanswerable turns
data=[r for r in rows if r['ans'] or r['unans']]
names=list(data[0]['f'].keys())
X=np.array([[r['f'][n] for n in names] for r in data],float)
y=np.array([1 if (r['ans'] and r['y1']) else 0 for r in data])
g=np.array([r['biz'] for r in data])
isun=np.array([r['unans'] for r in data])
print('n',len(data),'pos',y.sum(),'unans',isun.sum())
def cv(model_fn,cols=None):
    P=np.zeros(len(y))
    for tr,te in GroupKFold(5).split(X,y,g):
        m=model_fn(); Xs=X if cols is None else X[:,cols]
        m.fit(Xs[tr],y[tr]); P[te]=m.predict_proba(Xs[te])[:,1]
    return P
base_cols=[names.index(n) for n in ('un','cov','mar','useful','s1')]
for label,fn,cols in (('useful only (as is)',None,None),
                      ('logreg 5 feats',lambda:LogisticRegression(max_iter=2000),base_cols),
                      ('logreg all',lambda:LogisticRegression(max_iter=5000,C=1.0),None),
                      ('GBM all',lambda:GradientBoostingClassifier(n_estimators=200,max_depth=3,learning_rate=0.05,subsample=0.8,random_state=0),None)):
    if fn is None:
        P=X[:,names.index('useful')]
    else:
        P=cv(fn,cols)
    a=roc_auc_score(y[~isun.astype(bool)|True],P) 
    # AUC: correct-top1 vs unanswerable only
    m=(y==1)|(isun==1); a_un=roc_auc_score(y[m],P[m])
    m2=(isun==0); a_wr=roc_auc_score(y[m2],P[m2])
    # TPR at FPR on unanswerable
    negs=np.sort(P[isun==1])[::-1]; out=[]
    for fpr in (0.02,0.05,0.10):
        thr=negs[int(fpr*len(negs))]; out.append(f'{fpr:.2f}:{((P>thr)&(y==1)).sum()/((y==1).sum()+0.0):.3f}')
    print(f'{label:22s} AUC all={a:.3f} vs-unans={a_un:.3f} vs-wrong-top1={a_wr:.3f} recall-of-correct@FPR {" ".join(out)}')

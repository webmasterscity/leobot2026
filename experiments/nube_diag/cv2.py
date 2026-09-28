import sys; sys.path.insert(0,'./pylibs')
import pickle, numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
rows=pickle.load(open('feat2.pkl','rb'))
names=list(rows[0][1][0][0].keys())
X=[];y=[];g=[];q=[]
for qi,(biz,cands) in enumerate(rows):
    for f,l in cands:
        X.append([f[n] for n in names]); y.append(l); g.append(biz); q.append(qi)
X=np.array(X,float); y=np.array(y); g=np.array(g); q=np.array(q)
print('queries',len(rows),'cands',len(y))
def top1(P):
    ok=0; tot=0
    for qi in np.unique(q):
        m=q==qi
        if y[m].sum()==0: continue
        tot+=1; ok+=y[m][np.argmax(P[m])]
    return ok/tot
print('mezcla (rank 0):',top1(-X[:,names.index('rank')]))
gkf=GroupKFold(5)
def cvp(fn,cols=None):
    P=np.zeros(len(y)); Xs=X if cols is None else X[:,cols]
    for tr,te in gkf.split(Xs,y,g):
        m=fn(); m.fit(Xs[tr],y[tr]); P[te]=m.predict_proba(Xs[te])[:,1]
    return P
print('logreg all:',top1(cvp(lambda:LogisticRegression(max_iter=5000))))
print('GBM all   :',top1(cvp(lambda:GradientBoostingClassifier(n_estimators=200,max_depth=3,learning_rate=0.05,subsample=0.8,random_state=0))))
print('GBM no bm :',top1(cvp(lambda:GradientBoostingClassifier(n_estimators=200,max_depth=3,learning_rate=0.05,subsample=0.8,random_state=0),[i for i,n in enumerate(names) if n!='bm'])))

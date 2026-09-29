import sys; sys.path.insert(0,'./pylibs')
import pickle, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
rows=pickle.load(open('feat.pkl','rb'))
data=[r for r in rows if r['ans'] or r['unans']]
names=list(data[0]['f'].keys())
X=np.array([[r['f'][n] for n in names] for r in data],float)
y=np.array([1 if (r['ans'] and r['y1']) else 0 for r in data]); g=np.array([r['biz'] for r in data])
isun=np.array([r['unans'] for r in data]); ans=np.array([r['ans'] for r in data])
tipo=np.array([r['tipo'] for r in data])
for label,fn in (('LR',lambda:make_pipeline(StandardScaler(),LogisticRegression(max_iter=5000,C=0.3))),
                 ('GBM',lambda:GradientBoostingClassifier(n_estimators=200,max_depth=3,learning_rate=0.05,subsample=0.8,random_state=0))):
    P=np.zeros(len(y))
    for tr,te in GroupKFold(5).split(X,y,g):
        m=fn(); m.fit(X[tr],y[tr]); P[te]=m.predict_proba(X[te])[:,1]
    print(label)
    tot_ans=(ans==1).sum(); tot_un=(isun==1).sum()
    for thr in (0.3,0.4,0.5,0.6,0.7,0.8,0.9):
        sel=P>=thr
        q_ans=(sel&(ans==1)).sum(); q_ok=(sel&(y==1)).sum(); q_un=(sel&(isun==1)).sum()
        print(f'  p>={thr}: quotes={sel.sum():4d}  useful={q_ok:4d} ({q_ok/tot_ans:.3f} of answerable)  precision={q_ok/max(1,sel.sum()):.3f}  on-unanswerable={q_un} ({q_un/tot_un:.3f})')
print('--- útiles entre respondibles, a igual tasa de citas sobre lo no respondible ---')
Ps={}
Ps['actual (NB+isotónica)']=X[:,names.index('useful')]
for label,fn in (('LR 25 rasgos',lambda:make_pipeline(StandardScaler(),LogisticRegression(max_iter=5000,C=0.3))),):
    P=np.zeros(len(y))
    for tr,te in GroupKFold(5).split(X,y,g):
        m=fn(); m.fit(X[tr],y[tr]); P[te]=m.predict_proba(X[te])[:,1]
    Ps[label]=P
tot_ans=(ans==1).sum()
for label,P in Ps.items():
    negs=np.sort(P[isun==1])[::-1]; out=[]
    for fpr in (0.02,0.05,0.10,0.20):
        thr=negs[int(fpr*len(negs))]; sel=P>thr
        out.append(f'{fpr:.2f}: útiles {(sel&(y==1)).sum()/tot_ans:.3f}')
    print(f'{label:24s}',' | '.join(out))

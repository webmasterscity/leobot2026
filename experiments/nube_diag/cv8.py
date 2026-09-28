import sys; sys.path.insert(0,'experiments/nube_diag/pylibs')
exec(open('cv7.py').read().split("gkf=GroupKFold(5)")[0])
bank=np.array([r['biz'].split('/')[0] for r in rows])[q]
banks=['desarrollo','congelado','congelado_g58','congelado_g59','congelado_g60','congelado_g61','congelado_g62','congelado_g63','congelado_g64']
def fit_predict(tr,te,mats,C=0.3,w=0.5):
    s=StandardScaler().fit(X[tr]); parts=[sp.csr_matrix(s.transform(X))]
    for M in mats:
        cnt=np.asarray((M[tr]>0).sum(0)).ravel(); keep=np.where(cnt>=3)[0]; parts.append(M[:,keep]*w)
    Z=sp.hstack(parts).tocsr(); m=LogisticRegression(max_iter=3000,C=C); m.fit(Z[tr],y[tr]); return m.predict_proba(Z[te])[:,1]
# leave-one-bank-out
P=np.zeros(len(y)); Pd=np.zeros(len(y))
for b in banks:
    te=np.where(bank==b)[0]; tr=np.where(bank!=b)[0]
    P[te]=fit_predict(tr,te,[M1]); Pd[te]=fit_predict(tr,te,[])
evaluate(Pd,'LOBO: solo rasgos densos'); evaluate(P,'LOBO: + pares léxicos')
# temporal: train on earlier banks, test on last 3
P=np.zeros(len(y)); Pd=np.zeros(len(y))
tests=['congelado_g62','congelado_g63','congelado_g64']
tr=np.where(~np.isin(bank,tests))[0]; te=np.where(np.isin(bank,tests))[0]
Pd[te]=fit_predict(tr,te,[]); P[te]=fit_predict(tr,te,[M1])
# evaluate only on test rows: restrict arrays
import types
sel=np.array([r['biz'].split('/')[0] in tests for r in rows])
def evaluate_sel(P,label):
    n=len(rows); top_ok=np.zeros(n,bool); conf=np.zeros(n)
    order=np.argsort(q,kind='stable'); bounds=np.searchsorted(q[order],np.arange(n+1))
    for qi in range(n):
        if not sel[qi]: continue
        m=order[bounds[qi]:bounds[qi+1]]; j=m[np.argmax(P[m])]; conf[qi]=P[j]; top_ok[qi]=y[j]==1
    a=ans&sel; u=un&sel
    negs=np.sort(conf[u])[::-1]; out=[]
    for fpr in (0.02,0.05,0.10,0.20):
        thr=negs[int(fpr*len(negs))]; out.append(f'{fpr:.2f}: {((conf>thr)&top_ok&a).sum()/a.sum():.3f}')
    m=((top_ok&a)|u); auc=roc_auc_score((top_ok&a)[m],conf[m])
    print(f'{label:34s} top1={top_ok[a].mean():.3f} AUC={auc:.3f} | '+' | '.join(out),flush=True)
evaluate_sel(Pd,'TEMPORAL g62-64: densos'); evaluate_sel(P,'TEMPORAL g62-64: + pares')

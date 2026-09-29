import sys; sys.path.insert(0,'experiments/nube_diag/pylibs')
exec(open('cv5.py').read().split("gkf=GroupKFold(5)")[0])
import random
gkf=GroupKFold(5)
def cv_frac(frac,C=0.3,seed=0):
    P=np.zeros(len(y)); rng=random.Random(seed)
    for tr,te in gkf.split(X,y,cg):
        bs=sorted(set(cg[tr])); rng.shuffle(bs); keepb=set(bs[:max(5,int(frac*len(bs)))])
        tr2=np.array([i for i in tr if cg[i] in keepb])
        s=StandardScaler().fit(X[tr2]); Xa=sp.csr_matrix(s.transform(X))
        cnt=np.asarray((XP[tr2]>0).sum(0)).ravel(); keep=np.where(cnt>=2)[0]
        Z=sp.hstack([Xa,XP[:,keep]*0.5]).tocsr()
        m=LogisticRegression(max_iter=3000,C=C); m.fit(Z[tr2],y[tr2]); P[te]=m.predict_proba(Z[te])[:,1]
    return P
for frac in (0.1,0.25,0.5,0.75,1.0):
    print('fracción de negocios de entrenamiento',frac,'(~%d negocios)'%int(frac*172),end=' ')
    evaluate(cv_frac(frac),'')

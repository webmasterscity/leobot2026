"""Validación cruzada dejando fuera grupos de negocios de vocabulario parecido (sectores) en vez de negocios sueltos.

Usa feat5.pkl (rasgos de candidatas de los bancos gastados).  Agrupa los negocios por similitud de su texto (TF-IDF + k-medias)
y compara solo rasgos densos frente a densos + pares con validación cruzada por grupo de sector.
"""
import sys, os, re, pickle, glob
sys.path.insert(0, '/tmp/claude-0/-home-user-leobot2026/c6a07e9b-8d92-5cd1-afd1-d7a29379d968/scratchpad/pylibs')
import numpy as np, scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
exec(open('experiments/nube_diag/cv7.py').read().split("gkf=GroupKFold(5)")[0].replace("open('feat5.pkl','rb')", "open('/tmp/claude-0/-home-user-leobot2026/c6a07e9b-8d92-5cd1-afd1-d7a29379d968/scratchpad/feat5.pkl','rb')"))
def text_of(biz):
    tag, name = biz.split('/', 1)
    path = f'results_v3/kiosco/desarrollo/{name}/negocio.txt' if tag == 'desarrollo' else f'results_v3/kiosco/{tag}/{name}/negocio.txt'
    return open(path, encoding='utf8').read()
bizs = sorted({r['biz'] for r in rows})
docs = [text_of(b) for b in bizs]
vec = TfidfVectorizer(min_df=2, max_df=0.5, sublinear_tf=True)
Xd = vec.fit_transform(docs)
for K in (20, 40):
    labels = KMeans(K, n_init=5, random_state=0).fit_predict(Xd)
    cluster = {b: int(l) for b, l in zip(bizs, labels)}
    cg2 = np.array([cluster[r['biz']] for r in rows])[q]
    gkf = GroupKFold(5)
    def cv(mats, C=0.3, w=0.5):
        P = np.zeros(len(y))
        for tr, te in gkf.split(X, y, cg2):
            s = StandardScaler().fit(X[tr]); parts = [sp.csr_matrix(s.transform(X))]
            for M in mats:
                cnt = np.asarray((M[tr] > 0).sum(0)).ravel(); keep = np.where(cnt >= 3)[0]; parts.append(M[:, keep] * w)
            Z = sp.hstack(parts).tocsr()
            m = LogisticRegression(max_iter=3000, C=C); m.fit(Z[tr], y[tr]); P[te] = m.predict_proba(Z[te])[:, 1]
        return P
    print(f'--- validación cruzada por grupo de sector, K={K} (tamaño mayor {max(np.bincount(labels))} negocios)')
    evaluate(cv([]), 'solo densos')
    evaluate(cv([M1, M2, M3]), 'densos + pares')

import sys; sys.path.insert(0,'experiments/nube_diag')
from sweep import *
DEV=['results_v3/kiosco/desarrollo/'+c for c in 'ABCDEF']
import glob,os
def leaves(bank): return sorted({os.path.dirname(os.path.dirname(f)) for f in glob.glob(f'results_v3/kiosco/{bank}/**/conversaciones.json',recursive=True)})
VAL=[l for b in ('congelado','congelado_g58','congelado_g59','congelado_g60') for l in leaves(b)]
print(len(VAL),'carpetas de validación')
def show(name,sc):
    a=run(sc,DEV); b=run(sc,VAL)
    print(f'{name:34s} dev n={a[0]} top1={a[1][0]:.3f} top3={a[1][1]:.3f} top5={a[1][2]:.3f} | val n={b[0]} top1={b[1][0]:.3f} top3={b[1][1]:.3f} top5={b[1][2]:.3f}',flush=True)
show('bm25 inh=1',lambda c,q:bm25(c,q,1.0))
show('bm25 inh=0.5',lambda c,q:bm25(c,q,0.5))
show('bm25 inh=0',lambda c,q:bm25(c,q,0.0))
show('bm25 b=0.3',lambda c,q:bm25(c,q,1.0,b=0.3))
show('bm25 b=1.0',lambda c,q:bm25(c,q,1.0,b=1.0))
show('bm25 k1=2',lambda c,q:bm25(c,q,1.0,k1=2.0))
def cov(a):
    def f(c,q):
        s=bm25(c,q); return {i:v*(coverage(c,q,i)**a) for i,v in s.items()}
    return f
show('bm25*cov^1',cov(1)); show('bm25*cov^2',cov(2))
def big(w):
    def f(c,q):
        s=bm25(c,q); return {i:v+w*bigram_bonus(c,q,i) for i,v in s.items()}
    return f
show('bm25+1*bigram',big(1.0)); show('bm25+3*bigram',big(3.0))
def win(w):
    def f(c,q):
        s=bm25(c,q); return {i:v*(1+w*window(c,q,i)) for i,v in s.items()}
    return f
show('bm25*(1+win)',win(1.0))

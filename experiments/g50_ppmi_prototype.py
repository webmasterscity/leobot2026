# G-50 (prototipo fuera del motor, sugerencia del usuario): equivalencias por PPMI de ventana, vecinos mutuos, filtro de coaparición y sondas de clase y asociación.
import sys, json, math, time, random, re, resource
sys.path.insert(0, '/media/leonardo/data/leobot2026')
from collections import Counter, defaultdict
from leobot import Bot
t0 = time.process_time()
b = Bot.load(sys.argv[1])
TOK = re.compile(r'\w+', re.U)
lex = b.syntax_model['lexicon']
tagcount = defaultdict(Counter)
for k, c in lex.items():
    w, t = k.rsplit('\x1f', 1); tagcount[w.lower()][t] += c
CONTENT = {'NOUN', 'VERB', 'ADJ'}
def tag(w):
    r = tagcount.get(w); return max(sorted(r), key=lambda t: r[t]) if r else None
sents = []
for line in open('/media/leonardo/data/corpus_ud/es_ancora-ud-train.conllu', encoding='utf8'):
    if line.startswith('# text = '): sents.append(line[9:].strip())
d = json.load(open('/tmp/squad_es_train_v1.1.json'))
ctx = sorted({p['context'] for a in d['data'] for p in a['paragraphs']})
for c in ctx: sents.extend(re.split(r'(?<=[.!?])\s+', c))
lk = {}
def key(w):
    if w not in lk:
        t = tag(w); lk[w] = (b.lemma_key(w), t) if t in CONTENT else None
    return lk[w]
docs = []
for s in sents:
    ks = [key(w.lower()) for w in TOK.findall(s)]
    docs.append([k for k in ks if k])
freq = Counter(k for d_ in docs for k in d_)
vocab = {k for k, c in freq.items() if c >= 20}
print('sentences', len(sents), 'tokens', sum(freq.values()), 'vocab>=20', len(vocab), round(time.process_time()-t0,1), flush=True)
co = defaultdict(Counter); sent_co = Counter(); sent_f = Counter()
for d_ in docs:
    ks = [k for k in d_ if k in vocab]
    for i, k in enumerate(ks):
        for j in range(max(0, i-2), min(len(ks), i+3)):
            if j != i: co[k][ks[j]] += 1
    u = sorted(set(ks))
    for k in u: sent_f[k] += 1
    if len(u) <= 40:
        for i in range(len(u)):
            for j in range(i+1, len(u)): sent_co[(u[i], u[j])] += 1
N = sum(sum(r.values()) for r in co.values())
cf = Counter()
for r in co.values():
    for c, n in r.items(): cf[c] += n
Z = sum(v ** 0.75 for v in cf.values())
vec = {}
for w, r in co.items():
    fw = sum(r.values()); v = {}
    for c, n in r.items():
        pmi = math.log(n * Z / (fw * cf[c] ** 0.75))
        if pmi > 0: v[c] = pmi
    norm = math.sqrt(sum(x*x for x in v.values())) or 1
    vec[w] = {c: x / norm for c, x in v.items()}
inv = defaultdict(list)
for w, v in vec.items():
    for c, x in v.items(): inv[c].append((w, x))
common = {c for c, l in inv.items() if len(l) > 1500}
top = {}
for w, v in vec.items():
    acc = Counter()
    for c, x in v.items():
        if c in common: continue
        for u, y in inv[c]:
            if u != w and u[1] == w[1]: acc[u] += x * y
    top[w] = [u for u, _ in acc.most_common(5)]
S_ = len(docs)
def spmi(a, b_):
    p = sent_co.get(tuple(sorted((a, b_))), 0)
    return math.log((p + 0.5) * S_ / (sent_f[a] * sent_f[b_]))
eq = {}
for w, ns in top.items():
    for u in ns:
        if w in top.get(u, ()) and spmi(w, u) <= 0:
            eq.setdefault(w, []).append(u)
print('pairs', sum(len(v) for v in eq.values()) // 2, 'cpu', round(time.process_time()-t0,1), 'rss_mib', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)

def cos(a, b_):
    va, vb = vec.get(a, {}), vec.get(b_, {})
    return round(sum(x * vb.get(c, 0) for c, x in va.items()), 3)
def ppmi(a, b_):
    n = co.get(a, {}).get(b_, 0)
    if not n: return 0.0
    return round(max(0, math.log(n * Z / (sum(co[a].values()) * cf[b_] ** 0.75))), 2)
ranks = {}
for w, v in vec.items():
    pass
pairs = [('verde','nuevo'),('azul','caro'),('azul','verde'),('rojo','gris'),('abogado','ingeniero'),('abogado','medico'),('maestro','conductor'),('maestro','esposo'),('grande','pequeno'),('seis','nueve'),('tarde','noche'),('martes','lunes'),('medellin','cali'),('perro','gato'),('moto','camioneta'),('historia','matematica'),('clavo','tornillo'),('cerrado','abierto')]
for a, b_ in pairs:
    ka = key(a); kb = key(b_)
    print(a, b_, ka, kb, 'cos', ka and kb and cos(ka, kb))
for n_, ans in [('color','azul'),('color','usado'),('color','rojo'),('color','mazda'),('marca','usado'),('marca','toyota'),('material','madera'),('hora','siete'),('edad','ocho'),('color','electricista'),('ciudad','cali'),('profesion','ingeniero')]:
    kn = key(n_); ka = key(ans)
    print('ppmi', n_, ans, kn, ka, kn and ka and ppmi(kn, ka), kn and ka and ppmi(ka, kn))

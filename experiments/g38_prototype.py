"""Development prototype (outside the engine): distributional neighbours learned by counting (PPMI)."""
import math, types, pathlib
import leobot.reading as R
from leobot.reading import _TOKEN,_norm,_is_word
CFG={'k':10,'min_sim':0.15,'weight':0.5}
def learn(texts,window=3,min_count=5,max_ctx=2000):
    counts={}; pair={}
    for text in texts:
        w=[_norm(t) for t in _TOKEN.findall(text) if _is_word(t)]
        for i,a in enumerate(w):
            counts[a]=counts.get(a,0)+1
            for j in range(max(0,i-window),min(len(w),i+window+1)):
                if j!=i:
                    d=pair.setdefault(a,{}); d[w[j]]=d.get(w[j],0)+1
    total=sum(counts.values()); vec={}
    for a,ctx in pair.items():
        if counts[a]<min_count: continue
        v={}
        for b,c in ctx.items():
            if counts.get(b,0)<min_count: continue
            pmi=math.log(c*total/(counts[a]*counts[b]))
            if pmi>0: v[b]=pmi
        top=dict(sorted(v.items(),key=lambda x:-x[1])[:max_ctx])
        norm=math.sqrt(sum(x*x for x in top.values())) or 1
        vec[a]={b:x/norm for b,x in top.items()}
    return vec
class Neigh:
    def __init__(self,vec): self.vec=vec; self.cache={}
    def sim(self,a,b):
        va,vb=self.vec.get(a),self.vec.get(b)
        if not va or not vb: return 0.0
        if len(va)>len(vb): va,vb=vb,va
        return sum(x*vb.get(k,0.0) for k,x in va.items())
src=pathlib.Path(R.__file__).read_text()
src=src.replace("""        literal = {p: self._reading_overlap(qtokens, word_sets[p]) for p in candidates}
        scored = [(literal[p], p) for p in candidates]""","""        literal = {p: self._reading_overlap(qtokens, word_sets[p]) for p in candidates}
        scored = [(self._dist_overlap(qtokens, word_sets[p]), p) for p in candidates]""")
src=src.replace("""                cover[name] = sum(self._reading_idf(t) * (BM25_K1 + 1) / (1 + norm)
                                  for t in unique if t in words)""","""                cover[name] = sum(self._reading_idf(t) * (BM25_K1 + 1) / (1 + norm) * self._dist_presence(t, words)
                                  for t in unique)""")
src=src.replace("""    def consolidate_reading(self) -> dict:""","""    def _dist_presence(self, token, words):
        if token in words:
            return 1.0
        n = getattr(self, '_proto_neigh', None)
        if n is None:
            return 0.0
        key = (token, id(words))
        if key not in n.cache:
            best = max((n.sim(token, w) for w in words), default=0.0)
            n.cache[key] = CFG['weight'] * best if best >= CFG['min_sim'] else 0.0
        return n.cache[key]

    def _dist_overlap(self, question, words):
        total = sum(self._reading_idf(t) for t in question)
        return sum(self._reading_idf(t) * self._dist_presence(t, words) for t in question) / total if total else 0.0

    def consolidate_reading(self) -> dict:""")
mod=types.ModuleType('reading_g38'); mod.__dict__['CFG']=CFG; exec(compile(src,'reading_g38','exec'),mod.__dict__); mod.CFG=CFG
for name in ('answer_from_utterances','_dist_presence','_dist_overlap'):
    setattr(R.ReadingMemoryMixin,name,getattr(mod.ReadingMemoryMixin,name))

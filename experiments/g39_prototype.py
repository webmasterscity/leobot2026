"""Development prototype (outside the engine): span choice by a decision tree grown from counts
(information gain on categorical span features; leaves hold smoothed positive rates)."""
import math, random, types, pathlib
import leobot.reading as R
from leobot.reading import _TOKEN, _norm, _is_word
CFG={'w_tree':1.0,'w_nb':0.001,'neg':40,'depth':12,'min_leaf':15,'kappa':5.0,'blend':1.0}
def instances(bot, examples):
    data=[]; rng=random.Random(39)
    for ex in examples:
        q=[_norm(t) for t in _TOKEN.findall(ex['question']) if _is_word(t)]
        target=[_norm(t) for t in _TOKEN.findall(ex['answers'][0]) if _is_word(t)]
        if not q or not target: continue
        found=None
        for s in bot._document_sentences(ex['context']):
            toks=_TOKEN.findall(s); words=[(i,_norm(t)) for i,t in enumerate(toks) if _is_word(t)]
            for k in range(len(words)-len(target)+1):
                if [w for _,w in words[k:k+len(target)]]==target:
                    found=(toks,words[k][0],words[k+len(target)-1][0]+1); break
            if found: break
        if not found: continue
        toks,gs,ge=found; present={_norm(t) for t in toks}; qset=set(q)
        key=bot._gap_marker(q); anchors=set(bot._anchors(toks,qset)); gap=bot._gap_neighbours(q,key,present)
        norm=[_norm(t) for t in toks]
        cands=list(bot._candidate_spans(toks)); negs=[c for c in cands if c!=(gs,ge)]
        rng.shuffle(negs)
        for (s,e) in [(gs,ge)]+negs[:CFG['neg']]:
            f={x[0]:x[1:] for x in bot._span_features(toks,s,e,anchors,qset,gap,norm)}
            f['key']=(key,)
            data.append((f,(s,e)==(gs,ge)))
    return data
def grow(data, depth, prior, used=()):
    pos=sum(1 for _,y in data if y); n=len(data)
    rate=(pos+CFG['kappa']*prior)/(n+CFG['kappa'])
    node={'rate':rate}
    if depth==0 or n<2*CFG['min_leaf'] or pos==0 or pos==n: return node
    def H(p,m):
        if m==0 or p in (0,m): return 0.0
        a=p/m; return -(a*math.log(a)+(1-a)*math.log(1-a))
    base=H(pos,n); best=None
    stats={}
    for f,y in data:
        for name,val in f.items():
            if name=='key' and 0: pass
            k=(name,val); c=stats.setdefault(k,[0,0]); c[0]+=1; c[1]+=y
    for k,(m,p) in stats.items():
        if m<CFG['min_leaf'] or n-m<CFG['min_leaf'] or k in used: continue
        gain=base-(m/n)*H(p,m)-((n-m)/n)*H(pos-p,n-m)
        if best is None or gain>best[0]: best=(gain,k)
    if best is None or best[0]<=1e-4: return node
    name,val=best[1]
    yes=[(f,y) for f,y in data if f.get(name)==val]; no=[(f,y) for f,y in data if f.get(name)!=val]
    node.update(test=best[1],yes=grow(yes,depth-1,rate,used+(best[1],)),no=grow(no,depth-1,rate,used+(best[1],)))
    return node
def leaf(tree,f):
    if isinstance(tree,list):
        return sum(leaf(t,f) for t in tree)/len(tree)
    while 'test' in tree:
        name,val=tree['test']; tree=tree['yes'] if f.get(name)==val else tree['no']
    return tree['rate']
src=pathlib.Path(R.__file__).read_text()
old="""                if use_model:
                    score = 0.0
                    for feature in self._span_features(tokens, start, end, anchors, qset, gap, normalized):
                        value = memo.get(feature)
                        if value is None:
                            value = memo[feature] = self._feature_score(key, feature, prior)
                        score += value"""
new="""                if use_model:
                    feats = self._span_features(tokens, start, end, anchors, qset, gap, normalized)
                    nb = 0.0
                    for feature in feats:
                        value = memo.get(feature)
                        if value is None:
                            value = memo[feature] = self._feature_score(key, feature, prior)
                        nb += value
                    tree = getattr(self, '_proto_tree', None)
                    if tree is not None:
                        f = {x[0]: x[1:] for x in feats}; f['key'] = (key,)
                        r = min(max(leaf(tree, f), 1e-9), 1 - 1e-9)
                        score = CFG['w_tree'] * math.log(r / (1 - r)) + CFG['w_nb'] * nb
                    else:
                        score = nb"""
assert src.count(old)==1; src=src.replace(old,new)
mod=types.ModuleType('reading_g39'); mod.__dict__.update(leaf=leaf,CFG=CFG); exec(compile(src,'reading_g39','exec'),mod.__dict__)
R.ReadingMemoryMixin.answer_from_utterances=mod.ReadingMemoryMixin.answer_from_utterances

def forest(data,prior,trees=25,depth=12,frac=0.6,names=None):
    out=[]; names=sorted({k for f,_ in data for k in f})
    for i in range(trees):
        rng=random.Random(1000+i); keep=set(rng.sample(names,max(2,int(len(names)*frac))))
        sample=[rng.choice(data) for _ in range(len(data))]
        sub=[({k:v for k,v in f.items() if k in keep},y) for f,y in sample]
        out.append(grow(sub,depth,prior))
    return out

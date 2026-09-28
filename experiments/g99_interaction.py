"""Small learned evidence selector; exact and learned token matches, no semantic rules."""
import json
from pathlib import Path
import numpy as np
from experiments.g97_neural import features, encode_numpy
from experiments.g68_confianza import calibrated

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.leobot-data/g99'
LEXICAL=13
WIDTH=LEXICAL+9+3*64


class PairFeatures:
    width=WIDTH
    def __init__(self,bot,vocab,weights):
        self.bot,self.vocab,self.weights=bot,vocab,weights
        self.word_cache={'q':{},'a':{}}
        self.unit_cache={}

    def token_vectors(self,words,side,limit):
        cache=self.word_cache[side]; vectors=[]
        for w in words[:limit]:
            if w not in self.vocab:continue
            if w not in cache:cache[w]=encode_numpy([self.vocab[w]],self.weights,side)
            vectors.append(cache[w])
        return np.stack(vectors) if vectors else np.zeros((0,64),dtype=np.float32)

    def pooled(self,words,side):
        ids=[self.vocab[f] for f in features(words) if f in self.vocab]
        return encode_numpy(ids,self.weights,side)

    def prepare(self,texts):
        result=[]
        for text in texts:
            if text not in self.unit_cache:
                words=self.bot.context_terms(text); vectors=self.token_vectors(words,'a',64)
                self.unit_cache[text]={'words':words,'set':set(words),'pairs':set(zip(words,words[1:])),
                    'vectors':vectors if len(vectors) else np.zeros((1,64),dtype=np.float32),
                    'mean':self.pooled(words,'a'),'known':sum(w in self.vocab for w in words)/max(1,len(words))}
            result.append(self.unit_cache[text])
        return result

    def one_question(self,text,units):
        result=np.zeros((len(units),WIDTH),dtype=np.float32)
        if not units:return result
        words=self.bot.context_terms(text); unique=list(dict.fromkeys(words)); pairs=set(zip(words,words[1:]))
        pi=np.array([self.bot._delta(w) for w in unique],dtype=np.float32)
        bridge=self.bot._bridge(); n=max(1,len(unique)); mass=max(1e-9,float(pi.sum()))
        qmean=self.pooled(words,'q'); qvec=self.token_vectors(words,'q',32)
        if len(qvec):
            lengths=[len(u['vectors']) for u in units];starts=np.cumsum([0]+lengths[:-1])
            matched=np.maximum.reduceat(qvec@np.concatenate([u['vectors'] for u in units]).T,starts,axis=1)
            quartiles=np.quantile(matched,[.25,.75],axis=0)
            result[:,LEXICAL:LEXICAL+6]=np.stack((matched.mean(0),matched.min(0),matched.std(0),
                                               quartiles[0],quartiles[1],matched.max(0)),axis=1)
        known=sum(w in self.vocab for w in words)/max(1,len(words))
        for i,u in enumerate(units):
            hits=np.array([w in u['set'] for w in unique],dtype=np.float32)
            links=np.array([max((v for a,v in bridge.get(w,()) if a in u['set']),default=0.) for w in unique],dtype=np.float32)
            result[i,:LEXICAL]=[np.log1p(len(words)),np.log1p(len(u['words'])),float(hits.sum())/n,
                float(hits.sum())/max(1,len(u['set'])),float(hits@pi)/mass,
                float(np.max(pi*(1-hits))) if n>1 or len(pi) else 0.,float(pi.mean()) if len(pi) else 0.,
                float(links.max()) if len(links) else 0.,float(links.mean()) if len(links) else 0.,
                float((links>0).sum())/n,len(pairs & u['pairs'])/max(1,len(pairs)),
                float(pi.max()) if len(pi) else 0.,float(np.maximum(hits*pi,links).sum())/mass]
            result[i,LEXICAL+6:LEXICAL+9]=[float(qmean@u['mean']),known,u['known']]
            result[i,LEXICAL+9:]=np.concatenate((qmean,u['mean'],qmean*u['mean']))
        return result

    def matrix(self,question,previous,units):
        now=self.one_question(question,units)
        before=self.one_question(previous,units) if previous else np.zeros_like(now)
        return np.concatenate((now,before),axis=1)


def model_indices(name):
    return np.arange(LEXICAL if name=='lexical' else WIDTH if name=='interaction' else 2*WIDTH)


def predict_numpy(matrix,weights):
    normalized=(matrix-weights['mean'])/weights['scale']
    return (np.tanh(normalized@weights['w1']+weights['b1'])@weights['w2']+weights['b2'])[:,0]


class InteractionRoute:
    def __init__(self,bot,name,threshold=.9,root=OUT):
        self.bot,self.name,self.threshold=bot,name,threshold
        self.meta=json.loads((root/'models.json').read_text())
        with np.load(root/f'{name}.npz',allow_pickle=False) as source:self.weights=dict(source)
        old=ROOT/'.leobot-data/g98'
        oldmeta=json.loads((old/'neural.json').read_text())
        with np.load(old/'localized.npz',allow_pickle=False) as source:embeddings=dict(source)
        self.encoder=PairFeatures(bot,oldmeta['vocabulary'],embeddings)
        self.indices=model_indices(name)
        self.gate=self.meta.get('calibration',{}).get(name)

    def prepare(self):
        self.encoder.unit_cache.clear()
        self.ids=[i for i,u in enumerate(self.bot.context_units) if u.get('kind') not in ('heading','question')]
        texts=[self.bot.context_units[i]['text']+(' '+self.bot.context_units[i]['heading']
               if self.bot.context_units[i].get('inherited') else '') for i in self.ids]
        self.units=self.encoder.prepare(texts)

    def raw(self,question,history=()):
        if not self.ids:return None
        previous=history[-2] if len(history)>=2 and isinstance(history[-2],str) else ''
        if self.name in ('lexical','interaction'):previous=''
        x=self.encoder.matrix(question,previous,self.units)[:,self.indices]
        values=predict_numpy(x,self.weights);order=np.argsort(-values,kind='stable');i=int(order[0])
        return {'index':self.ids[i],'score':float(values[i]),'null_selected':bool(values[i]<=0),
                'margin':float(values[i]-values[int(order[1])]) if len(order)>1 else float(values[i])}

    def propose(self,question,history):
        raw=self.raw(question,history)
        if raw is None or raw['null_selected'] or self.gate is None:return None
        p=calibrated(self.gate['blocks'],raw['score'])
        return {'index':raw['index'],'confidence':p} if p>=self.threshold else None

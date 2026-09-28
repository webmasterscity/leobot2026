"""Static representations are evidence features, never probabilities of correctness."""
from functools import lru_cache
import json
import time
import numpy as np
from experiments.g99_interaction import PairFeatures,LEXICAL,predict_numpy,ROOT
from experiments.g68_confianza import calibrated

OUT=ROOT/'.leobot-data/g101'


@lru_cache(maxsize=1)
def static_model():
    from model2vec import StaticModel
    begin=time.perf_counter()
    model=StaticModel.from_pretrained(str(OUT/'model'),normalize=True,force_download=False)
    model.embedding.flags.writeable=False
    return model,(time.perf_counter()-begin)*1000


def encode(model,texts):
    return model.encode(texts,max_length=None,use_multiprocessing=False)


def combine(lexical,similarities):
    if not len(similarities):return np.zeros((0,LEXICAL+3),dtype=np.float32)
    if len(similarities)==1:runner=np.zeros(1)
    else:
        order=np.argsort(-similarities,kind='stable');runner=np.full(len(similarities),similarities[order[0]])
        runner[order[0]]=similarities[order[1]]
    return np.column_stack((lexical,similarities,similarities-runner,similarities-similarities.mean())).astype('float32')


def admit(raw,blocks,threshold):
    if raw is None or raw['score']<=0:return None
    p=calibrated(blocks,raw['score'])
    return {'index':raw['index'],'confidence':p} if p>=threshold else None


class StaticFeatures:
    def __init__(self,bot):
        self.model,self.load_ms=static_model()
        # Reuse exactly G99's first 13 variables. Empty vocabulary avoids computing
        # the discarded G98 neural channels; lexical identities are still intact.
        dummy={'embedding':np.zeros((1,64),dtype=np.float32)}
        for side in ('q','a'):
            dummy[side+'_weight']=np.eye(64,dtype=np.float32);dummy[side+'_bias']=np.zeros(64,dtype=np.float32)
        self.lexical=PairFeatures(bot,{},dummy)

    def prepare(self,texts):
        return self.lexical.prepare(texts),encode(self.model,texts) if texts else np.zeros((0,256),dtype=np.float32)

    def matrix(self,question,units):
        lexical,vectors=units
        if not len(lexical):return np.zeros((0,16),dtype=np.float32)
        q=encode(self.model,[question])[0]
        return combine(self.lexical.one_question(question,lexical)[:,:LEXICAL],vectors@q)


class StaticRoute:
    def __init__(self,bot,name,threshold=.9):
        self.bot,self.name,self.threshold=bot,name,threshold
        self.meta=json.loads((OUT/'models.json').read_text())
        self.encoder=StaticFeatures(bot);self.load_ms=self.encoder.load_ms
        if name!='static':
            with np.load(OUT/f'{name}.npz',allow_pickle=False) as saved:self.weights=dict(saved)
        self.gate=self.meta.get('calibration',{}).get(name)

    def prepare(self):
        self.encoder.lexical.unit_cache.clear()
        self.ids=[i for i,u in enumerate(self.bot.context_units) if u.get('kind') not in ('heading','question')]
        texts=[self.bot.context_units[i]['text']+(' '+self.bot.context_units[i]['heading']
               if self.bot.context_units[i].get('inherited') else '') for i in self.ids]
        self.units=self.encoder.prepare(texts)

    def raw(self,question,history=()):
        if not self.ids:return None
        x=self.encoder.matrix(question,self.units)
        values=x[:,LEXICAL] if self.name=='static' else predict_numpy(x,self.weights)
        i=int(np.argmax(values))
        return {'index':self.ids[i],'score':float(values[i]),'similarity':float(x[i,LEXICAL]),
                'null_selected':bool(values[i]<=0)}

    def propose(self,question,history):
        return admit(self.raw(question,history),self.gate['blocks'],self.threshold) if self.gate else None

"""G97C: small retrieval network trained locally from scratch, not a generative LLM."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import resource
import time
BOOT = time.process_time()
import numpy as np

from experiments.g97_backups import ABSTAINED
from experiments.g60_calibrar_confianza import naive_bayes, score
from experiments.g68_confianza import TRAIN, isotonic, calibrated
from experiments.g57_kiosco import businesses, contains
from leobot.context import COVER_BINS, _bin

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.leobot-data/g97'


def features(words):
    return list(words)+[a+'\x1f'+b for a,b in zip(words,words[1:])]


def encode_numpy(ids, weights, side):
    if not ids:
        return np.zeros(weights['embedding'].shape[1], dtype=np.float32)
    mean = weights['embedding'][ids].mean(axis=0)
    value = np.tanh(mean@weights[side+'_weight']+weights[side+'_bias'])
    return value/max(float(np.linalg.norm(value)),1e-12)


class NeuralRoute:
    def __init__(self, bot, name, *, root=OUT):
        self.bot, self.name = bot, name
        self.meta = json.loads((root/'neural.json').read_text())
        self.vocab = self.meta['vocabulary']
        with np.load(root/f'{name}.npz', allow_pickle=False) as saved:
            self.weights = dict(saved)
        self.gate = self.meta.get('gates',{}).get(name)

    def encode(self, text, side):
        fs = features(self.bot.context_terms(text))
        ids = [self.vocab[x] for x in fs if x in self.vocab]
        return encode_numpy(ids,self.weights,side), len(ids)/max(1,len(fs))

    def prepare(self):
        texts = [u['text']+(' '+u['heading'] if u.get('inherited') else '') for u in self.bot.context_units]
        self.matrix = np.stack([self.encode(t,'a')[0] for t in texts]) if texts else np.zeros((0,64),dtype=np.float32)
        self.terms = [set(self.bot.context_terms(t)) for t in texts]

    def raw(self, question):
        if not len(self.matrix): return None
        vector,known = self.encode(question,'q')
        values = self.matrix@vector
        eligible = [i for i,u in enumerate(self.bot.context_units) if u.get('kind') not in ('heading','question')]
        if not eligible: return None
        ordered = sorted(eligible,key=lambda i:(-float(values[i]),i))
        i = ordered[0]
        value = float(values[i]); runner = float(values[ordered[1]]) if len(ordered)>1 else 0.
        q = set(self.bot.context_terms(question))
        f = {'score':str(round(value*10)), 'margin':str(_bin(value-runner,(0.,.01,.025,.05,.1,.2,.4))),
             'known':str(_bin(known,COVER_BINS)),
             'overlap':str(_bin(len(q & self.terms[i])/max(1,len(q)),COVER_BINS))}
        return {'index':i,'features':f,'similarity':value,'known':known}

    def propose(self, question, history):
        choice = self.raw(question)
        if choice is None or self.gate is None: return None
        p = calibrated(self.gate['calibration'],score(self.gate['counts'],choice['features']))
        return {'index':choice['index'],'confidence':p} if p >= .4 else None


def train():
    import torch
    from torch import nn
    from torch.nn import functional as F
    from leobot import Bot
    from experiments.g65_correspondencias import examples, MFAQ_SHA
    from experiments.g74_relation_coverage import BASE_SHA, ENGINE
    import subprocess
    # The installed torch maps >3 GiB of virtual libraries while using ~0.5 GiB
    # RSS. The preregistered physical memory limit must not be an address limit.
    def check_budget():
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 3*1024**2:
            raise MemoryError('G97 physical memory budget')
        if time.process_time()-start > 1200:
            raise TimeoutError('G97 neural education budget')
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    start, wall = BOOT, time.monotonic()
    before = subprocess.check_output(['git','rev-parse','HEAD:leobot'],text=True).strip()
    assert before == ENGINE
    base = ROOT/'.leobot-data/base_kiosco.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    bot = Bot.load(base)
    sampled = examples(bot,ROOT/'.leobot-data/mfaq_es_train.jsonl')
    eligible = sorted((row for row in sampled if 1 <= len(row[1]) <= 40 and 1 <= len(row[2]) <= 160),
                      key=lambda row:hashlib.sha256(json.dumps(row,ensure_ascii=False).encode()).digest())
    is_valid = lambda d:int(hashlib.sha256(d.encode()).hexdigest(),16)%5 == 0
    training = [r for r in eligible if not is_valid(r[0])][:6000]
    validation = [r for r in eligible if is_valid(r[0])][:1000]
    assert len(training)==6000 and len(validation)==1000
    counts = Counter(f for _,q,a in training for words in (q,a) for f in features(words))
    chosen = sorted((f for f,n in counts.items() if n>=2),key=lambda f:(-counts[f],f))[:20000]
    vocabulary = {f:i+1 for i,f in enumerate(chosen)}
    encode = lambda words:[vocabulary[f] for f in features(words) if f in vocabulary]
    qrows,arows = [encode(q) for _,q,_ in training], [encode(a) for _,_,a in training]
    def tensor(rows):
        a = torch.zeros((len(rows),max(1,max(map(len,rows)))),dtype=torch.long)
        for i,row in enumerate(rows):
            if row: a[i,:len(row)] = torch.tensor(row,dtype=torch.long)
        return a
    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.EmbeddingBag(len(vocabulary)+1,64,mode='mean',padding_idx=0)
            self.q = nn.Linear(64,64); self.a = nn.Linear(64,64)
        def forward(self,x,side):
            value = torch.tanh(getattr(self,side)(self.embedding(x)))
            return F.normalize(value,dim=1)*x.ne(0).any(dim=1,keepdim=True)
    OUT.mkdir(exist_ok=True)
    def exported(model):
        return {'embedding':model.embedding.weight.detach().numpy().copy(),
                **{side+'_weight':getattr(model,side).weight.detach().numpy().T.copy() for side in ('q','a')},
                **{side+'_bias':getattr(model,side).bias.detach().numpy().copy() for side in ('q','a')}}
    domain_rows = defaultdict(list)
    for i,(domain,_,_) in enumerate(training): domain_rows[domain].append(i)
    permutation = list(range(len(training))); rng = random.Random(1)
    for _,indices in sorted(domain_rows.items()):
        shuffled = indices.copy(); rng.shuffle(shuffled)
        for i,j in zip(indices,shuffled): permutation[i]=j
    meta = {'vocabulary':vocabulary,'source_sha256':MFAQ_SHA,'base_sha256':BASE_SHA,
            'engine':ENGINE,'training_pairs':len(training),'validation_pairs':len(validation),
            'training_domains':len({r[0] for r in training}),'validation_domains':len({r[0] for r in validation}),
            'training_sha256':hashlib.sha256(json.dumps(training,ensure_ascii=False).encode()).hexdigest(),
            'validation_sha256':hashlib.sha256(json.dumps(validation,ensure_ascii=False).encode()).hexdigest(),
            'torch':torch.__version__,'numpy':np.__version__,'models':{},'gates':{},
            'shuffled_changed':sum(i!=j for i,j in enumerate(permutation))}
    for mode in ('random','trained','shuffled'):
        torch.manual_seed(1); model=Encoder(); begin=time.process_time()
        opt=torch.optim.AdamW(model.parameters(),lr=.003,weight_decay=.0001)
        perm=permutation if mode=='shuffled' else list(range(len(training)))
        epochs=[]; order=list(range(len(training))); rng=random.Random(1)
        for epoch in range(0 if mode=='random' else 6):
            rng.shuffle(order); losses=[]
            for lo in range(0,len(order),64):
                check_budget()
                ids=order[lo:lo+64]
                qs=model(tensor([qrows[i] for i in ids]),'q')
                ans=model(tensor([arows[perm[i]] for i in ids]),'a')
                logits=qs@ans.T/.1
                mask=torch.tensor([[training[i][1]==training[j][1] or training[perm[i]][2]==training[perm[j]][2]
                                    for j in ids] for i in ids],dtype=torch.bool)
                def loss(x,m): return (x.logsumexp(1)-x.masked_fill(~m,-1e9).logsumexp(1)).mean()
                error=(loss(logits,mask)+loss(logits.T,mask.T))/2
                opt.zero_grad(); error.backward(); opt.step(); losses.append(float(error.detach()))
            epochs.append(sum(losses)/len(losses))
            print(json.dumps({'stage':'train','mode':mode,'epoch':epoch+1,'loss':epochs[-1],
                              'cpu_s':time.process_time()-start}),flush=True)
        model.eval(); weights=exported(model)
        check = np.stack([encode_numpy(row,weights,'q') for row in qrows[:32]])
        with torch.no_grad(): observed=model(tensor(qrows[:32]),'q').numpy()
        export_error=float(np.max(np.abs(check-observed)))
        assert export_error<1e-5
        np.savez(OUT/f'{mode}.npz',**weights)
        vq=np.stack([encode_numpy(encode(q),weights,'q') for _,q,_ in validation])
        va=np.stack([encode_numpy(encode(a),weights,'a') for _,_,a in validation])
        correct=0
        for i in range(len(validation)):
            rival=[(i+j)%len(validation) for j in range(16)]
            correct += int(np.argmax(va[rival]@vq[i])==0)
        meta['models'][mode]={'parameters':sum(p.numel() for p in model.parameters()),'epochs':epochs,
                             'cpu_s':time.process_time()-begin,'export_max_error':export_error,
                             'validation_top1_of16':correct,'validation_n':len(validation),
                             'sha256':hashlib.sha256((OUT/f'{mode}.npz').read_bytes()).hexdigest()}
        (OUT/'neural.json').write_text(json.dumps(meta,ensure_ascii=False))
        print(json.dumps({'stage':'model_saved','mode':mode,**meta['models'][mode]}),flush=True)
    del model,opt,sampled,eligible
    routes={n:NeuralRoute(bot,n) for n in meta['models']}
    rows={n:[] for n in routes}; begin=time.process_time()
    for bank in TRAIN:
        root=ROOT/'results_v3/kiosco'/bank
        for name,text,instructions,conversations in businesses(sorted(p for p in root.iterdir() if p.is_dir())):
            half=int(hashlib.sha256((bank+'/'+name).encode()).hexdigest(),16)%2
            bot.load_context(text,instructions)
            for route in routes.values(): route.prepare()
            for conv in conversations:
                history=[]
                for turn in conv:
                    reply=bot.answer(turn['cliente'],history)
                    if reply['status'] in ABSTAINED and turn.get('accion')!='charla':
                        keys=turn.get('claves') or []
                        absent=turn.get('accion') in ('abstenerse','derivar')
                        if keys or absent:
                            for name,route in routes.items():
                                raw=route.raw(turn['cliente'])
                                if raw is not None:
                                    unit=bot.context_units[raw['index']]['text']
                                    label=int(not absent and all(contains(unit,k) for k in keys))
                                    rows[name].append({'half':half,'y':label,'f':raw['features']})
                    history += [turn['cliente'],reply['text']]
            check_budget()
    for name,items in rows.items():
        crossed=[]
        for half in (0,1):
            counts=naive_bayes([r for r in items if r['half']!=half])
            crossed += [(score(counts,r['f']),r['y']) for r in items if r['half']==half]
        meta['gates'][name]={'counts':naive_bayes(items),'calibration':isotonic(crossed),'rows':len(items),
                             'correct_proposals':sum(r['y'] for r in items)}
    meta['gate_cpu_s']=time.process_time()-begin
    meta['cpu_s']=time.process_time()-start; meta['wall_s']=time.monotonic()-wall
    meta['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    meta['source_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'neural.json').write_text(json.dumps(meta,ensure_ascii=False))
    summary={k:v for k,v in meta.items() if k not in ('vocabulary','gates')}
    summary['gates']={n:{k:v for k,v in g.items() if k in ('rows','correct_proposals')} for n,g in meta['gates'].items()}
    summary['model_metadata_sha256']=hashlib.sha256((OUT/'neural.json').read_bytes()).hexdigest()
    (ROOT/'results_v3/g97_training.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'stage':'training_done',**summary}),flush=True)


if __name__=='__main__':
    try: train()
    except Exception as exc:
        (ROOT/'results_v3/g97_training_interruption.json').write_text(json.dumps({'error':repr(exc),
            'cpu_s':time.process_time()-BOOT,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n')
        raise

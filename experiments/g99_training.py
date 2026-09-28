"""G99 learns the decision over frozen token interactions on G98 educational splits."""
import time
BOOT=time.process_time()
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import random
import resource
import subprocess
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from leobot import Bot
from experiments.g98_training import prepare,partition,selection_loss
from experiments.g99_interaction import PairFeatures,InteractionRoute,model_indices,predict_numpy,ROOT,OUT
from experiments.g57_kiosco import contains
from experiments.g97_backups import ABSTAINED
from experiments.g68_confianza import isotonic
from experiments.g74_relation_coverage import BASE_SHA,ENGINE


class Decision(nn.Module):
    def __init__(self,width):
        super().__init__();self.hidden=nn.Linear(width,48);self.out=nn.Linear(48,1)
    def forward(self,x):return self.out(torch.tanh(self.hidden(x)))[...,0]
    def export(self):
        return {'w1':self.hidden.weight.detach().numpy().T.copy(),'b1':self.hidden.bias.detach().numpy().copy(),
                'w2':self.out.weight.detach().numpy().T.copy(),'b2':self.out.bias.detach().numpy().copy()}


def decision_loss(values,targets,valid):
    logits=torch.cat((values,torch.zeros((len(values),1))),1)
    selection=selection_loss(logits,targets,valid)
    binary=F.binary_cross_entropy_with_logits(values,targets[:,:-1].float(),reduction='none')
    return selection+.25*(binary*valid).sum()/valid.sum()


def check():
    if time.process_time()-BOOT>1200:raise TimeoutError('G99 training CPU budget')
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>3*1024**2:raise MemoryError('G99 RSS budget')


def valid_measure(model,rows,features,mean,scale,indices):
    result={'answerable':0,'absent':0,'raw_correct':0,'correct_with_null':0}
    weights={**model.export(),'mean':mean,'scale':scale}
    for r,x in zip(rows,features):
        values=predict_numpy(x[:,indices],weights);i=int(values.argmax())
        result['answerable' if r['pos'] else 'absent']+=1
        result['raw_correct']+=i in r['pos']
        result['correct_with_null']+=bool((i in r['pos'] and values[i]>0) if r['pos'] else values[i]<=0)
    return result


def train():
    startwall=time.monotonic();torch.set_num_threads(1);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    assert subprocess.check_output(['git','rev-parse','HEAD:leobot'],text=True).strip()==ENGINE
    assert hashlib.sha256((ROOT/'.leobot-data/base_kiosco.json').read_bytes()).hexdigest()==BASE_SHA
    old=ROOT/'.leobot-data/g98'; oldmeta=json.loads((old/'neural.json').read_text())
    with np.load(old/'localized.npz',allow_pickle=False) as source:embedded=dict(source)
    assert hashlib.sha256((old/'localized.npz').read_bytes()).hexdigest()==oldmeta['models']['localized']['sha256']
    with np.load(ROOT/'.leobot-data/g97/trained.npz',allow_pickle=False) as source:initial=dict(source)
    bot=Bot.load(ROOT/'.leobot-data/base_kiosco.json')
    rows,validation,banks,education=prepare(bot,oldmeta['vocabulary'],initial)
    for key in ('train_sha256','validation_sha256'):
        assert education[key]==oldmeta['education'][key]
    previous={}
    for b in banks:
        for ci,conv in enumerate(b['conversations']):
            for ti,t in enumerate(conv):previous[f'{b["id"]}/{ci}/{ti}']=conv[ti-1]['cliente'] if ti else ''
    for r in rows+validation:r['previous']=previous.get(r['id'],'')
    perm=list(range(len(rows)));bygroup=defaultdict(list);rng=random.Random(1)
    for i,r in enumerate(rows):bygroup[r['group']].append(i)
    for _,ids in sorted(bygroup.items()):
        mixed=ids.copy();rng.shuffle(mixed)
        for i,j in zip(ids,mixed):perm[i]=j
    encoder=PairFeatures(bot,oldmeta['vocabulary'],embedded)
    xs=[];mixedxs=[];vs=[]
    for i,r in enumerate(rows):
        units=encoder.prepare(r['units']);other=rows[perm[i]]
        xs.append(encoder.matrix(r['q'],r['previous'],units))
        mixedxs.append(encoder.matrix(other['q'],other['previous'],units))
        if i%512==0:
            check();print(json.dumps({'stage':'features','rows':i,'cpu_s':time.process_time()-BOOT}),flush=True)
    for r in validation:
        vs.append(encoder.matrix(r['q'],r['previous'],encoder.prepare(r['units'])))
    encoder.unit_cache.clear()
    OUT.mkdir(exist_ok=True)
    if (OUT/'models.json').exists():raise FileExistsError('Preserve G99 artifacts')
    meta={'engine':ENGINE,'base_sha256':BASE_SHA,'embedding_sha256':oldmeta['models']['localized']['sha256'],
          'education':education,'models':{},'calibration':{},'preparation_cpu_s':time.process_time()-BOOT,
          'shuffled_changed':sum(rows[i]['q']!=rows[j]['q'] for i,j in enumerate(perm)),
          'history_examples':sum(bool(r['previous']) for r in rows),'feature_width':xs[0].shape[1]}
    print(json.dumps({'stage':'prepared','cpu_s':meta['preparation_cpu_s'],'rows':len(rows),
                      'history_examples':meta['history_examples'],'feature_width':meta['feature_width']}),flush=True)
    for name in ('lexical','interaction','history','shuffled'):
        begin=time.process_time();indices=model_indices(name);source=mixedxs if name=='shuffled' else xs
        stacked=np.concatenate([x[:,indices] for x in source]);mean=stacked.mean(0);scale=np.maximum(stacked.std(0),1e-3)
        del stacked
        values=[torch.from_numpy(((x[:,indices]-mean)/scale).astype('float32')) for x in source]
        torch.manual_seed(1);model=Decision(len(indices));opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
        order=list(range(len(rows)));rng=random.Random(1);losses=[]
        for epoch in range(24):
            rng.shuffle(order);total=0.;seen=0
            for lo in range(0,len(order),64):
                check();ids=order[lo:lo+64];width=max(len(values[i]) for i in ids)
                x=torch.zeros((len(ids),width,len(indices)));valid=torch.zeros((len(ids),width),dtype=torch.bool)
                target=torch.zeros((len(ids),width+1),dtype=torch.bool)
                for j,i in enumerate(ids):
                    x[j,:len(values[i])]=values[i];valid[j,:len(values[i])]=True
                    target[j,rows[i]['pos'] or [width]]=True
                loss=decision_loss(model(x),target,valid)
                opt.zero_grad();loss.backward();opt.step();total+=float(loss.detach())*len(ids);seen+=len(ids)
            losses.append(total/seen)
            if (epoch+1)%6==0:print(json.dumps({'stage':'epoch','mode':name,'epoch':epoch+1,'loss':losses[-1],
                                               'cpu_s':time.process_time()-BOOT}),flush=True)
        weights={**model.export(),'mean':mean,'scale':scale};np.savez(OUT/f'{name}.npz',**weights)
        sample=source[0][:,indices]
        with torch.no_grad():expected=model(torch.from_numpy(((sample-mean)/scale).astype('float32'))).numpy()
        error=float(np.max(np.abs(expected-predict_numpy(sample,weights))));assert error<1e-4
        meta['models'][name]={'parameters':sum(p.numel() for p in model.parameters()),'features':len(indices),
            'cpu_s':time.process_time()-begin,'losses':losses,'export_max_error':error,
            'sha256':hashlib.sha256((OUT/f'{name}.npz').read_bytes()).hexdigest(),
            'validation':valid_measure(model,validation,vs,mean,scale,indices)}
        (OUT/'models.json').write_text(json.dumps(meta,ensure_ascii=False))
        print(json.dumps({'stage':'saved','mode':name,**{k:v for k,v in meta['models'][name].items() if k!='losses'}}),flush=True)
    del values,model,opt,xs,mixedxs,vs,encoder
    gatebegin=time.process_time();routes={n:InteractionRoute(bot,n) for n in meta['models']}
    points={n:[] for n in routes}
    for b in banks:
        if partition(b['id'])!='calibration':continue
        bot.load_context(b['text'],b['instructions'])
        for route in routes.values():route.prepare()
        for conv in b['conversations']:
            history=[]
            for t in conv:
                reply=bot.answer(t['cliente'],history)
                if reply['status'] in ABSTAINED and t.get('accion')!='charla':
                    absent=t.get('accion') in ('abstenerse','derivar');keys=t.get('claves') or []
                    if absent or keys:
                        for name,route in routes.items():
                            raw=route.raw(t['cliente'],history)
                            if raw is not None:
                                y=int(not absent and all(contains(bot.context_units[raw['index']]['text'],k) for k in keys))
                                points[name].append((raw['score'],y))
                history += [t['cliente'],reply['text']]
        check()
    for name,values in points.items():
        meta['calibration'][name]={'blocks':isotonic(values),'rows':len(values),'correct_proposals':sum(y for _,y in values)}
    meta.update(gate_cpu_s=time.process_time()-gatebegin,cpu_s=time.process_time()-BOOT,
                wall_s=time.monotonic()-startwall,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    meta['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((ROOT/'experiments').glob('g99_*.py'))}
    check();(OUT/'models.json').write_text(json.dumps(meta,ensure_ascii=False))
    report={k:v for k,v in meta.items() if k!='calibration'}
    report['calibration']={n:{'rows':g['rows'],'correct_proposals':g['correct_proposals'],
                             'maximum':max(p[1] for p in g['blocks'])} for n,g in meta['calibration'].items()}
    report['metadata_sha256']=hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest()
    (ROOT/'results_v3/g99_training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'stage':'done','cpu_s':meta['cpu_s'],'calibration':report['calibration']}),flush=True)


if __name__=='__main__':
    try:train()
    except Exception as exc:
        (ROOT/'results_v3/g99_interruption.json').write_text(json.dumps({'error':repr(exc),'cpu_s':time.process_time()-BOOT,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n');raise

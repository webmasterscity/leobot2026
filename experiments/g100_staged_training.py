"""G100: controlled domain adaptation of G99 heads, preserving the representation."""
import time
BOOT=time.process_time()
import hashlib
import json
from pathlib import Path
import random
import resource
import numpy as np
import torch
from leobot import Bot
from experiments.g98_training import prepare,partition
from experiments.g99_training import Decision,decision_loss,valid_measure
from experiments.g99_interaction import PairFeatures,InteractionRoute,model_indices,predict_numpy,ROOT,OUT as OLD
from experiments.g57_kiosco import contains
from experiments.g97_backups import ABSTAINED
from experiments.g68_confianza import isotonic
from experiments.g100_route import StageRoute,OUT,NAMES


def check():
    if time.process_time()-BOOT>900:raise TimeoutError('G100 training CPU budget')
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>3*1024**2:raise MemoryError('G100 RSS budget')


def train():
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    wall=time.monotonic();base=ROOT/'.leobot-data/base_kiosco.json'
    original=json.loads((OLD/'models.json').read_text())
    assert hashlib.sha256(base.read_bytes()).hexdigest()==original['base_sha256']
    for name,m in original['models'].items():assert hashlib.sha256((OLD/f'{name}.npz').read_bytes()).hexdigest()==m['sha256']
    old98=ROOT/'.leobot-data/g98';meta98=json.loads((old98/'neural.json').read_text())
    with np.load(old98/'localized.npz',allow_pickle=False) as saved:embedding=dict(saved)
    with np.load(ROOT/'.leobot-data/g97/trained.npz',allow_pickle=False) as saved:initial=dict(saved)
    bot=Bot.load(base);rows,validation,banks,education=prepare(bot,meta98['vocabulary'],initial)
    for k in ('train_sha256','validation_sha256'):assert education[k]==original['education'][k]
    previous={}
    for b in banks:
        for ci,c in enumerate(b['conversations']):
            for ti,t in enumerate(c):previous[f'{b["id"]}/{ci}/{ti}']=c[ti-1]['cliente'] if ti else ''
    for r in rows+validation:r['previous']=previous.get(r['id'],'')
    business=[r for r in rows if r['source']=='synthetic_business_train']
    general=sorted((r for r in rows if r['source']=='human_sqac'),key=lambda r:hashlib.sha256(r['id'].encode()).digest())[:len(business)]
    assert len(business)==1737 and len(general)==1737
    groups={}
    for i,r in enumerate(business):groups.setdefault(r['group'],[]).append(i)
    perm=list(range(len(business)));rng=random.Random(1)
    for _,ids in sorted(groups.items()):
        shuffled=ids.copy();rng.shuffle(shuffled)
        for i,j in zip(ids,shuffled):perm[i]=j
    encoder=PairFeatures(bot,meta98['vocabulary'],embedding)
    datasets={'business':business,'general':general,'shuffled':business};features={}
    for stage,items in datasets.items():
        xs=[]
        for i,r in enumerate(items):
            q=business[perm[i]] if stage=='shuffled' else r
            xs.append(encoder.matrix(q['q'],q['previous'],encoder.prepare(r['units'])))
            if i%512==0:check()
        features[stage]=xs
        print(json.dumps({'stage':'features','kind':stage,'cpu_s':time.process_time()-BOOT}),flush=True)
    vs=[encoder.matrix(r['q'],r['previous'],encoder.prepare(r['units'])) for r in validation]
    OUT.mkdir(exist_ok=True)
    if (OUT/'models.json').exists():raise FileExistsError('Preserve G100 models')
    metadata={'engine':original['engine'],'base_sha256':original['base_sha256'],'education':education,
              'embedding_sha256':original['embedding_sha256'],'initial_models':{k:v['sha256'] for k,v in original['models'].items()},
              'stage_examples':{s:len(r) for s,r in datasets.items()},'models':{},'calibration':{},
              'preparation_cpu_s':time.process_time()-BOOT,'shuffled_changed':sum(business[i]['q']!=business[j]['q'] for i,j in enumerate(perm)),
              'general_subset_sha256':hashlib.sha256(json.dumps([r['id'] for r in general]).encode()).hexdigest()}
    for name in NAMES:
        begin=time.process_time();kind,stage=name.split('_');indices=model_indices(kind)
        with np.load(OLD/f'{kind}.npz',allow_pickle=False) as saved:oldweights=dict(saved)
        mean,scale=oldweights['mean'],oldweights['scale'];items=datasets[stage]
        values=[torch.from_numpy(((x[:,indices]-mean)/scale).astype('float32')) for x in features[stage]]
        torch.manual_seed(1);model=Decision(len(indices))
        with torch.no_grad():
            model.hidden.weight.copy_(torch.from_numpy(oldweights['w1'].T));model.hidden.bias.copy_(torch.from_numpy(oldweights['b1']))
            model.out.weight.copy_(torch.from_numpy(oldweights['w2'].T));model.out.bias.copy_(torch.from_numpy(oldweights['b2']))
        opt=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.001)
        order=list(range(len(items)));rng=random.Random(1);losses=[]
        for epoch in range(24):
            rng.shuffle(order);total=0.;seen=0
            for lo in range(0,len(order),64):
                check();ids=order[lo:lo+64];width=max(len(values[i]) for i in ids)
                x=torch.zeros((len(ids),width,len(indices)));valid=torch.zeros((len(ids),width),dtype=torch.bool)
                target=torch.zeros((len(ids),width+1),dtype=torch.bool)
                for j,i in enumerate(ids):
                    x[j,:len(values[i])]=values[i];valid[j,:len(values[i])]=True;target[j,items[i]['pos'] or [width]]=True
                loss=decision_loss(model(x),target,valid)
                opt.zero_grad();loss.backward();opt.step();total+=float(loss.detach())*len(ids);seen+=len(ids)
            losses.append(total/seen)
        weights={**model.export(),'mean':mean,'scale':scale};np.savez(OUT/f'{name}.npz',**weights)
        sample=features[stage][0][:,indices]
        with torch.no_grad():expected=model(torch.from_numpy(((sample-mean)/scale).astype('float32'))).numpy()
        error=float(np.max(np.abs(expected-predict_numpy(sample,weights))));assert error<1e-4
        checks={}
        for source in ('human_sqac','synthetic_business_train'):
            ids=[i for i,r in enumerate(validation) if r['source']==source]
            checks[source]=valid_measure(model,[validation[i] for i in ids],[vs[i] for i in ids],mean,scale,indices)
        metadata['models'][name]={'sha256':hashlib.sha256((OUT/f'{name}.npz').read_bytes()).hexdigest(),
            'cpu_s':time.process_time()-begin,'losses':losses,'export_max_error':error,'validation':checks}
        (OUT/'models.json').write_text(json.dumps(metadata,ensure_ascii=False))
        print(json.dumps({'stage':'saved','mode':name,'cpu_s':time.process_time()-BOOT,'validation':checks}),flush=True)
    del encoder,values,features,vs,model,opt
    begin=time.process_time();routes={n:StageRoute(bot,n) for n in NAMES};points={n:[] for n in NAMES}
    for b in banks:
        if partition(b['id'])!='calibration':continue
        bot.load_context(b['text'],b['instructions'])
        for route in routes.values():route.prepare()
        for c in b['conversations']:
            history=[]
            for t in c:
                reply=bot.answer(t['cliente'],history)
                if reply['status'] in ABSTAINED and t.get('accion')!='charla':
                    absent=t.get('accion') in ('abstenerse','derivar');keys=t.get('claves') or []
                    if absent or keys:
                        for n,route in routes.items():
                            raw=route.raw(t['cliente'],history)
                            if raw is not None:points[n].append((raw['score'],int(not absent and all(contains(bot.context_units[raw['index']]['text'],k) for k in keys))))
                history += [t['cliente'],reply['text']]
        check()
    for n,p in points.items():metadata['calibration'][n]={'blocks':isotonic(p),'rows':len(p),'correct_proposals':sum(y for _,y in p)}
    metadata.update(gate_cpu_s=time.process_time()-begin,cpu_s=time.process_time()-BOOT,wall_s=time.monotonic()-wall,
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    metadata['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'experiments').glob('g100_*.py'))}
    check();(OUT/'models.json').write_text(json.dumps(metadata,ensure_ascii=False))
    report={k:v for k,v in metadata.items() if k!='calibration'}
    report['calibration']={n:{'rows':g['rows'],'correct_proposals':g['correct_proposals'],'maximum':max(p[1] for p in g['blocks'])} for n,g in metadata['calibration'].items()}
    report['metadata_sha256']=hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest()
    (ROOT/'results_v3/g100_training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'stage':'done','cpu_s':metadata['cpu_s'],'calibration':report['calibration']}),flush=True)


if __name__=='__main__':
    try:train()
    except Exception as exc:
        (ROOT/'results_v3/g100_interruption.json').write_text(json.dumps({'error':repr(exc),'cpu_s':time.process_time()-BOOT,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n');raise

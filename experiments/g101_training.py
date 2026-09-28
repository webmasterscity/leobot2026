"""Learn only the evidence decision; the multilingual Model2Vec table is frozen."""
import time
BOOT=time.process_time()
import hashlib
import json
from collections import defaultdict
import random
import resource
import numpy as np
# Loading the 512 MB table has a transient peak. Finish that before importing
# torch/loading Bot; the runtime instance is then shared and never copied.
from experiments.g101_model2vec import static_model
static_model()
import torch
from leobot import Bot
from experiments.g98_training import prepare,partition
from experiments.g99_training import Decision,decision_loss,valid_measure
from experiments.g99_interaction import predict_numpy
from experiments.g101_model2vec import StaticFeatures,StaticRoute,ROOT,OUT
from experiments.g57_kiosco import contains
from experiments.g97_backups import ABSTAINED
from experiments.g68_confianza import isotonic


def check():
    if time.process_time()-BOOT>900:raise TimeoutError('G101 training CPU budget')
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>3*1024**2:raise MemoryError('G101 RSS budget')


def train():
    wall=time.monotonic();torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    old98=ROOT/'.leobot-data/g98';old=json.loads((old98/'neural.json').read_text())
    assert hashlib.sha256((ROOT/'.leobot-data/base_kiosco.json').read_bytes()).hexdigest()==old['base_sha256']
    acquisition=json.loads((ROOT/'results_v3/g101_acquisition.json').read_text())
    for f in acquisition['files']:
        digest=hashlib.sha256()
        with (OUT/'model'/f['file']).open('rb') as stream:
            while chunk:=stream.read(1024**2):digest.update(chunk)
        assert digest.hexdigest()==f['sha256']
    with np.load(ROOT/'.leobot-data/g97/trained.npz',allow_pickle=False) as saved:initial=dict(saved)
    bot=Bot.load(ROOT/'.leobot-data/base_kiosco.json')
    rows,validation,banks,education=prepare(bot,old['vocabulary'],initial)
    for k in ('train_sha256','validation_sha256'):assert education[k]==old['education'][k]
    encoder=StaticFeatures(bot);groups=defaultdict(list);perm=list(range(len(rows)));rng=random.Random(1)
    for i,r in enumerate(rows):groups[r['group']].append(i)
    for _,ids in sorted(groups.items()):
        mixed=ids.copy();rng.shuffle(mixed)
        for i,j in zip(ids,mixed):perm[i]=j
    xs=[];mixedxs=[];vs=[]
    for i,r in enumerate(rows):
        units=encoder.prepare(r['units']);xs.append(encoder.matrix(r['q'],units));mixedxs.append(encoder.matrix(rows[perm[i]]['q'],units))
        if i%512==0:
            check();print(json.dumps({'stage':'features','rows':i,'cpu_s':time.process_time()-BOOT}),flush=True)
    for r in validation:vs.append(encoder.matrix(r['q'],encoder.prepare(r['units'])))
    encoder.lexical.unit_cache.clear()
    if (OUT/'models.json').exists():raise FileExistsError('Preserve G101 artifacts')
    meta={'engine':old['engine'],'base_sha256':old['base_sha256'],'education':education,'models':{},'calibration':{},
          'representation_revision':acquisition['revision'],'load_ms':encoder.load_ms,
          'representation_shape':list(encoder.model.embedding.shape),'preparation_cpu_s':time.process_time()-BOOT,
          'shuffled_changed':sum(rows[i]['q']!=rows[j]['q'] for i,j in enumerate(perm))}
    for name,source in [('hybrid',xs),('shuffled',mixedxs)]:
        begin=time.process_time();stacked=np.concatenate(source);mean=stacked.mean(0);scale=np.maximum(stacked.std(0),1e-3);del stacked
        values=[torch.from_numpy(((x-mean)/scale).astype('float32')) for x in source]
        torch.manual_seed(1);model=Decision(16);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
        order=list(range(len(rows)));rng=random.Random(1);losses=[]
        for epoch in range(24):
            rng.shuffle(order);total=0.;seen=0
            for lo in range(0,len(order),64):
                check();ids=order[lo:lo+64];width=max(len(values[i]) for i in ids)
                x=torch.zeros((len(ids),width,16));valid=torch.zeros((len(ids),width),dtype=torch.bool)
                target=torch.zeros((len(ids),width+1),dtype=torch.bool)
                for j,i in enumerate(ids):
                    x[j,:len(values[i])]=values[i];valid[j,:len(values[i])]=True;target[j,rows[i]['pos'] or [width]]=True
                loss=decision_loss(model(x),target,valid)
                opt.zero_grad();loss.backward();opt.step();total+=float(loss.detach())*len(ids);seen+=len(ids)
            losses.append(total/seen)
            if (epoch+1)%6==0:print(json.dumps({'stage':'epoch','mode':name,'epoch':epoch+1,'loss':losses[-1],
                                               'cpu_s':time.process_time()-BOOT}),flush=True)
        weights={**model.export(),'mean':mean,'scale':scale};np.savez(OUT/f'{name}.npz',**weights)
        with torch.no_grad():expected=model(values[0]).numpy()
        error=float(np.max(np.abs(expected-predict_numpy(source[0],weights))));assert error<1e-4
        meta['models'][name]={'sha256':hashlib.sha256((OUT/f'{name}.npz').read_bytes()).hexdigest(),
            'cpu_s':time.process_time()-begin,'parameters':sum(p.numel() for p in model.parameters()),'losses':losses,
            'export_max_error':error,'validation':valid_measure(model,validation,vs,mean,scale,np.arange(16))}
        (OUT/'models.json').write_text(json.dumps(meta,ensure_ascii=False))
        print(json.dumps({'stage':'saved','mode':name,'validation':meta['models'][name]['validation']}),flush=True)
    meta['static_validation']={'answerable':sum(bool(r['pos']) for r in validation),
        'raw_correct':sum(int(np.argmax(x[:,13])) in r['pos'] for r,x in zip(validation,vs))}
    del values,model,opt,xs,mixedxs,vs
    begin=time.process_time();routes={n:StaticRoute(bot,n) for n in ('static','hybrid','shuffled')};points={n:[] for n in routes}
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
                            if raw is not None:points[name].append((raw['score'],int(not absent and all(contains(bot.context_units[raw['index']]['text'],k) for k in keys))))
                history += [t['cliente'],reply['text']]
        check()
    for name,p in points.items():meta['calibration'][name]={'blocks':isotonic(p),'rows':len(p),'correct_proposals':sum(y for _,y in p)}
    meta.update(gate_cpu_s=time.process_time()-begin,cpu_s=time.process_time()-BOOT,wall_s=time.monotonic()-wall,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    meta['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'experiments').glob('g101_*.py'))}
    check();(OUT/'models.json').write_text(json.dumps(meta,ensure_ascii=False))
    report={k:v for k,v in meta.items() if k!='calibration'}
    report['calibration']={n:{'rows':g['rows'],'correct_proposals':g['correct_proposals'],'maximum':max(x[1] for x in g['blocks'])} for n,g in meta['calibration'].items()}
    report['metadata_sha256']=hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest()
    (ROOT/'results_v3/g101_training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'stage':'done','cpu_s':meta['cpu_s'],'calibration':report['calibration']}),flush=True)


if __name__=='__main__':
    try:train()
    except Exception as exc:
        (ROOT/'results_v3/g101_interruption.json').write_text(json.dumps({'error':repr(exc),'cpu_s':time.process_time()-BOOT,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n');raise

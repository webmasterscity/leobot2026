"""Evaluate complete answers and calibration diagnostics without fitting on DEV."""
import time
BOOT=time.process_time()
import argparse
import hashlib
import json
import resource
from pathlib import Path
from leobot import Bot
from experiments import g97_neural,g97_evaluate
from experiments.g98_route import EvidenceRoute
from experiments.g101_model2vec import StaticRoute,ROOT,OUT
from experiments.g68_confianza import calibrated
from experiments.g97_backups import ABSTAINED
from experiments.g57_kiosco import contains

MODES=('baseline','localized')+tuple(n+'_'+t for n in ('static','hybrid','shuffled') for t in ('40','90'))


def factory(bot,name):
    if name=='localized':return EvidenceRoute(bot,'localized',root=ROOT/'.leobot-data/g98')
    n,threshold=name.rsplit('_',1);return StaticRoute(bot,n,float(threshold)/100)


def raw_choices(items):
    bot=Bot.load(ROOT/'.leobot-data/base_kiosco.json');routes={n:StaticRoute(bot,n) for n in ('static','hybrid','shuffled')}
    assert len({id(r.encoder.model) for r in routes.values()})==1
    counts={n:{'answerable':0,'correct_raw':0,'absent':0,'null_on_absent':0,'null_on_answerable':0,
               'calibrated_brier_sum':0.,'calibrated_brier_n':0} for n in routes}
    for b in items:
        bot.load_context(b['text'],b.get('instructions',''))
        for route in routes.values():route.prepare()
        for conv in b['conversations']:
            history=[]
            for t in conv:
                reply=bot.answer(t['cliente'],history)
                if reply['status'] in ABSTAINED:
                    answerable=t.get('accion')=='responder' and t.get('claves');absent=t.get('accion') in ('abstenerse','derivar')
                    if answerable or absent:
                        for n,route in routes.items():
                            raw=route.raw(t['cliente'],history);c=counts[n]
                            correct=bool(raw and answerable and all(contains(bot.context_units[raw['index']]['text'],k) for k in t['claves']))
                            if answerable:
                                c['answerable']+=1;c['correct_raw']+=correct;c['null_on_answerable']+=bool(raw and raw['null_selected'])
                            else:c['absent']+=1;c['null_on_absent']+=bool(raw and raw['null_selected'])
                            if raw is not None:
                                p=calibrated(route.gate['blocks'],raw['score']);c['calibrated_brier_sum']+=(p-int(correct))**2;c['calibrated_brier_n']+=1
                history += [t['cliente'],reply['text']]
    for c in counts.values():c['calibrated_brier']=c['calibrated_brier_sum']/max(1,c['calibrated_brier_n'])
    return counts


def run(items,modes):
    meta=json.loads((OUT/'models.json').read_text())
    for n,m in meta['models'].items():assert hashlib.sha256((OUT/f'{n}.npz').read_bytes()).hexdigest()==m['sha256']
    constructor=g97_neural.NeuralRoute;g97_neural.NeuralRoute=factory
    try:result=g97_evaluate.run(items,modes)
    finally:g97_neural.NeuralRoute=constructor
    result['experiment']='G101';result['g101_metadata_sha256']=hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest()
    result['g101_source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'experiments').glob('g101_*.py'))}
    result['raw_choices']=raw_choices(items);result['cpu_s_with_imports_and_raw']=time.process_time()-BOOT
    result['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if result['cpu_s_with_imports_and_raw']>240:raise TimeoutError('G101 evaluation CPU budget')
    if result['peak_rss_kib']>3*1024**2:raise MemoryError('G101 evaluation RSS budget')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset');p.add_argument('--output',required=True)
    p.add_argument('--modes',default=','.join(MODES));a=p.parse_args();path=Path(a.output)
    if path.exists():raise FileExistsError(path)
    items=json.loads(Path(a.dataset).read_text())['businesses'] if a.dataset else g97_evaluate.common()
    result=run(items,tuple(a.modes.split(',')));path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()

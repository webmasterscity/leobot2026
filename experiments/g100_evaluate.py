"""G100 comparison, using the unchanged G97 judgment and fallback wrapper."""
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
from experiments.g100_route import StageRoute,ROOT,OUT,NAMES
from experiments.g97_backups import ABSTAINED
from experiments.g57_kiosco import contains

MODES=('baseline','localized')+tuple(n+'_'+t for n in NAMES for t in ('40','90'))


def factory(bot,name):
    if name=='localized':return EvidenceRoute(bot,'localized',root=ROOT/'.leobot-data/g98')
    n,threshold=name.rsplit('_',1)
    return StageRoute(bot,n,float(threshold)/100)


def raw_choices(items):
    bot=Bot.load(ROOT/'.leobot-data/base_kiosco.json')
    routes={n:StageRoute(bot,n) for n in NAMES}
    counts={n:{'answerable':0,'correct_raw':0,'absent':0,'null_on_absent':0,'null_on_answerable':0} for n in routes}
    for b in items:
        bot.load_context(b['text'],b.get('instructions',''))
        for route in routes.values():route.prepare()
        for conv in b['conversations']:
            history=[]
            for t in conv:
                reply=bot.answer(t['cliente'],history)
                if reply['status'] in ABSTAINED:
                    answerable=t.get('accion')=='responder' and t.get('claves')
                    absent=t.get('accion') in ('abstenerse','derivar')
                    if answerable or absent:
                        for n,route in routes.items():
                            raw=route.raw(t['cliente'],history);c=counts[n]
                            if answerable:
                                c['answerable']+=1
                                c['correct_raw']+=bool(raw and all(contains(bot.context_units[raw['index']]['text'],k) for k in t['claves']))
                                c['null_on_answerable']+=bool(raw and raw['null_selected'])
                            else:c['absent']+=1;c['null_on_absent']+=bool(raw and raw['null_selected'])
                history += [t['cliente'],reply['text']]
    return counts


def run(items,modes):
    metadata=json.loads((OUT/'models.json').read_text())
    for n,m in metadata['models'].items():assert hashlib.sha256((OUT/f'{n}.npz').read_bytes()).hexdigest()==m['sha256']
    assert hashlib.sha256((ROOT/'.leobot-data/g98/localized.npz').read_bytes()).hexdigest()==metadata['embedding_sha256']
    constructor=g97_neural.NeuralRoute;g97_neural.NeuralRoute=factory
    try:result=g97_evaluate.run(items,modes)
    finally:g97_neural.NeuralRoute=constructor
    result['experiment']='G100';result['g100_metadata_sha256']=hashlib.sha256((OUT/'models.json').read_bytes()).hexdigest()
    result['g100_source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((ROOT/'experiments').glob('g100_*.py'))}
    result['raw_choices']=raw_choices(items);result['cpu_s_with_imports_and_raw']=time.process_time()-BOOT
    result['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if result['cpu_s_with_imports_and_raw']>300:raise TimeoutError('G100 evaluation CPU budget')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset');p.add_argument('--output',required=True)
    p.add_argument('--modes',default=','.join(MODES));a=p.parse_args();path=Path(a.output)
    if path.exists():raise FileExistsError(path)
    items=json.loads(Path(a.dataset).read_text())['businesses'] if a.dataset else g97_evaluate.common()
    result=run(items,tuple(a.modes.split(',')));path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()

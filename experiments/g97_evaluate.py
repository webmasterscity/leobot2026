"""Common evaluation for G97; no fitting or access to answer keys by routes."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time
from leobot import Bot
from experiments.g74_relation_coverage import BASE_SHA, ENGINE
from experiments.g57_kiosco import businesses, judge
from experiments.g68_confianza import DEV
from experiments.g97_backups import BackupBot, ManualRules, ABSTAINED

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.leobot-data/g97'
MODES=('baseline','rules','llm','trained','random','shuffled')


def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def common():
    selected=[]
    for bank in DEV:
        root=ROOT/'results_v3/kiosco'/bank
        rows=list(businesses(sorted(p for p in root.iterdir() if p.is_dir())))
        rows.sort(key=lambda r:hashlib.sha256((bank+'/'+r[0]).encode()).digest())
        selected += [{'id':bank+'/'+name,'text':text,'instructions':ins,'conversations':convs}
                     for name,text,ins,convs in rows[:2]]
    return selected


def summary(times):
    values=sorted(times)
    return {'n':len(values),'p50_ms':values[len(values)//2] if values else None,
            'p95_ms':values[min(len(values)-1,int(.95*len(values)))] if values else None,
            'max_ms':max(values) if values else None}


def run(items, modes=MODES):
    begin,wall=time.process_time(),time.monotonic()
    child0=resource.getrusage(resource.RUSAGE_CHILDREN)
    base=ROOT/'.leobot-data/base_kiosco.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest()==BASE_SHA
    assert subprocess.check_output(['git','rev-parse','HEAD:leobot'],text=True).strip()==ENGINE
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((ROOT/'experiments').glob('g97_*')) if p.suffix in ('.py','.cpp')}
    meta=json.loads((OUT/'neural.json').read_text())
    for name,info in meta['models'].items():
        assert hashlib.sha256((OUT/f'{name}.npz').read_bytes()).hexdigest()==info['sha256']
    bot=Bot.load(base)
    rows=[]; reports={}
    for name in modes:
        started=time.process_time(); mode_wall=time.monotonic()
        child_before=resource.getrusage(resource.RUSAGE_CHILDREN)
        if name=='baseline': route=None; wrapped=bot
        else:
            if name=='rules': route=ManualRules(bot)
            elif name=='llm':
                from experiments.g97_llm import LLMRoute
                route=LLMRoute(bot)
            else:
                from experiments.g97_neural import NeuralRoute
                route=NeuralRoute(bot,name)
            wrapped=BackupBot(bot,route,name)
        part=[]; prepare_cpu=0.; first_answer=None
        try:
            for business in items:
                prep=time.process_time()
                wrapped.load_context(business['text'],business.get('instructions',''))
                prepare_cpu+=time.process_time()-prep
                for ci,conversation in enumerate(business['conversations']):
                    history=[]
                    for ti,turn in enumerate(conversation):
                        t=time.perf_counter()
                        reply=wrapped.answer(turn['cliente'],history)
                        ms=(time.perf_counter()-t)*1000
                        if first_answer is None: first_answer=ms
                        history += [turn['cliente'],reply.get('text','')]
                        ev=reply.get('evidence')
                        literal=(not ev or (isinstance(ev.get('index'),int) and 0<=ev['index']<len(bot.context_units)
                                             and ev['unit']==bot.context_units[ev['index']]['text']))
                        row={'id':f'{business["id"]}/{ci}/{ti}','mode':name,'question':turn['cliente'],
                             'turn':turn,'reply':reply,'ms':ms,'literal':literal,
                             'verdict':judge(turn,reply,'g57')}
                        part.append(row)
                        child=resource.getrusage(resource.RUSAGE_CHILDREN)
                        cpu=time.process_time()-begin+child.ru_utime+child.ru_stime-child0.ru_utime-child0.ru_stime
                        native=sum(c.get('cpu_s',0) for c in route.calls) if name=='llm' else 0.
                        if cpu+native>1800 or time.monotonic()-wall>2400: raise TimeoutError('G97 evaluation budget')
                print(json.dumps({'stage':'business','mode':name,'business':business['id'],'rows':len(part)}),flush=True)
        finally:
            if name=='llm': route.close()
        answerable=[r for r in part if r['turn'].get('accion','responder')=='responder' and r['turn'].get('claves')]
        absent=[r for r in part if r['turn'].get('accion') in ('abstenerse','derivar')]
        useful=lambda r:r['verdict'] in ('correcta','cita_util')
        abstains=lambda r:r['reply']['status'] in ABSTAINED
        child=resource.getrusage(resource.RUSAGE_CHILDREN)
        report={'answerable':len(answerable),'useful':sum(map(useful,answerable)),
                'incorrect_quotes':sum(not useful(r) and not abstains(r) for r in answerable),
                'absent':len(absent),'quotes_without_data':sum(not abstains(r) for r in absent),
                'literal_failures':sum(not r['literal'] for r in part),
                'latency':summary([r['ms'] for r in part]),
                'activated_latency':summary(wrapped.activated_ms) if route else summary([]),
                'first_answer_ms':first_answer,'preparation_cpu_s':prepare_cpu,
                'response_sha256':digest([(r['id'],r['reply']) for r in part]),
                'parent_cpu_s':time.process_time()-started,
                'child_cpu_s':child.ru_utime+child.ru_stime-child_before.ru_utime-child_before.ru_stime,
                'wall_s':time.monotonic()-mode_wall,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        if name=='llm':
            report['llm']={'load_ms':route.load_ms,'ready':route.ready,'calls':len(route.calls),
                           'invalid_or_zero':sum(not c.get('text','').strip().isdigit() or c['text'].strip()=='0' for c in route.calls),
                           'native_latency':summary([c['ms'] for c in route.calls]),
                           'errors':[c.get('error') for c in route.calls if c.get('error')],
                           'peak_rss_kib':max([route.ready['peak_rss_kib']]+[c['peak_rss_kib'] for c in route.calls])}
        reports[name]=report; rows.extend(part)
        print(json.dumps({'stage':'measured','mode':name,**report}),flush=True)
    baseline={r['id']:r for r in rows if r['mode']=='baseline'}
    if baseline:
        for name,report in reports.items():
            own=[r for r in rows if r['mode']==name]
            active=[r for r in own if baseline[r['id']]['reply']['status'] in ABSTAINED]
            report['new_useful']=sum(r['verdict'] in ('correcta','cita_util') for r in active)
            report['new_incorrect']=sum(r['reply']['status'] not in ABSTAINED and r['verdict'] not in ('correcta','cita_util') for r in active)
            report['changed_existing_answers']=sum(r['reply']!=baseline[r['id']]['reply'] for r in own
                                                    if baseline[r['id']]['reply']['status'] not in ABSTAINED)
            report['fallback_useful_ceiling']=report['answerable']-reports['baseline']['incorrect_quotes']
    cpu_child=resource.getrusage(resource.RUSAGE_CHILDREN)
    assert subprocess.check_output(['git','rev-parse','HEAD:leobot'],text=True).strip()==ENGINE
    return {'experiment':'G97','engine':ENGINE,'base_sha256':BASE_SHA,'dataset_sha256':digest(items),
            'source_sha256':sources,
            'businesses':[b['id'] for b in items],'reports':reports,'rows':rows,
            'cpu_s':time.process_time()-begin+cpu_child.ru_utime+cpu_child.ru_stime-child0.ru_utime-child0.ru_stime,
            'wall_s':time.monotonic()-wall,'neural_metadata_sha256':hashlib.sha256((OUT/'neural.json').read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--dataset'); p.add_argument('--output',required=True)
    p.add_argument('--modes',default=','.join(MODES)); args=p.parse_args()
    target=Path(args.output)
    if target.exists(): raise FileExistsError(target)
    items=json.loads(Path(args.dataset).read_text())['businesses'] if args.dataset else common()
    result=run(items,tuple(args.modes.split(',')))
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__': main()

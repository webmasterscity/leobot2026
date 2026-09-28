"""Raw neural proposal diagnosis on frozen data; never supplies public answers."""
import argparse
import json
from pathlib import Path
import resource
import time
from leobot import Bot
from experiments.g97_evaluate import common
from experiments.g97_backups import ABSTAINED
from experiments.g97_neural import NeuralRoute, OUT
from experiments.g57_kiosco import contains


def main():
    p=argparse.ArgumentParser(); p.add_argument('--dataset'); p.add_argument('--output',required=True)
    args=p.parse_args(); begin=time.process_time(); wall=time.monotonic()
    items=json.loads(Path(args.dataset).read_text())['businesses'] if args.dataset else common()
    bot=Bot.load('.leobot-data/base_kiosco.json')
    routes={n:NeuralRoute(bot,n) for n in ('trained','random','shuffled')}
    counts={n:{'unknown_answerable':0,'correct_raw_proposal':0,'unknown_absent':0,
               'proposal_on_absent':0,'maximum_calibrated_confidence':max(x[1] for x in r.gate['calibration'])}
            for n,r in routes.items()}
    for b in items:
        bot.load_context(b['text'],b.get('instructions',''))
        for r in routes.values(): r.prepare()
        for conv in b['conversations']:
            history=[]
            for t in conv:
                reply=bot.answer(t['cliente'],history)
                history += [t['cliente'],reply['text']]
                if reply['status'] not in ABSTAINED: continue
                for name,r in routes.items():
                    raw=r.raw(t['cliente']); c=counts[name]
                    if t.get('accion')=='responder' and t.get('claves'):
                        c['unknown_answerable']+=1
                        c['correct_raw_proposal']+=bool(raw and all(contains(bot.context_units[raw['index']]['text'],k) for k in t['claves']))
                    elif t.get('accion') in ('abstenerse','derivar'):
                        c['unknown_absent']+=1; c['proposal_on_absent']+=raw is not None
    result={'scope':'Ungated proposal ceiling on original abstentions, not actual useful responses',
            'counts':counts,'cpu_s':time.process_time()-begin,'wall_s':time.monotonic()-wall,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    target=Path(args.output)
    if target.exists(): raise FileExistsError(target)
    target.write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result),flush=True)


if __name__=='__main__': main()

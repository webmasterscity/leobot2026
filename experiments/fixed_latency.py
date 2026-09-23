"""Fixed 100k-fact latency gate; see prereg/performance-1-latencia.md."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import resource
import subprocess
import time
from pathlib import Path

from leobot import Bot
from leobot.core import Atom, Rule


ROOT=Path(__file__).resolve().parents[1]
FIXED_SEED=int('644c5552',16)
CATEGORIES=('known','reasoning','procedure','spanish','unknown_spanish')


def percentile(values,proportion):
    ordered=sorted(values)
    return ordered[max(0,math.ceil(proportion*len(ordered))-1)]


def setup():
    started=time.perf_counter_ns();cpu=time.process_time_ns()
    bot=Bot()
    for text,before,after in (
        ('triplica 2',(2,),(6,)),('triplica 3',(3,),(9,)),
        ('triplica 5',(5,),(15,)),
    ):
        bot.observe_transition(text,before,after)
    for text in ('equipo alfa enlaza modulo rojo',
                 'grupo beta enlaza pieza azul',
                 'unidad gamma enlaza nodo verde'):
        bot.respond(text)
    for index in range(100_000):
        bot.kb.add(Atom('edge',(f'n{index}',f'n{index+1}')),'latency_fixed')
    bot.kb.add_rule(Rule('latency_hop2',Atom('hop2',('?x','?y')),
                         (Atom('edge',('?x','?z')),
                          Atom('edge',('?z','?y')))))
    return bot,{'wall_ms':(time.perf_counter_ns()-started)/1e6,
                'cpu_ms':(time.process_time_ns()-cpu)/1e6,
                'facts':bot.kb.stats()['facts']}


def query_set(bot):
    rng=random.Random(FIXED_SEED)
    indices=rng.sample(range(100,99_897),20)
    queries={category:[] for category in CATEGORIES}
    for index in indices:
        queries['known'].append((lambda i=index:bot.answer_atom(
            Atom('edge',(f'n{i}',f'n{i+1}'))), 'supported'))
        queries['reasoning'].append((lambda i=index:bot.answer_atom(
            Atom('hop2',(f'n{i}',f'n{i+2}'))), 'supported'))
        number=7+index%20
        queries['procedure'].append((lambda n=number:bot.respond(f'triplica {n}'),
                                     'procedure_executed'))
        queries['spanish'].append((lambda:bot.respond(
            '¿equipo alfa enlaza modulo rojo?'), 'supported'))
        queries['unknown_spanish'].append((lambda:bot.respond(
            '¿equipo alfa separa modulo rojo?'), 'unrecognized'))
    return queries


def run(tag):
    engine_tree=subprocess.check_output(('git','rev-parse',f'{tag}:leobot'),
                                        cwd=ROOT,text=True).strip()
    if subprocess.check_output(('git','diff','--name-only',tag,'--','leobot'),
                               cwd=ROOT,text=True).strip():
        raise RuntimeError('El motor de trabajo no coincide con el tag solicitado.')
    affinity=None
    if hasattr(os,'sched_getaffinity') and hasattr(os,'sched_setaffinity'):
        try:
            current=os.sched_getaffinity(0)
            chosen=min(current)
            os.sched_setaffinity(0,{chosen})
            affinity=chosen
        except OSError:
            pass
    bot,build=setup()
    queries=query_set(bot)
    # Same 20 warmups for every tag, outside the measured samples.
    for repeat in range(4):
        for category in CATEGORIES:
            action,expected=queries[category][repeat]
            actual=action()
            if actual.get('status')!=expected:
                raise AssertionError((category,expected,actual.get('status')))
    samples={category:[] for category in CATEGORIES}
    cpu_samples={category:[] for category in CATEGORIES}
    errors=[]
    for index in range(20):
        for category in CATEGORIES:
            action,expected=queries[category][index]
            before_wall=time.perf_counter_ns();before_cpu=time.process_time_ns()
            actual=action()
            cpu_ms=(time.process_time_ns()-before_cpu)/1e6
            wall_ms=(time.perf_counter_ns()-before_wall)/1e6
            samples[category].append(wall_ms)
            cpu_samples[category].append(cpu_ms)
            if actual.get('status')!=expected:
                errors.append({'category':category,'case':index,
                               'expected':expected,'actual':actual.get('status')})
            if category=='procedure' and actual.get('result')!=(3*(7+(
                    random.Random(FIXED_SEED).sample(range(100,99_897),20)[index]%20)),):
                errors.append({'category':category,'case':index,'reason':'wrong_result'})
    summary={}
    for category,values in samples.items():
        summary[category]={'n':len(values),'p50_ms':round(percentile(values,0.5),5),
                           'p95_ms':round(percentile(values,0.95),5),
                           'max_ms':round(max(values),5),
                           'cpu_total_ms':round(sum(cpu_samples[category]),5)}
    all_samples=[value for category in CATEGORIES for value in samples[category]]
    summary['overall']={'n':len(all_samples),
                        'p50_ms':round(percentile(all_samples,0.5),5),
                        'p95_ms':round(percentile(all_samples,0.95),5),
                        'max_ms':round(max(all_samples),5)}
    limits={'known_p95':summary['known']['p95_ms']<=10,
            'procedure_p95':summary['procedure']['p95_ms']<=10,
            'spanish_p95':summary['spanish']['p95_ms']<=10,
            'unknown_spanish_p95':summary['unknown_spanish']['p95_ms']<=10,
            'reasoning_p95':summary['reasoning']['p95_ms']<=200,
            'absolute_max':summary['overall']['max_ms']<=1000,
            'correctness':not errors}
    result={'tag':tag,'engine_tree':engine_tree,'fixed_seed':FIXED_SEED,
            'pythonhashseed':os.environ.get('PYTHONHASHSEED'),
            'cpu_affinity':affinity,'build':build,'summary':summary,
            'limits':limits,'errors':errors,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if subprocess.check_output(('git','diff','--name-only',tag,'--','leobot'),
                               cwd=ROOT,text=True).strip():
        raise RuntimeError('El motor cambió durante la prueba.')
    output=ROOT/'results_v3'/f'latency_{tag}_hashseed{os.environ.get("PYTHONHASHSEED","unset")}.json'
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--tag',default='estable-A-1')
    args=parser.parse_args()
    run(args.tag)

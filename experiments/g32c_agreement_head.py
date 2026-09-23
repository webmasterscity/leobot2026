"""G-32c evaluator: agreement and head-word contexts; memory measured per process.

See prereg/G-32c-concordancia-y-cabeza-en-funciones.md.
Run from the repository root: python3 -m experiments.g32c_agreement_head [--dev]
"""
from __future__ import annotations

import gc
import json
import os
import random
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.g31_dependency_functions import split, educate, evaluate
from experiments.g32_backoff_arcs import baseline_uas

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-32c-concordancia-y-cabeza-en-funciones.md'


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def reserve_for(dev,seed):
    pool=[s for s in split('dev' if dev else 'test') if len(s[0])<=60]
    return random.Random(seed if seed is not None else 3131).sample(pool,300)


def control(kind,dev,seed):
    """Run one control with its own educated bot (called in a child process)."""
    train=split('train'); reserve=reserve_for(dev,seed)
    if kind=='labels':
        bot,_=educate(train,shuffle=True)
    else:
        rng=random.Random(7); bot=Bot()
        for words,tags,heads,labels in train:
            heads=[rng.choice([h for h in range(len(words)+1) if h!=i+1]) for i in range(len(words))]
            bot.observe_parsed_sentence(words,tags,heads,labels)
        bot.consolidate_syntax()
    result,_=evaluate(bot,reserve)
    result['rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps(result))


def child(kind,dev,seed):
    command=[sys.executable,'-m','experiments.g32c_agreement_head','--control',kind,
             '--seed',str(seed)]+(['--dev'] if dev else [])
    out=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=1800,check=True,
                       env={**os.environ})
    return json.loads(out.stdout.strip().splitlines()[-1])


def main():
    args=sys.argv[1:]; dev='--dev' in args
    if '--control' in args:
        seed=args[args.index('--seed')+1]
        control(args[args.index('--control')+1],dev,None if seed=='None' else int(seed)); return
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean=not git('status','--porcelain','--','leobot','experiments/g32c_agreement_head.py')
    seed=None if dev else int(before[:8],16)
    train=split('train'); reserve=reserve_for(dev,seed)
    bot,edu_cpu=educate(train)
    result,outputs=evaluate(bot,reserve)
    ablation,_=evaluate(bot,reserve,lexical=False)
    fresh_none=all(Bot().parse_words(s[0]) is None for s in reserve)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; bot.save(path)
        del bot; gc.collect()
        restored=Bot.load(path)
    _,restored_outputs=evaluate(restored,reserve)
    del restored; gc.collect()
    main_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    shuffled=child('labels',dev,seed); shuffled_heads=child('heads',dev,seed)
    base_uas,base_tree=baseline_uas(train,reserve)
    after=git('rev-parse','HEAD:leobot')
    rss=max(main_rss,shuffled['rss_kib'],shuffled_heads['rss_kib'])
    budget=edu_cpu<=240 and rss<=768*1024 and result['p95_ms'] is not None and result['p95_ms']<=100
    gate=(result['tag_accuracy']>=0.92 and result['uas']>=0.75 and result['uas']-base_uas>=0.01 and
          result['las']>=0.70 and result['f1']['nsubj']>=0.60 and result['f1']['obj']>=0.60 and
          result['label_given_head']>=0.85 and result['las']-ablation['las']>=0.02 and
          shuffled['las']<=0.40 and shuffled_heads['uas']<=0.35 and fresh_none and
          restored_outputs==outputs and budget and before==after and clean)
    out={'kind':'G32c_agreement_head','preregistration':PREREG,'development':dev,'engine_tree':before,
         'engine_unchanged':before==after,'engine_committed':clean,'seed':seed,
         'hashseed':os.environ.get('PYTHONHASHSEED'),'reserve_sentences':len(reserve),
         'reserve_words':sum(len(s[0]) for s in reserve),'treatment':result,
         'baseline_freeze_G31_uas':base_uas,'baseline_engine_tree':base_tree,
         'ablation_no_lexical_marker':ablation,'shuffled_labels':shuffled,'shuffled_heads':shuffled_heads,
         'fresh_unparsed':fresh_none,'restart_identical':restored_outputs==outputs,
         'education_cpu_s':round(edu_cpu,2),'cpu_total_s':round(time.process_time()-cpu0,2),
         'wall_total_s':round(time.perf_counter()-wall0,2),'main_rss_kib':main_rss,
         'max_rss_kib_per_process':rss,'budget_ok':budget,'gate_pass':gate}
    name='g32c_agreement_head_dev' if dev else f'g32c_agreement_head_{seed}'
    (ROOT/'results_v3'/f'{name}_hashseed{out["hashseed"]}.json').write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()

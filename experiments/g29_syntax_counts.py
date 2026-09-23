"""G-29 evaluator: word classes and dependencies learned by counting.

See prereg/G-29-sintaxis-aprendida-por-conteo.md.
Run from the repository root: python3 -m experiments.g29_syntax_counts [--dev]
"""
from __future__ import annotations

import json
import os
import random
import resource
import subprocess
import sys
import tempfile
import time
import urllib.request
from hashlib import sha256
from pathlib import Path

from leobot import Bot

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-29-sintaxis-aprendida-por-conteo.md'
REV='20adddbfcdd773c6dc97ba48ea11ca9364e74185'
SHA={'train':'47b6fc49d6ed48a016e7fa5ad9f5c7ecf3ec21e9db005df3ea14d10f07c6deb6',
     'dev':'1a132068062edf2654fb45b41cd4c59ba7e5c18e7c5f642ed5a9cc351fd9f0fe',
     'test':'679f1c05ca654aa26801c80319df45f8f97606718fb534b91755b48f3e67fa6f'}
CACHE=Path(os.environ.get('ANCORA_CACHE','/tmp'))


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def split(name):
    path=CACHE/f'es_ancora-ud-{name}.conllu'
    if not (path.exists() and sha256(path.read_bytes()).hexdigest()==SHA[name]):
        url=(f'https://raw.githubusercontent.com/UniversalDependencies/UD_Spanish-AnCora/'
             f'{REV}/es_ancora-ud-{name}.conllu')
        data=urllib.request.urlopen(url,timeout=60).read()
        if sha256(data).hexdigest()!=SHA[name]:
            raise RuntimeError(f'AnCora {name} cambió.')
        path.write_bytes(data)
    sentences=[]; words=[]; tags=[]; heads=[]
    for line in path.read_text(encoding='utf8').split('\n'):
        if not line.strip():
            if words:
                sentences.append((words,tags,heads))
            words=[]; tags=[]; heads=[]
            continue
        if line.startswith('#'):
            continue
        cols=line.split('\t')
        if '-' in cols[0] or '.' in cols[0]:
            continue
        words.append(cols[1]); tags.append(cols[3]); heads.append(int(cols[6]))
    if words:
        sentences.append((words,tags,heads))
    return sentences


def educate(sentences,shuffle=None):
    bot=Bot(); started=time.process_time()
    for words,tags,heads in sentences:
        if shuffle is not None:
            heads=[shuffle.choice([h for h in range(len(words)+1) if h!=i+1]) for i in range(len(words))]
        bot.observe_parsed_sentence(words,tags,heads)
    bot.consolidate_syntax()
    return bot,time.process_time()-started


def evaluate(bot,sentences,gold_tags=False):
    tag_ok=arc_ok=total=0; latency=[]; trees=[]
    for words,tags,heads in sentences:
        started=time.perf_counter()
        parsed=bot.parse_words(words,tags if gold_tags else None)
        if len(words)<=40:
            latency.append((time.perf_counter()-started)*1000)
        if parsed is None:
            trees.append(None); total+=len(words); continue
        trees.append(parsed['heads'])
        tag_ok+=sum(a==b for a,b in zip(parsed['tags'],tags))
        arc_ok+=sum(a==b for a,b in zip(parsed['heads'],heads))
        total+=len(words)
    ordered=sorted(latency)
    p95=ordered[max(0,-(-95*len(ordered)//100)-1)] if ordered else None
    return {'tag_accuracy':round(tag_ok/total,4),'uas':round(arc_ok/total,4),
            'p95_ms':round(p95,3) if p95 is not None else None},trees


def chain(sentences,direction):
    ok=total=0
    for words,_,heads in sentences:
        n=len(words)
        guess=[i+2 if i+1<n else 0 for i in range(n)] if direction=='right' else [i for i in range(n)]
        ok+=sum(a==b for a,b in zip(guess,heads)); total+=n
    return round(ok/total,4)


def rename(sentences,known):
    rng=random.Random(29); out=[]
    for words,tags,heads in sentences:
        new=[]
        for w in words:
            if w in known or not w.isalpha() or len(w)<4:
                new.append(w); continue
            stem=''.join(rng.choice('bcdfglmnprstv')+rng.choice('aeiou') for _ in range(2))
            fresh=stem+w[-3:]
            new.append(fresh.capitalize() if w[:1].isupper() else fresh)
        out.append((new,tags,heads))
    return out


def main():
    dev='--dev' in sys.argv[1:]
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean=not git('status','--porcelain','--','leobot','experiments/g29_syntax_counts.py')
    train=split('train')
    if dev:
        seed=None; pool=split('dev')
    else:
        seed=int(before[:8],16); pool=split('test')
    pool=[s for s in pool if len(s[0])<=60]
    reserve=random.Random(seed if seed is not None else 2929).sample(pool,300)
    limit=int(os.environ.get('G29_TRAIN_LIMIT','0')) if dev else 0
    education=train[:limit] if limit else train
    bot,edu_cpu=educate(education)
    result,trees=evaluate(bot,reserve)
    gold_tag_result,_=evaluate(bot,reserve,gold_tags=True)
    shuffled,_=educate(education,shuffle=random.Random(7))
    shuffled_result,_=evaluate(shuffled,reserve)
    fresh=Bot(); fresh_none=all(fresh.parse_words(w) is None for w,_,_ in reserve)
    known=set(bot.syntax_model['word_counts'])
    renamed_result,_=evaluate(bot,rename(reserve,known))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; bot.save(path); restored=Bot.load(path)
    _,restored_trees=evaluate(restored,reserve)
    after=git('rev-parse','HEAD:leobot')
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    best_chain=max(chain(reserve,'right'),chain(reserve,'left'))
    budget=edu_cpu<=180 and rss<=512*1024 and result['p95_ms'] is not None and result['p95_ms']<=100
    gate=(result['tag_accuracy']>=0.92 and result['uas']>=0.70 and result['uas']-best_chain>=0.20 and
          shuffled_result['uas']<=0.35 and fresh_none and restored_trees==trees and budget and
          before==after and clean)
    out={'kind':'G29_syntax_counts','preregistration':PREREG,'development':dev,'engine_tree':before,
         'engine_unchanged':before==after,'engine_committed':clean,'seed':seed,
         'hashseed':os.environ.get('PYTHONHASHSEED'),'education_sentences':len(education),
         'reserve_sentences':len(reserve),'reserve_words':sum(len(s[0]) for s in reserve),
         'treatment':result,'gold_tags_uas':gold_tag_result['uas'],
         'chain_right':chain(reserve,'right'),'chain_left':chain(reserve,'left'),
         'shuffled_heads':shuffled_result,'renamed_diagnostic':renamed_result,
         'fresh_unparsed':fresh_none,'restart_identical':restored_trees==trees,
         'education_cpu_s':round(edu_cpu,2),'cpu_total_s':round(time.process_time()-cpu0,2),
         'wall_total_s':round(time.perf_counter()-wall0,2),'max_rss_kib':rss,
         'budget_ok':budget,'gate_pass':gate}
    name='g29_syntax_counts_dev' if dev else f'g29_syntax_counts_{seed}'
    (ROOT/'results_v3'/f'{name}_hashseed{out["hashseed"]}.json').write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()

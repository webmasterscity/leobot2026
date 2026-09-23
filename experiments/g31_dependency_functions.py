"""G-31 evaluator: dependency functions learned by counting.

See prereg/G-31-funciones-de-dependencia-por-conteo.md.
Run from the repository root: python3 -m experiments.g31_dependency_functions [--dev]
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
from pathlib import Path

from leobot import Bot
from experiments.g29_syntax_counts import CACHE, REV, SHA, chain

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-31-funciones-de-dependencia-por-conteo.md'
KEY_LABELS=('nsubj','obj','obl','iobj','amod')


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def split(name):
    from experiments.g29_syntax_counts import split as base
    base(name)   # downloads and verifies the SHA-256
    path=CACHE/f'es_ancora-ud-{name}.conllu'
    sentences=[]; row=([],[],[],[])
    for line in path.read_text(encoding='utf8').split('\n'):
        if not line.strip():
            if row[0]:
                sentences.append(row)
            row=([],[],[],[]); continue
        if line.startswith('#'):
            continue
        cols=line.split('\t')
        if '-' in cols[0] or '.' in cols[0]:
            continue
        row[0].append(cols[1]); row[1].append(cols[3]); row[2].append(int(cols[6]))
        row[3].append(cols[7].split(':')[0])
    if row[0]:
        sentences.append(row)
    return sentences


def educate(sentences,shuffle=False):
    bot=Bot(); rng=random.Random(31); started=time.process_time()
    for words,tags,heads,labels in sentences:
        if shuffle:
            labels=list(labels); rng.shuffle(labels)
        bot.observe_parsed_sentence(words,tags,heads,labels)
    bot.consolidate_syntax()
    return bot,time.process_time()-started


def evaluate(bot,sentences,lexical=True):
    tag_ok=uas=las=label_ok=head_ok=total=0; latency=[]; outputs=[]
    tp={l:0 for l in KEY_LABELS}; fp=dict(tp); fn=dict(tp)
    for words,tags,heads,labels in sentences:
        started=time.perf_counter(); parsed=bot.parse_words(words)
        if len(words)<=40:
            latency.append((time.perf_counter()-started)*1000)
        if parsed is None or 'labels' not in parsed:
            outputs.append(None); total+=len(words)
            for gl in labels:
                if gl in fn: fn[gl]+=1
            continue
        predicted=parsed['labels'] if lexical else bot.label_arcs(words,parsed['tags'],parsed['heads'],lexical=False)
        outputs.append((parsed['heads'],predicted))
        for pt,gt,ph,gh,pl,gl in zip(parsed['tags'],tags,parsed['heads'],heads,predicted,labels):
            tag_ok+=pt==gt; total+=1
            if ph==gh:
                uas+=1; head_ok+=1; label_ok+=pl==gl; las+=pl==gl
            for l in KEY_LABELS:
                if pl==l and ph==gh and gl==l: tp[l]+=1
                elif pl==l: fp[l]+=1
                if gl==l and not (pl==l and ph==gh): fn[l]+=1
    f1={l:round(2*tp[l]/max(1,2*tp[l]+fp[l]+fn[l]),4) for l in KEY_LABELS}
    ordered=sorted(latency); p95=ordered[max(0,-(-95*len(ordered)//100)-1)] if ordered else None
    return {'tag_accuracy':round(tag_ok/total,4),'uas':round(uas/total,4),'las':round(las/total,4),
            'label_given_head':round(label_ok/max(1,head_ok),4),'f1':f1,
            'p95_ms':round(p95,3) if p95 is not None else None},outputs


def main():
    dev='--dev' in sys.argv[1:]
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean=not git('status','--porcelain','--','leobot','experiments/g31_dependency_functions.py')
    train=split('train')
    seed=None if dev else int(before[:8],16)
    pool=[s for s in split('dev' if dev else 'test') if len(s[0])<=60]
    reserve=random.Random(seed if seed is not None else 3131).sample(pool,300)
    bot,edu_cpu=educate(train)
    result,outputs=evaluate(bot,reserve)
    ablation,_=evaluate(bot,reserve,lexical=False)
    shuffled_bot,_=educate(train,shuffle=True)
    shuffled,_=evaluate(shuffled_bot,reserve)
    fresh=Bot(); fresh_none=all(fresh.parse_words(s[0]) is None for s in reserve)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; bot.save(path); restored=Bot.load(path)
    _,restored_outputs=evaluate(restored,reserve)
    after=git('rev-parse','HEAD:leobot')
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget=edu_cpu<=240 and rss<=768*1024 and result['p95_ms'] is not None and result['p95_ms']<=100
    gate=(result['tag_accuracy']>=0.92 and result['uas']>=0.70 and result['las']>=0.63 and
          result['label_given_head']>=0.85 and result['f1']['nsubj']>=0.60 and result['f1']['obj']>=0.60 and
          result['las']-ablation['las']>=0.02 and shuffled['las']<=0.40 and fresh_none and
          restored_outputs==outputs and budget and before==after and clean)
    out={'kind':'G31_dependency_functions','preregistration':PREREG,'development':dev,'engine_tree':before,
         'engine_unchanged':before==after,'engine_committed':clean,'seed':seed,
         'hashseed':os.environ.get('PYTHONHASHSEED'),'treebank_revision':REV,
         'reserve_sentences':len(reserve),'reserve_words':sum(len(s[0]) for s in reserve),
         'treatment':result,'ablation_no_lexical_marker':ablation,'shuffled_labels':shuffled,
         'fresh_unlabelled':fresh_none,'restart_identical':restored_outputs==outputs,
         'education_cpu_s':round(edu_cpu,2),'cpu_total_s':round(time.process_time()-cpu0,2),
         'wall_total_s':round(time.perf_counter()-wall0,2),'max_rss_kib':rss,'budget_ok':budget,
         'gate_pass':gate}
    name='g31_dependency_functions_dev' if dev else f'g31_dependency_functions_{seed}'
    (ROOT/'results_v3'/f'{name}_hashseed{out["hashseed"]}.json').write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()

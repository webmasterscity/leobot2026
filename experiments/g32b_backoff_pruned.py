"""G-32b evaluator: backoff arcs with pruning of uninformative contexts.

See prereg/G-32b-arcos-por-respaldo-con-poda.md.
Run from the repository root: python3 -m experiments.g32b_backoff_pruned [--dev]
"""
from __future__ import annotations

import json
import os
import random
import resource
import subprocess
import sys
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import Path

from leobot import Bot
from experiments.g31_dependency_functions import split, educate, evaluate

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-32b-arcos-por-respaldo-con-poda.md'
BASELINE_TAG='freeze-G-31'
CHILD="""
import json,sys,time
sys.path.insert(0,sys.argv[1])
from leobot import Bot
data=json.load(open(sys.argv[2]))
bot=Bot()
for w,t,h,l in data['train']:
    bot.observe_parsed_sentence(w,t,h,l)
bot.consolidate_syntax()
ok=total=0
for w,t,h,l in data['reserve']:
    p=bot.parse_words(w); ok+=sum(a==b for a,b in zip(p['heads'],h)); total+=len(w)
import leobot
print(json.dumps({'uas':round(ok/total,4),'engine_path':leobot.__file__}))
"""


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def baseline_uas(train,reserve):
    with tempfile.TemporaryDirectory() as directory:
        archive=subprocess.check_output(('git','archive',BASELINE_TAG,'leobot'),cwd=ROOT)
        tarfile.open(fileobj=BytesIO(archive)).extractall(directory)
        data=Path(directory)/'data.json'
        data.write_text(json.dumps({'train':train,'reserve':reserve}),encoding='utf8')
        out=subprocess.run((sys.executable,'-c',CHILD,directory,str(data)),capture_output=True,text=True,
                           timeout=900,check=True,env={**os.environ,'PYTHONPATH':directory},cwd=directory)
        row=json.loads(out.stdout.strip().splitlines()[-1])
        if not row['engine_path'].startswith(directory):
            raise RuntimeError('El motor base no es el archivado.')
        return row['uas'],git('rev-parse',f'{BASELINE_TAG}:leobot')


def main():
    dev='--dev' in sys.argv[1:]
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean=not git('status','--porcelain','--','leobot','experiments/g32b_backoff_pruned.py')
    train=split('train')
    seed=None if dev else int(before[:8],16)
    pool=[s for s in split('dev' if dev else 'test') if len(s[0])<=60]
    reserve=random.Random(seed if seed is not None else 3131).sample(pool,300)
    bot,edu_cpu=educate(train)
    result,outputs=evaluate(bot,reserve)
    ablation,_=evaluate(bot,reserve,lexical=False)
    shuffled_bot,_=educate(train,shuffle=True)
    shuffled,_=evaluate(shuffled_bot,reserve)
    rng=random.Random(7); heads_shuffled=Bot()
    for words,tags,heads,labels in train:
        heads=[rng.choice([h for h in range(len(words)+1) if h!=i+1]) for i in range(len(words))]
        heads_shuffled.observe_parsed_sentence(words,tags,heads,labels)
    heads_shuffled.consolidate_syntax()
    shuffled_heads,_=evaluate(heads_shuffled,reserve)
    fresh_none=all(Bot().parse_words(s[0]) is None for s in reserve)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; bot.save(path); restored=Bot.load(path)
    _,restored_outputs=evaluate(restored,reserve)
    base_uas,base_tree=baseline_uas(train,reserve)
    after=git('rev-parse','HEAD:leobot')
    children=resource.getrusage(resource.RUSAGE_CHILDREN)
    rss=max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children.ru_maxrss)
    budget=edu_cpu<=240 and rss<=768*1024 and result['p95_ms'] is not None and result['p95_ms']<=100
    gate=(result['tag_accuracy']>=0.92 and result['uas']>=0.75 and result['uas']-base_uas>=0.01 and
          result['las']>=0.70 and result['f1']['nsubj']>=0.60 and result['f1']['obj']>=0.60 and
          result['label_given_head']>=0.85 and result['las']-ablation['las']>=0.02 and
          shuffled['las']<=0.40 and shuffled_heads['uas']<=0.35 and fresh_none and
          restored_outputs==outputs and budget and before==after and clean)
    out={'kind':'G32b_backoff_pruned','preregistration':PREREG,'development':dev,'engine_tree':before,
         'engine_unchanged':before==after,'engine_committed':clean,'seed':seed,
         'hashseed':os.environ.get('PYTHONHASHSEED'),'reserve_sentences':len(reserve),
         'reserve_words':sum(len(s[0]) for s in reserve),'treatment':result,
         'baseline_freeze_G31_uas':base_uas,'baseline_engine_tree':base_tree,
         'ablation_no_lexical_marker':ablation,'shuffled_labels':shuffled,'shuffled_heads':shuffled_heads,
         'fresh_unparsed':fresh_none,'restart_identical':restored_outputs==outputs,
         'education_cpu_s':round(edu_cpu,2),'cpu_total_s':round(time.process_time()-cpu0,2),
         'cpu_children_s':round(children.ru_utime+children.ru_stime,2),
         'wall_total_s':round(time.perf_counter()-wall0,2),'max_rss_kib':rss,'budget_ok':budget,
         'gate_pass':gate}
    name='g32b_backoff_pruned_dev' if dev else f'g32b_backoff_pruned_{seed}'
    (ROOT/'results_v3'/f'{name}_hashseed{out["hashseed"]}.json').write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()

"""G-35 evaluator: learned splitting of contractions and attached pronouns on raw text.

See prereg/G-35-separacion-aprendida-de-palabras.md.
Run from the repository root: python3 -m experiments.g35_learned_splitting [--dev]
"""
from __future__ import annotations

import copy
import json
import os
import random
import re
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.g29_syntax_counts import CACHE, split as split29
from experiments.g31_dependency_functions import split as split31

ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-35-separacion-aprendida-de-palabras.md'
WORD=re.compile(r'\w+|[^\w\s]')
PREVIOUS_TREES=('0af619ee','3b13f49b','7d68100c','5ef2dd5f','9e53c219','6b229755')


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def read(name):
    split29(name)   # download and SHA check
    sentences=[]; cur=None
    for line in (CACHE/f'es_ancora-ud-{name}.conllu').read_text(encoding='utf8').split('\n'):
        if line.startswith('# text = '):
            cur={'text':line[9:],'words':[],'tags':[],'heads':[],'labels':[],'surfaces':[]}
            continue
        if not line.strip():
            if cur and cur['words']:
                sentences.append(cur)
            cur=None; continue
        if line.startswith('#') or cur is None:
            continue
        cols=line.split('\t')
        if '.' in cols[0]:
            continue
        if '-' in cols[0]:
            a,b=map(int,cols[0].split('-'))
            cur['surfaces'].append((cols[1],list(range(a-1,b)))); continue
        index=int(cols[0])-1
        if not cur['surfaces'] or index not in cur['surfaces'][-1][1]:
            cur['surfaces'].append((cols[1],[index]))
        cur['words'].append(cols[1]); cur['tags'].append(cols[3]); cur['heads'].append(int(cols[6]))
        cur['labels'].append(cols[7].split(':')[0])
    return sentences


def gold_positions(sentence):
    """Map each gold word to (surface span, sub-index); None if not found in the text."""
    text=sentence['text']; cursor=0; where={}
    for surface,indices in sentence['surfaces']:
        at=text.find(surface,cursor)
        if at<0:
            continue
        span=(at,at+len(surface)); cursor=at+len(surface)
        for sub,index in enumerate(indices):
            where[index]=(span,sub,len(indices))
    return where


def predicted(bot,text,mode):
    words=[]; keys=[]
    for match in WORD.finditer(text):
        token=match.group(0); span=(match.start(),match.end())
        parts=[token] if mode=='regex' else bot.split_words(token)
        for sub,word in enumerate(parts):
            words.append(word); keys.append((span,sub,len(parts)))
    return words,keys


def evaluate(bot,sentences,mode='learned'):
    matched=pred_total=gold_total=uas=las=0; latency=[]; outputs=[]
    for sentence in sentences:
        started=time.perf_counter(); words,keys=predicted(bot,sentence['text'],mode)
        split_ms=(time.perf_counter()-started)*1000
        parsed=bot.parse_words(words) if words and len(words)<=60 else None
        latency.append(split_ms)
        gold=gold_positions(sentence); gold_by_key={v:k for k,v in gold.items()}
        to_gold={i:gold_by_key.get(k) for i,k in enumerate(keys)}
        to_gold={i:g for i,g in to_gold.items() if g is not None and
                 words[i].lower()==sentence['words'][g].lower()}
        matched+=len(to_gold); pred_total+=len(words); gold_total+=len(sentence['words'])
        outputs.append(parsed['heads'] if parsed else None)
        if not parsed or 'labels' not in parsed:
            continue
        for i,g in to_gold.items():
            ph=parsed['heads'][i]; gh=sentence['heads'][g]
            ok=(ph==0 and gh==0) or (ph>0 and to_gold.get(ph-1)==gh-1)
            uas+=ok; las+=ok and parsed['labels'][i]==sentence['labels'][g]
    ordered=sorted(latency); p95=ordered[max(0,-(-95*len(ordered)//100)-1)]
    precision=matched/max(1,pred_total); recall=matched/max(1,gold_total)
    return {'word_f1':round(2*precision*recall/max(1e-9,precision+recall),4),'uas_raw':round(uas/gold_total,4),
            'las_raw':round(las/gold_total,4),'split_p95_ms':round(p95,4)},outputs


def main():
    dev='--dev' in sys.argv[1:]
    cpu0=time.process_time(); wall0=time.perf_counter()
    before=git('rev-parse','HEAD:leobot')
    clean=not git('status','--porcelain','--','leobot','experiments/g35_learned_splitting.py')
    train=read('train')
    if dev:
        seed=None; reserve=random.Random(3535).sample([s for s in read('dev') if len(s['words'])<=60],300)
    else:
        seed=int(before[:8],16)
        used=set()
        pool29=[s for s in split29('test') if len(s[0])<=60]; pool31=[s for s in split31('test') if len(s[0])<=60]
        for tree in PREVIOUS_TREES[:2]:
            used.update(' '.join(s[0]) for s in random.Random(int(tree,16)).sample(pool29,300))
        for tree in PREVIOUS_TREES[2:]:
            used.update(' '.join(s[0]) for s in random.Random(int(tree,16)).sample(pool31,300))
        pool=[s for s in read('test') if len(s['words'])<=60 and ' '.join(s['words']) not in used]
        reserve=random.Random(seed).sample(pool,300)
    bot=Bot(); started=time.process_time()
    for s in train:
        bot.observe_parsed_sentence(s['words'],s['tags'],s['heads'],s['labels'])
        for surface,indices in s['surfaces']:
            if len(indices)>1:
                bot.observe_multiword(surface,[s['words'][i] for i in indices])
    bot.consolidate_syntax(); edu_cpu=time.process_time()-started
    learned,outputs=evaluate(bot,reserve)
    regex,_=evaluate(bot,reserve,'regex')
    gold_words=0; total=0
    for s in reserve:
        p=bot.parse_words(s['words']); total+=len(s['words'])
        gold_words+=sum(a==b for a,b in zip(p['heads'],s['heads']))
    gold_uas=round(gold_words/total,4)
    rules=bot.syntax_model['split_rules']
    bot.syntax_model['split_rules']={}; table_only,_=evaluate(bot,reserve)
    endings=sorted(rules); targets=[rules[e] for e in endings]; random.Random(35).shuffle(targets)
    bot.syntax_model['split_rules']=dict(zip(endings,targets)); shuffled,_=evaluate(bot,reserve)
    bot.syntax_model['split_rules']=rules
    fresh_none=Bot().parse_sentence(reserve[0]['text']) is None
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'; bot.save(path); restored=Bot.load(path)
    _,restored_outputs=evaluate(restored,reserve)
    after=git('rev-parse','HEAD:leobot')
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget=edu_cpu<=240 and rss<=768*1024 and learned['split_p95_ms']<=1
    gate=(learned['word_f1']>=0.98 and learned['uas_raw']-regex['uas_raw']>=0.02 and
          learned['uas_raw']>=table_only['uas_raw'] and gold_uas-learned['uas_raw']<=0.03 and
          shuffled['uas_raw']<=learned['uas_raw'] and fresh_none and restored_outputs==outputs and
          budget and before==after and clean)
    out={'kind':'G35_learned_splitting','preregistration':PREREG,'development':dev,'engine_tree':before,
         'engine_unchanged':before==after,'engine_committed':clean,'seed':seed,
         'hashseed':os.environ.get('PYTHONHASHSEED'),'reserve_sentences':len(reserve),
         'reserve_with_multiword':sum(any(len(i)>1 for _,i in s['surfaces']) for s in reserve),
         'rules':len(rules),'table':len(bot.syntax_model['split_table']),
         'learned':learned,'regex':regex,'table_only':table_only,'shuffled_rules':shuffled,
         'uas_with_corpus_words':gold_uas,'fresh_unparsed':fresh_none,'restart_identical':restored_outputs==outputs,
         'education_cpu_s':round(edu_cpu,2),'cpu_total_s':round(time.process_time()-cpu0,2),
         'wall_total_s':round(time.perf_counter()-wall0,2),'max_rss_kib':rss,'budget_ok':budget,'gate_pass':gate}
    name='g35_learned_splitting_dev' if dev else f'g35_learned_splitting_{seed}'
    (ROOT/'results_v3'/f'{name}_hashseed{out["hashseed"]}.json').write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()

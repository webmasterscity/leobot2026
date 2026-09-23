"""Read-only inventory of human counterfactual pairs from the authors' corpus."""
from __future__ import annotations

import csv
import io
import json
import resource
import time
import urllib.request
from collections import Counter
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git


ROOT=Path(__file__).resolve().parents[1]
COMMIT='6f232a1d2a11462a30ce08fb4825b734ab30828e'
BASE=f'https://raw.githubusercontent.com/acmi-lab/counterfactually-augmented-data/{COMMIT}/'
FILES=('NLI/original/train.tsv','NLI/revised_combined/train.tsv',
       'sentiment/combined/paired/train_paired.tsv')


def read(name):
    with urllib.request.urlopen(BASE+name,timeout=15) as response:
        data=response.read(5*1024*1024+1)
    if len(data)>5*1024*1024:raise RuntimeError('Fuente demasiado grande')
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig')),delimiter='\t'))
    return rows,{'bytes':len(data),'sha256':sha256(data).hexdigest(),
                 'fields':list(rows[0]) if rows else []}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    data={};sources={}
    for name in FILES:data[name],sources[name]=read(name)
    original=data[FILES[0]];revised=data[FILES[1]]
    sentiment=data[FILES[2]]
    if len(revised)!=4*len(original) or len(sentiment)%2:
        raise RuntimeError('Estructura de pares distinta de la esperada')
    nli=Counter();changes=Counter()
    for i,row in enumerate(original):
        group=revised[4*i:4*i+4]
        nli['groups']+=1
        labels=Counter(item['gold_label'] for item in group)
        nli['two_of_each_other_label']+=(
            len(labels)==2 and all(value==2 for value in labels.values())
            and row['gold_label'] not in labels)
        for edited in group:
            shared=sum(row[key]==edited[key] for key in ('sentence1','sentence2'))
            nli['revisions']+=1
            nli['exactly_one_sentence_unchanged']+=shared==1
            nli['label_changed']+=row['gold_label']!=edited['gold_label']
            changes[(row['gold_label'],edited['gold_label'])]+=1
    pairs=Counter()
    for i in range(0,len(sentiment),2):
        left,right=sentiment[i:i+2]
        pairs['pairs']+=1
        pairs['label_changed']+=left['Sentiment']!=right['Sentiment']
        pairs['same_batch_id']+=left['batch_id']==right['batch_id']
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'kind':'source_feasibility_only','source_repository':
            'https://github.com/acmi-lab/counterfactually-augmented-data',
            'source_commit':COMMIT,'source_license':'Apache-2.0',
            'sources':sources,'engine_tree':tree,'engine_unchanged':unchanged,
            'nli_train':dict(nli),'nli_label_transitions':[
                {'before':a,'after':b,'count':n} for (a,b),n in sorted(changes.items())],
            'sentiment_train':dict(pairs),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f14_counterfactual_inventory.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key!='sources'},ensure_ascii=False))


if __name__=='__main__':main()

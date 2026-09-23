"""F-16 grouped train controls on three human update families."""
from __future__ import annotations

import json
import math
import re
import resource
import time
import urllib.request
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f7_typed_sequences_dev import git
from experiments.f16_defeasible_inventory import BASE
from leobot.language import normalize


ROOT=Path(__file__).resolve().parents[1]
FAMILIES=('defeasible-snli','defeasible-atomic','defeasible-social')
LABELS=('strengthener','weakener')


def identifier(row,family):
    field={'defeasible-snli':'SNLIPairId',
           'defeasible-atomic':'AtomicEventId',
           'defeasible-social':'SocialChemSituationUID'}[family]
    value=row.get(field)
    if value is None or str(value)=='':raise RuntimeError('Grupo ausente')
    return str(value)


def load(family,tree,expected_hash):
    name=family+'/train.jsonl';url=BASE+name
    checksum=sha256();groups=set();rows=0
    with urllib.request.urlopen(url,timeout=30) as response:
        for line in response:
            checksum.update(line);row=json.loads(line);rows+=1
            if not row.get('UpdateTypeImpossible') and row.get('Update') and (
                    row.get('UpdateType') in LABELS):
                groups.add(identifier(row,family))
    if checksum.hexdigest()!=expected_hash:
        raise RuntimeError('Fuente defeasible distinta del inventario')
    ordered=sorted(groups,key=lambda key:(sha256((tree+':F-16:'+family+':'+key)
                       .encode()).hexdigest(),key))
    train=set(ordered[:1000]);validation=set(ordered[1000:1200])
    development=set(ordered[1200:1400])
    if min(len(train),len(validation),len(development))<200:
        raise RuntimeError('Grupos insuficientes')
    selected=train|validation|development
    output=defaultdict(list)
    with urllib.request.urlopen(url,timeout=30) as response:
        for line in response:
            row=json.loads(line)
            if row.get('UpdateTypeImpossible') or not row.get('Update') or (
                    row.get('UpdateType') not in LABELS):continue
            key=identifier(row,family)
            if key in selected:
                output[key].append({'GroupId':key,
                     'Premise':row.get('Premise') or '',
                     'Hypothesis':row.get('Hypothesis') or '',
                     'Update':row['Update'],'UpdateType':row['UpdateType']})
    return ([row for key in ordered[:1000] for row in output[key]],
            [row for key in ordered[1000:1200] for row in output[key]],
            [row for key in ordered[1200:1400] for row in output[key]],
            {'groups_available':len(groups),'groups_train':len(train),
             'groups_validation':len(validation),
             'groups_development':len(development),'source_rows':rows,
             'train_rows':sum(len(output[key]) for key in train),
             'validation_rows':sum(len(output[key]) for key in validation),
             'development_rows':sum(len(output[key]) for key in development)})


def words(text):
    return set(re.findall(r'[^\W_]+',normalize(text)))


def metrics(rows,predictions):
    totals=Counter();correct=Counter()
    for row,prediction in zip(rows,predictions):
        label=row['UpdateType'];totals[label]+=1
        correct[label]+=prediction==label
    size=sum(totals.values());hits=sum(correct.values())
    return {'total':size,'correct':hits,'accuracy':round(hits/size,6),
            'macro_accuracy':round(sum(correct[label]/max(1,totals[label])
                                    for label in LABELS)/len(LABELS),6),
            'by_label':{label:{'correct':correct[label],
                               'total':totals[label]} for label in LABELS}}


def controls(train,development):
    totals=Counter(row['UpdateType'] for row in train)
    winner=min(LABELS,key=lambda label:(-totals[label],label))
    majority=metrics(development,(winner for _ in development))
    counts=defaultdict(Counter);docs=Counter();vocab=set()
    for row in train:
        label=row['UpdateType'];tokens=words(row['Update'])
        docs[label]+=1;counts[label].update(tokens);vocab.update(tokens)
    n=sum(docs.values());vocabulary=len(vocab)
    def predict(row):
        tokens=[token for token in words(row['Update']) if token in vocab]
        scored=[]
        for label in LABELS:
            value=math.log((docs[label]+1)/(n+len(LABELS)))
            value+=sum(math.log((counts[label][token]+1)/(docs[label]+2))
                       for token in tokens)
            scored.append((value,label))
        return max(scored)[1]
    lexical=metrics(development,(predict(row) for row in development))
    return majority,lexical,{'documents':n,'vocabulary':vocabulary}


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    inventory=json.loads((ROOT/'results_v3'/'f16_defeasible_inventory.json').read_text())
    results={}
    for family in FAMILIES:
        tick=time.process_time()
        train,validation,development,partition=load(
            family,tree,inventory['files'][family+'/train.jsonl']['sha256'])
        acquisition_cpu=time.process_time()-tick
        tick=time.process_time()
        majority,lexical,profile=controls(train,development)
        control_cpu=time.process_time()-tick
        results[family]={'partition':partition,'majority':majority,
                         'lexical_update':lexical,'lexical_profile':profile,
                         'loading_cpu_s':round(acquisition_cpu,6),
                         'control_cpu_s':round(control_cpu,6)}
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'preregistration':'prereg/F-16-transferencia-igualdad-actualizaciones.md',
            'kind':'development_controls_only','engine_tree':tree,
            'engine_unchanged':unchanged,'families':results,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f16_defeasible_baselines.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

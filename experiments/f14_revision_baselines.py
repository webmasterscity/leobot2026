"""F-14 development controls before edit learner: transition and unpaired text."""
from __future__ import annotations

import json
import math
import re
import resource
import time
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path

from experiments.f14_counterfactual_inventory import read,FILES
from experiments.f7_typed_sequences_dev import git
from leobot.language import normalize


ROOT=Path(__file__).resolve().parents[1]
LABELS=('contradiction','entailment','neutral')


def groups(tree):
    inventory=json.loads((ROOT/'results_v3'/'f14_counterfactual_inventory.json').read_text())
    original,meta_o=read(FILES[0]);revised,meta_r=read(FILES[1])
    if (meta_o['sha256']!=inventory['sources'][FILES[0]]['sha256'] or
            meta_r['sha256']!=inventory['sources'][FILES[1]]['sha256'] or
            len(revised)!=4*len(original)):
        raise RuntimeError('Fuente NLI diferente a la fijada')
    ordered=sorted(range(len(original)),key=lambda i:(sha256(
        (tree+':F-14:nli:'+str(i)).encode()).hexdigest(),i))
    result=[]
    for number in ordered:
        states=[original[number],*revised[4*number:4*number+4]]
        if any(set(row)!={'sentence1','sentence2','gold_label'} or
               row['gold_label'] not in LABELS for row in states):
            raise RuntimeError('Esquema NLI no reconocido')
        result.append((number,states))
    return result[:1000],result[1000:1200],result[1200:1400],len(result)-1400


def pairs(groups_):
    for identifier,states in groups_:
        for i,before in enumerate(states):
            for j,after in enumerate(states):
                if i==j:continue
                changed=tuple(key for key in ('sentence1','sentence2')
                              if before[key]!=after[key])
                yield (identifier,i,j,before,after,changed)


def _winner(counts):
    return min(LABELS,key=lambda label:(-counts[label],label))


def score(predictions):
    totals=Counter();correct=Counter();attempts=0
    by_side=defaultdict(lambda:[0,0]);same=[0,0]
    for before,after,changed,prediction in predictions:
        gold=after['gold_label'];totals[gold]+=1
        side='+'.join(changed) or 'none'
        by_side[side][1]+=1
        if before['gold_label']==gold:same[1]+=1
        if prediction is None:continue
        attempts+=1;ok=prediction==gold;correct[gold]+=ok
        by_side[side][0]+=ok
        if before['gold_label']==gold:same[0]+=ok
    return {'total':sum(totals.values()),'attempts':attempts,
            'correct':sum(correct.values()),
            'accuracy':round(sum(correct.values())/max(1,sum(totals.values())),6),
            'precision':round(sum(correct.values())/attempts,6) if attempts else None,
            'coverage':round(attempts/max(1,sum(totals.values())),6),
            'macro_accuracy':round(sum(correct[label]/max(1,totals[label])
                                    for label in LABELS)/len(LABELS),6),
            'same_label':{'correct':same[0],'total':same[1]},
            'by_side':{key:{'correct':x,'total':n}
                       for key,(x,n) in sorted(by_side.items())}}


def prior(train,test):
    counts=defaultdict(Counter)
    for _,_,_,before,after,changed in pairs(train):
        counts[(before['gold_label'],changed)][after['gold_label']]+=1
    return score((before,after,changed,
                  _winner(counts[(before['gold_label'],changed)]))
                 for _,_,_,before,after,changed in pairs(test))


def _words(row):
    return set(re.findall(r'[^\W_]+',normalize(
        row['sentence1']+' '+row['sentence2'])))


def unpaired(train,test):
    docs=Counter();word_counts=defaultdict(Counter);vocabulary=set()
    for _,states in train:
        for row in states:
            label=row['gold_label'];docs[label]+=1
            terms=_words(row);word_counts[label].update(terms)
            vocabulary.update(terms)
    total=sum(docs.values());vocab=max(1,len(vocabulary))
    def predict(row):
        terms=[word for word in _words(row) if word in vocabulary]
        ranked=[]
        for label in LABELS:
            value=math.log((docs[label]+1)/(total+len(LABELS)))
            value+=sum(math.log((word_counts[label][word]+1)/(docs[label]+2))
                       for word in terms)
            ranked.append((value,label))
        return max(ranked)[1]
    return score((before,after,changed,predict(after))
                 for _,_,_,before,after,changed in pairs(test)),{
                     'documents':total,'vocabulary':vocab}


def main():
    wall=time.monotonic();cpu=time.process_time()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    train,validation,development,untouched=groups(tree)
    tick=time.process_time();prior_val=prior(train,validation)
    prior_cpu=time.process_time()-tick
    tick=time.process_time();unpaired_val,profile=unpaired(train,validation)
    unpaired_cpu=time.process_time()-tick
    output={'preregistration':'prereg/F-14-revision-contrafactual-tipada.md',
            'kind':'development_controls_only','engine_tree':tree,
            'groups_train':len(train),'groups_validation':len(validation),
            'groups_development':len(development),'train_groups_untouched':untouched,
            'prior_validation':prior_val,'unpaired_validation':unpaired_val,
            'unpaired_profile':profile,'prior_cpu_s':round(prior_cpu,6),
            'unpaired_cpu_s':round(unpaired_cpu,6),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f14_revision_baselines.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()

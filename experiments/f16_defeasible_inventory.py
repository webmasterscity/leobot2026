"""Read-only source audit of human defeasible inference updates."""
from __future__ import annotations

import hashlib
import json
import resource
import time
import urllib.request
from collections import Counter,defaultdict
from pathlib import Path

from experiments.f7_typed_sequences_dev import git


ROOT=Path(__file__).resolve().parents[1]
COMMIT='c675ffc1b0eec5fa56287f08490da8ed43c1ecc5'
BASE=f'https://raw.githubusercontent.com/rudinger/defeasible-nli/{COMMIT}/data/defeasible-nli/'


def main():
    cpu=time.process_time();wall=time.monotonic()
    tree=git('rev-parse','estable-E-1:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('Motor estable alterado')
    files={};parts={}
    for family in ('defeasible-snli','defeasible-atomic','defeasible-social'):
        name=family+'/train.jsonl';checksum=hashlib.sha256();count=Counter()
        groups=defaultdict(set);size=0
        with urllib.request.urlopen(BASE+name,timeout=30) as response:
            for line in response:
                size+=len(line)
                if size>50*1024*1024:raise RuntimeError('Fuente excede 50 MiB')
                checksum.update(line)
                row=json.loads(line)
                count['rows']+=1
                if row.get('UpdateTypeImpossible'):count['impossible']+=1
                elif row.get('Update') and row.get('UpdateType') in (
                        'strengthener','weakener'):
                    count[row['UpdateType']]+=1
                    key=(row.get('SNLIPairId') or row.get('AtomicEventId') or
                         row.get('SocialChemSituationUID') or
                         (row.get('Premise'),row.get('Hypothesis')))
                    groups[str(key)].add(row['UpdateType'])
        files[name]={'bytes':size,'sha256':checksum.hexdigest()}
        count['groups_with_updates']=len(groups)
        count['groups_with_both_labels']=sum(len(labels)==2 for labels in groups.values())
        parts[family]=dict(count)
    unchanged=(git('rev-parse','HEAD:leobot')==tree and
               not git('status','--porcelain','--','leobot'))
    output={'kind':'source_feasibility_only','engine_tree':tree,
            'engine_unchanged':unchanged,'source_repository':
            'https://github.com/rudinger/defeasible-nli',
            'source_commit':COMMIT,'source_license':'MIT',
            'files':files,'families':parts,
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f16_defeasible_inventory.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key!='files'},ensure_ascii=False))


if __name__=='__main__':main()

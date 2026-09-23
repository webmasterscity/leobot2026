"""F-6e: external human lexicalisations plus RDF observations, no manual frames."""
from __future__ import annotations

import json
import resource
from collections import Counter
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from leobot.language import normalize
from experiments.b1_aggregate_operator import ROOT
from experiments.d1_cross_modal_chain import remove_transfer
from experiments.f6b_role_geometry_freeze import FAMILIES, train_action, evaluate_action


TAG='freeze-F-6d'
COMMIT='587fa698bec705efbefe72a235a6019c2b9b8b6c'
CATEGORIES=('Airport','Artist','Astronaut','Athlete','Building','CelestialBody',
            'City','ComicsCharacter','Company','Food','MeanOfTransportation',
            'Monument','Politician','SportsTeam','University','WrittenWork')
BASE=f'https://gitlab.com/shimorina/webnlg-dataset/-/raw/{COMMIT}/release_v3.0/en'


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def frozen():
    tree=git('rev-parse',f'{TAG}:leobot')
    if git('rev-parse','HEAD:leobot')!=tree or git('status','--porcelain','--','leobot'):
        raise RuntimeError('El motor se alteró durante la sonda')
    return tree


def clock(fn):
    cpu=time.process_time();wall=time.monotonic()
    value=fn()
    return value,{'cpu_s':round(time.process_time()-cpu,6),
                  'wall_s':round(time.monotonic()-wall,6)}


def entity(value):
    return normalize(value.strip().strip('"').replace('_',' '))


def parse_file(data,category):
    root=ET.fromstring(data)
    entries=root.find('entries')
    if root.tag!='benchmark' or entries is None:
        raise RuntimeError('Formato externo inesperado')
    rows=[]
    for entry in entries.findall('entry'):
        triples=[node.text for node in entry.findall('modifiedtripleset/mtriple')]
        if len(triples)!=1 or not triples[0]:
            continue
        parts=[part.strip() for part in triples[0].split(' | ')]
        if len(parts)!=3:
            continue
        lexicalisations=[node.text.strip() for node in entry.findall('lex')
                         if node.attrib.get('comment')=='good' and node.text and node.text.strip()]
        if not lexicalisations:
            continue
        subject,predicate,object_value=parts
        row={'id':category+':'+entry.attrib.get('eid',''),
             'category':category,'text':lexicalisations[0],
             'subject':entity(subject),'predicate':predicate,
             'object':entity(object_value)}
        if row['subject'] and row['object'] and row['id']!=category+':':
            rows.append(row)
    return rows


def download_split(split):
    all_rows=[];sources={};size=0
    for category in CATEGORIES:
        path=f'{split}/1triples/{category}_allSolutions.xml'
        with urllib.request.urlopen(f'{BASE}/{path}',timeout=15) as response:
            data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:
            raise RuntimeError('Fuente externa excede el presupuesto')
        sources[path]={'bytes':len(data),'sha256':sha256(data).hexdigest()}
        size+=len(data)
        if size>32*1024*1024:
            raise RuntimeError('Total descargado excede el presupuesto')
        all_rows.extend(parse_file(data,category))
    return all_rows,sources,size


def select_train(rows,tree):
    by_category={category:[] for category in CATEGORIES}
    for row in rows:
        by_category[row['category']].append(row)
    chosen=[]
    for category in CATEGORIES:
        candidates=sorted(by_category[category],key=lambda row:(
            sha256((tree+':F-6e:train:'+category+':'+row['id']).encode()).hexdigest(),
            row['id']))
        chosen.extend(candidates[:32])
    return chosen


def save_reload(bot):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'
        bot.save(path)
        size=path.stat().st_size
        loaded=Bot.load(path)
    return loaded,size


def observe(bot,row):
    return bot.observe_world_transition(set(),{
        (row['predicate'],row['subject'],row['object'])})


def teach(rows,order,tree):
    bot=Bot();stages={}
    rows=list(rows)
    if order=='grouped':
        rows.sort(key=lambda row:(row['predicate'],row['category'],row['id']))
    else:
        rows.sort(key=lambda row:(sha256((tree+':F-6e:order:'+row['id']).encode()).hexdigest(),
                                  row['id']))
    reports,stages['documents']=clock(lambda:[
        bot.ingest_document_text(row['text'],source='webnlg:train:'+row['id'])
        for row in rows])
    raw_promotions=[value for value in bot.raw_relation_promotions.values()
                    if value.get('support',0)>=3]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'preworld.json';bot.save(path)
        baseline=Bot.load(path)
        shuffled=Bot.load(path)
        save_bytes=path.stat().st_size
    world_reports,stages['observations']=clock(lambda:[observe(bot,row) for row in rows])
    shuffled_rows=rows[1:]+rows[:1]
    shuffled_reports,stages['shuffled_observations']=clock(lambda:[
        observe(shuffled,{**row,'object':other['object']})
        for row,other in zip(rows,shuffled_rows)])
    world_only=Bot()
    world_only_reports,stages['world_only']=clock(lambda:[observe(world_only,row) for row in rows])
    role_sets=[row for row in bot.meta_representations.rows()
               if row.get('kind')=='role_set' and 'raw_world' in row.get('families',{})]
    shuffled_role_sets=[row for row in shuffled.meta_representations.rows()
                        if row.get('kind')=='role_set' and 'raw_world' in row.get('families',{})]
    # Ablation retains episodes and facts but removes their structural publication.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'withworld.json';bot.save(path)
        ablated=Bot.load(path)
    remove_transfer(ablated)
    return bot,{'order':order,'rows':len(rows),
                'raw_promotions':len(raw_promotions),
                'grounded_role_sets':len(role_sets),
                'grounded_role_set_schemas':[row['schema'] for row in role_sets],
                'world_statuses':dict(Counter(
                    row['status'] for row in world_reports)),
                'shuffled_role_sets':len(shuffled_role_sets),
                'shuffled_statuses':dict(Counter(
                    row['status'] for row in shuffled_reports)),
                'world_only_role_sets':len([r for r in world_only.meta_representations.rows()
                                            if r.get('kind')=='role_set']),
                'world_only_statuses':dict(Counter(
                    row['status'] for row in world_only_reports)),
                'raw_only_role_sets':len([r for r in baseline.meta_representations.rows()
                                          if r.get('kind')=='role_set']),
                'same_information_no_meta_role_sets':len(ablated.meta_representations.role_sets),
                'saved_bytes_before_world':save_bytes,
                'stages':stages}


def dev_probe(bot,train_rows,tree):
    rows,sources,size=download_split('dev')
    used={value for row in train_rows for value in (row['subject'],row['object'])}
    eligible=[row for row in rows if row['subject'] not in used and row['object'] not in used]
    chosen=sorted(eligible,key=lambda row:(sha256((tree+':F-6e:dev:'+row['id']).encode()).hexdigest(),
                                         row['id']))[:100]
    correct=0; timings=[]
    for row in chosen:
        before=set(bot.kb.facts)
        start=time.perf_counter()
        bot.ingest_document_text(row['text'],source='webnlg:dev:'+row['id'])
        timings.append((time.perf_counter()-start)*1000)
        added=set(bot.kb.facts)-before
        correct+=any(row['subject'] in bot.kb.facts[fid]['atom'].args and
                     row['object'] in bot.kb.facts[fid]['atom'].args
                     for fid in added)
    timings.sort()
    return {'available':len(rows),'entity_disjoint_available':len(eligible),
            'selected':len(chosen),'entity_pair_in_one_fact':correct,
            'p50_read_ms':timings[len(timings)//2] if timings else None,
            'p95_read_ms':timings[(95*len(timings)+99)//100-1] if timings else None,
            'sources':sources,'bytes':size}


def action_transfer(bot,tree):
    spec=FAMILIES[0]
    prefix='human'+tree[:8]
    seed=int(tree[:8],16)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'educated.json';bot.save(path)
        educated=Bot.load(path)
    fresh=Bot()
    taught=train_action(educated,spec,prefix,seed)
    untouched=train_action(fresh,spec,prefix,seed)
    return {'educated_statuses':[row['status'] for row in taught],
            'fresh_statuses':[row['status'] for row in untouched],
            'educated_score':evaluate_action(educated,spec,prefix,seed),
            'fresh_score':evaluate_action(fresh,spec,prefix,seed)}


def main():
    wall=time.monotonic();cpu=time.process_time();tree=frozen()
    all_rows,sources,size=download_split('train')
    train_rows=select_train(all_rows,tree)
    global_bot,global_report=teach(train_rows,'global',tree)
    grouped_bot,grouped_report=teach(train_rows,'grouped',tree)
    gate_train=(global_report['raw_promotions']>=3 and
                global_report['grounded_role_sets']>=1 and
                global_report['shuffled_role_sets']==0)
    dev=None;transfer=None
    if gate_train:
        dev=dev_probe(global_bot,train_rows,tree)
        transfer=action_transfer(global_bot,tree)
    unchanged=frozen()==tree
    output={'preregistration':'prereg/F-6e-texto-humano-y-hechos.md',
            'engine_tree':tree,'engine_unchanged':unchanged,
            'source_commit':COMMIT,'source_hashes':sources,'source_bytes':size,
            'source_rows':len(all_rows),'train_rows':len(train_rows),
            'global':global_report,'grouped':grouped_report,'train_gate':gate_train,
            'dev':dev,'action_transfer':transfer,
            'gate_passed':bool(unchanged and gate_train and dev and transfer and
                                dev['selected']==100 and dev['entity_pair_in_one_fact']>=10
                                and transfer['educated_score']['correct']>=116
                                and transfer['fresh_score']['correct']<116
                                and transfer['educated_score']['p95_ms']<=10),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-wall,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6e_human_text_grounding.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('source_hashes',)} ,ensure_ascii=False))


if __name__=='__main__':
    main()

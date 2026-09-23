"""F-6f pilot: construct semantic grammar from text and observed binary facts."""
from __future__ import annotations

import json
import random
import resource
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from leobot import Bot
from leobot.language import Language, normalize
from leobot.language_acquisition import LanguageAcquisitionMixin
from experiments.b1_aggregate_operator import ROOT
from experiments.f6e_human_text_grounding import download_split, frozen as engine_frozen


TAG='freeze-F-6f-piloto'


def train_partition(rows,tree):
    ranked=sorted(rows,key=lambda row:(
        sha256((tree+':F-6f:development:'+row['id']).encode()).hexdigest(),row['id']))
    held=[];reserved=set()
    for row in ranked:
        if row['subject'] in reserved or row['object'] in reserved:
            continue
        held.append(row);reserved.update((row['subject'],row['object']))
        if len(held)==128:
            break
    available=[row for row in rows if row['id'] not in {x['id'] for x in held}
               and row['subject'] not in reserved and row['object'] not in reserved]
    taught=sorted(available,key=lambda row:(
        sha256((tree+':F-6f:teaching:'+row['id']).encode()).hexdigest(),row['id']))[:2000]
    return taught,held,{'source_rows':len(rows),'heldout_available':len(held),
                        'teaching_available':len(available)}


class AnchoredConstructions:
    def __init__(self):
        self.episodes={}
        self.language=Language()
        self.promoted={}
        self.ambiguous=set()
        self.unaligned=0

    def observe(self,row):
        self.episodes[row['id']]={key:row[key] for key in
                                  ('id','text','subject','object','predicate')}

    def compile(self):
        self.language=Language(); self.promoted={}; self.ambiguous=set()
        groups=defaultdict(list); self.unaligned=0
        for row in self.episodes.values():
            frame={'act':'assert','pred':row['predicate'],
                   'args':[row['subject'],row['object']]}
            signature=LanguageAcquisitionMixin._grounding_signature(row['text'],frame)
            if signature is None:
                self.unaligned+=1;continue
            groups[signature[0]].append(row)
        for surface,rows in sorted(groups.items()):
            predicates={row['predicate'] for row in rows}
            if len(predicates)>1:
                self.ambiguous.add(surface);continue
            if (len({row['subject'] for row in rows})<3 or
                    len({row['object'] for row in rows})<3):
                continue
            representative=min(rows,key=lambda row:row['id'])
            frame={'act':'assert','pred':representative['predicate'],
                   'args':[representative['subject'],representative['object']]}
            try:
                changed=self.language.teach(representative['text'],frame,
                                            'observed_text_world',
                                            [row['id'] for row in sorted(rows,key=lambda r:r['id'])])
            except ValueError:
                continue
            if changed:
                self.promoted[surface]={'predicate':representative['predicate'],
                                        'support':len(rows),
                                        'evidence':[row['id'] for row in rows]}
        return {'episodes':len(self.episodes),'unaligned':self.unaligned,
                'candidate_surfaces':len(groups),'ambiguous_surfaces':len(self.ambiguous),
                'promoted_surfaces':len(self.promoted),
                'construction_count':len(self.language.constructions)}

    def as_dict(self):
        return {'episodes':[self.episodes[key] for key in sorted(self.episodes)]}

    @classmethod
    def from_dict(cls,data):
        model=cls()
        for row in data['episodes']:
            model.observe(row)
        model.compile()
        return model


def evaluate(model,rows):
    attempts=correct=wrong=0;times=[];status=Counter()
    for row in rows:
        tick=time.perf_counter()
        prediction=model.language.parse(row['text'])
        times.append((time.perf_counter()-tick)*1000)
        status[prediction['status']]+=1
        if prediction['status']!='parsed':
            continue
        attempts+=1; frame=prediction['frame']
        exact=(frame.get('pred')==row['predicate'] and
               frame.get('args')==[row['subject'],row['object']])
        correct+=exact; wrong+=not exact
    times.sort()
    return {'total':len(rows),'correct':correct,'attempts':attempts,
            'wrong_confident':wrong,
            'precision':round(correct/attempts,6) if attempts else None,
            'status':dict(status),
            'p50_ms':round(statistics.median(times),5) if times else None,
            'p95_ms':round(times[(95*len(times)+99)//100-1],5) if times else None}


def raw_control(taught,held):
    bot=Bot();start=time.process_time()
    for row in taught:
        bot.ingest_document_text(row['text'],source='f6f:raw:train:'+row['id'])
    acquisition=time.process_time()-start
    correct=0; start=time.process_time()
    for row in held:
        before=set(bot.kb.facts)
        bot.ingest_document_text(row['text'],source='f6f:raw:dev:'+row['id'])
        added=set(bot.kb.facts)-before
        correct+=any(bot.kb.facts[fid]['atom'].pred==row['predicate'] and
                     list(bot.kb.facts[fid]['atom'].args)==[row['subject'],row['object']]
                     for fid in added)
    return {'correct':correct,'total':len(held),
            'train_cpu_s':round(acquisition,6),
            'dev_cpu_s':round(time.process_time()-start,6)}


def renamed_probe(model):
    if not model.promoted:
        return False
    surface=next(iter(sorted(model.promoted)))
    row=model.episodes[model.promoted[surface]['evidence'][0]]
    text=normalize(row['text'])
    subject='sujetonuevo'+sha256(row['id'].encode()).hexdigest()[:6]
    object_value='objetodinovo'+sha256((row['id']+'object').encode()).hexdigest()[:6]
    text=text.replace(row['subject'],subject,1).replace(row['object'],object_value,1)
    parsed=model.language.parse(text)
    return (parsed['status']=='parsed' and parsed['frame'].get('pred')==row['predicate']
            and parsed['frame'].get('args')==[subject,object_value])


def correction_probe(model):
    if not model.promoted:
        return False
    surface=next(iter(sorted(model.promoted)))
    first=model.promoted[surface]['evidence'][0]
    old=model.episodes[first]
    different=next((row['predicate'] for row in model.episodes.values()
                    if row['predicate']!=old['predicate']),None)
    if different is None:
        return False
    original=model.as_dict()
    model.observe({**old,'predicate':different})
    model.compile()
    withdrawn=surface not in model.promoted and surface in model.ambiguous
    restored=AnchoredConstructions.from_dict(original)
    return withdrawn and surface in restored.promoted


def main():
    started=time.monotonic();cpu=time.process_time();tree=engine_frozen()
    rows,sources,source_bytes=download_split('train')
    taught,held,partition=train_partition(rows,tree)
    model=AnchoredConstructions()
    start=time.process_time()
    for row in taught:model.observe(row)
    extraction_cpu=time.process_time()-start
    start=time.process_time();learning=model.compile()
    compilation_cpu=time.process_time()-start
    treatment=evaluate(model,held)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'model.json'
        start=time.process_time()
        path.write_text(json.dumps(model.as_dict(),ensure_ascii=False),encoding='utf8')
        restarted=AnchoredConstructions.from_dict(json.loads(path.read_text(encoding='utf8')))
        restart_cpu=time.process_time()-start
        restarted_result=evaluate(restarted,held)
        restart_same=all(restarted_result[key]==treatment[key] for key in
                         ('correct','attempts','wrong_confident'))
        saved_bytes=path.stat().st_size
    memory_only=AnchoredConstructions()
    for row in taught:
        memory_only.observe(row)
    memory_result=evaluate(memory_only,held)
    shuffled=AnchoredConstructions()
    ordered=sorted(taught,key=lambda row:row['id'])
    for i,row in enumerate(ordered):
        shuffled.observe({**row,'predicate':ordered[(i+1)%len(ordered)]['predicate']})
    shuffled_learning=shuffled.compile();shuffled_result=evaluate(shuffled,held)
    raw=raw_control(taught,held)
    renamed=renamed_probe(model)
    corrected=correction_probe(model)
    unchanged=engine_frozen()==tree
    gate=(unchanged and len(held)==128 and treatment['correct']>=15
          and treatment['precision'] is not None and treatment['precision']>=0.8
          and treatment['correct']-raw['correct']>=10
          and shuffled_result['correct']<=2
          and restart_same and renamed and corrected
          and treatment['p95_ms']<=10
          and extraction_cpu+compilation_cpu<=40)
    output={'preregistration':'prereg/F-6f-construcciones-ancladas.md',
            'kind':'development_only','engine_tree':tree,'engine_unchanged':unchanged,
            'source_commit':'587fa698bec705efbefe72a235a6019c2b9b8b6c',
            'source_hashes':sources,'source_bytes':source_bytes,
            'partition':partition,'teaching_rows':len(taught),'heldout_rows':len(held),
            'learning':learning,'extraction_cpu_s':round(extraction_cpu,6),
            'compilation_cpu_s':round(compilation_cpu,6),
            'treatment':treatment,'raw_control':raw,'memory_only':memory_result,
            'shuffled_learning':shuffled_learning,'shuffled_control':shuffled_result,
            'restart_same':restart_same,'restart_cpu_s':round(restart_cpu,6),
            'saved_bytes':saved_bytes,'renamed_probe':renamed,
            'correction_probe':corrected,'gate_passed':bool(gate),
            'cpu_total_s':round(time.process_time()-cpu,6),
            'wall_total_s':round(time.monotonic()-started,6),
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    path=ROOT/'results_v3'/'f6f_anchored_constructions_dev.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:value for key,value in output.items()
                      if key not in ('source_hashes',)},ensure_ascii=False))


if __name__=='__main__':
    main()

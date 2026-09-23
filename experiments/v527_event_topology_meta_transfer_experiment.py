"""V5.27 frozen experiment: event topology meta-transfer across vocabularies."""
from __future__ import annotations
import hashlib,json,tempfile
from pathlib import Path
from statistics import median
from time import perf_counter
from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'results_v3'/'v527_event_topology_meta_transfer.json'

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def ground(bot,names):
    lines=[]
    for j,name in enumerate(names):
        lines += [f'a{j}x {name} b{j}x.',f'a{j}y {name} b{j}y.',f'a{j}z {name} b{j}z.']
    bot.ingest_document_text(' '.join(lines),source='v527_grammar')
    return {p['surface'].split()[1]:p['predicate'] for p in bot.raw_relation_promotions.values()}

def train_family(bot,names,prefix):
    p,q,r=names
    for i in range(3):
        bot.ingest_document_text(
            f'{prefix}{i} {p} {prefix}o{i}. {prefix}{i} {q} {prefix}l{i}. {prefix}{i} {r} {prefix}t{i}.',
            source=f'{prefix}_schema_{i}')

def use_family(bot,names,prefix):
    p,q,r=names
    return bot.ingest_document_text(
        f'{prefix}u {p} {prefix}obj. {prefix}u {q} {prefix}loc. {prefix}u {r} {prefix}time. Eso activa {prefix}alarm.',
        source=f'{prefix}_use')

def prepare(two_families=True):
    names=['frobla','tulka','norga','peka','rula','soma','zeta','kora','miva','activa','chaina','chainb','chainc']
    b=Bot(allow_extensional_grounding=False);preds=ground(b,names)
    train_family(b,('frobla','tulka','norga'),'f');use_family(b,('frobla','tulka','norga'),'f')
    if two_families:
        train_family(b,('peka','rula','soma'),'g');use_family(b,('peka','rula','soma'),'g')
    return b,preds

def main():
    before=code_hash();bot,preds=prepare(True)
    meta=[s for s in bot.document_event_meta_hypotheses.values() if s.get('promoted')]
    frozen_meta_count=len(meta)
    frozen_meta_support=meta[0].get('support') if len(meta)==1 else None
    frozen_source_count=len(meta[0].get('source_schemas',[])) if len(meta)==1 else None
    successes=0;times=[]
    one,_=prepare(False);control_unresolved=0;wrong=0
    with tempfile.TemporaryDirectory() as td:
        full_state=Path(td)/'full.json';control_state=Path(td)/'control.json'
        bot.save(full_state);one.save(control_state)
        for i in range(100):
            trial=Bot.load(full_state)
            t=perf_counter();r=trial.ingest_document_text(
                f'n{i} zeta o{i}. n{i} kora l{i}. n{i} miva t{i}. Eso activa a{i}.',source=f'v527_target_{i}')
            times.append((perf_counter()-t)*1000);row=r['sentence_results'][3]
            if row.get('status')=='document_coreference_resolved':
                ref=row['references'][0];event_id=ref['antecedent']
                successes += (ref.get('criteria')==['latent_document_event_meta_v527']
                              and trial.kb.contains(Atom(preds['activa'],(event_id,f'a{i}'))))
        for i in range(100):
            trial=Bot.load(control_state)
            r=trial.ingest_document_text(
                f'c{i} zeta o{i}. c{i} kora l{i}. c{i} miva t{i}. Eso activa ca{i}.',source=f'v527_control_{i}')
            control_unresolved += r['sentence_results'][3].get('status')=='document_coreference_unresolved'
        for i in range(50):
            trial=Bot.load(full_state)
            r=trial.ingest_document_text(
                f'x{i} chaina y{i}. y{i} chainb z{i}. z{i} chainc w{i}. Eso activa q{i}.',source=f'v527_wrong_{i}')
            wrong += r['sentence_results'][3].get('status')=='document_coreference_unresolved'
    after=code_hash()
    report={
      'version':'0.5.27','experiment':'predicate_disjoint_event_topology_meta_transfer',
      'code_hash_before':before,
      'learned':{
        'meta_schemas_promoted_at_freeze':frozen_meta_count,
        'meta_support_at_freeze':frozen_meta_support,
        'source_schema_count':frozen_source_count,
        'unseen_predicate_family_one_shot_resolved':successes,'heldout_cases':100,
        'median_document_ms':median(times),
      },
      'controls':{
        'one_source_family_unresolved':control_unresolved,'one_family_cases':100,
        'different_topology_unresolved':wrong,'different_topology_cases':50,
      },
      'code_hash_after':after,'code_unchanged_during_evaluation':before==after,
    }
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

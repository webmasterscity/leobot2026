#!/usr/bin/env python3
"""Frozen V5.15 experiment: contextual one-slot revision without taught correction phrases.

The experiment first learns two opaque relations and a Horn rule through normal
Spanish assertions/conditionals. It then corrects 100 newly stored facts using
elliptical discourse turns that were never taught as language examples. Success
requires retracting the old fact, changing the rule consequence, preserving an
unrelated fact, and leaving a no-context control untouched. A deliberately
ambiguous anchor must abstain rather than guess.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
import json

from leobot import Bot
from leobot.core import Atom

ROOT=Path(__file__).resolve().parents[1]


def code_hash() -> str:
    h=sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def ground_relation(bot: Bot, rows: list[str]) -> str:
    report=None
    for row in rows:
        report=bot.respond(row)
    assert report and report.get('status')=='raw_relation_learned', report
    return report['predicate']


def prepare_reasoner(bot: Bot) -> tuple[str,str]:
    occurs=ground_relation(bot,[
        'proyecto alfa ocurre el lunes',
        'proyecto beta ocurre el martes',
        'proyecto gamma ocurre el miercoles',
    ])
    mark=ground_relation(bot,[
        'proyecto alfa marca lunes',
        'proyecto beta marca martes',
        'proyecto gamma marca miercoles',
    ])
    learned=None
    for row in [
        'si proyecto uno ocurre el lunes entonces proyecto uno marca lunes',
        'si proyecto dos ocurre el martes entonces proyecto dos marca martes',
        'si proyecto tres ocurre el miercoles entonces proyecto tres marca miercoles',
    ]:
        learned=bot.respond(row)
    assert learned and learned.get('status')=='conditional_rule_learned', learned
    return occurs,mark


def main() -> None:
    before=code_hash()
    treatment=Bot(allow_extensional_grounding=False)
    occurs,mark=prepare_reasoner(treatment)
    unrelated=treatment.kb.add(Atom('control_ajeno',('u','v')),'control')

    success=0; old_retracted=0; new_consequence=0; old_consequence_gone=0
    latencies=[]
    variants=('era','mejor','realmente')
    for i in range(100):
        subject=f'item {i}'
        old=f'valor viejo {i}'
        new=f'valor nuevo {i}'
        stored=treatment.respond(f'proyecto {subject} ocurre el {old}')
        assert stored.get('status')=='stored', stored
        assert treatment.answer_atom(Atom(mark,(subject,old)))['status']=='hypothesis'
        t0=perf_counter()
        report=treatment.respond(f'No, {variants[i % len(variants)]} el {new}.')
        latencies.append((perf_counter()-t0)*1000)
        if report.get('status')=='corrected_contextually':
            success += 1
        if not treatment.kb.contains(Atom(occurs,(subject,old))):
            old_retracted += 1
        if treatment.answer_atom(Atom(mark,(subject,new)))['status']=='hypothesis':
            new_consequence += 1
        if treatment.answer_atom(Atom(mark,(subject,old)))['status']=='unknown':
            old_consequence_gone += 1

    # Same learned language, but no active discourse referent: correction must abstain.
    control=Bot(allow_extensional_grounding=False)
    control_occurs,_=prepare_reasoner(control)
    control.last_fact=None
    facts_before=control.kb.stats()['facts']
    raw_neg_before=len(control.raw_negative_relation_observations)
    unresolved=0
    for i in range(100):
        report=control.respond(f'No, era el valor nuevo {i}.')
        unresolved += report.get('status')=='correction_unresolved'
    control_unchanged=(control.kb.stats()['facts']==facts_before and
                       len(control.raw_negative_relation_observations)==raw_neg_before)

    # Repeated lexical anchor creates two equally plausible repair slots.
    ambiguous=Bot(allow_extensional_grounding=False)
    relation4=ground_relation(ambiguous,[f'a{i} liga b{i} con c{i} con d{i}' for i in range(4)])
    ambiguous_count=0; ambiguous_unchanged=0
    for i in range(20):
        stored=ambiguous.respond(f'ax{i} liga bx{i} con cx{i} con dx{i}')
        fid=stored['id']; old_atom=ambiguous.kb.get_fact(fid)['atom']
        report=ambiguous.respond(f'No, con nuevo{i}.')
        ambiguous_count += report.get('status')=='correction_ambiguous'
        ambiguous_unchanged += ambiguous.kb.get_fact(fid) is not None and ambiguous.kb.get_fact(fid)['atom']==old_atom

    # Save/reload after the learned language and a fresh discourse fact, then repair it.
    with TemporaryDirectory() as td:
        path=Path(td)/'bot.json'
        treatment.respond('proyecto persistente ocurre el valor previo')
        treatment.save(path)
        loaded=Bot.load(path)
        persisted=loaded.respond('No, era el valor posterior.')
        persistence_ok=(persisted.get('status')=='corrected_contextually' and
                        loaded.kb.contains(Atom(occurs,('persistente','valor posterior'))))

    correction_examples=sum(
        ex.get('frame',{}).get('act')=='correct_last'
        for ex in treatment.language.examples
    )
    after=code_hash()
    report={
        'version':'5.15',
        'code_hash_unchanged': before==after,
        'corrections':f'{success}/100',
        'old_facts_retracted':f'{old_retracted}/100',
        'new_rule_consequences':f'{new_consequence}/100',
        'old_rule_consequences_removed':f'{old_consequence_gone}/100',
        'unrelated_fact_preserved': treatment.kb.get_fact(unrelated) is not None,
        'control_without_context_abstained':f'{unresolved}/100',
        'control_memory_unchanged':control_unchanged,
        'ambiguous_repairs_abstained':f'{ambiguous_count}/20',
        'ambiguous_facts_unchanged':f'{ambiguous_unchanged}/20',
        'explicit_correct_last_examples':correction_examples,
        'persistence_after_restart':persistence_ok,
        'median_correction_ms':round(median(latencies),4),
        'max_correction_ms':round(max(latencies),4),
        'predicates':{'occurs':occurs,'mark':mark,'control_occurs':control_occurs,'ambiguous':relation4},
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert before==after
    assert success==old_retracted==new_consequence==old_consequence_gone==100
    assert treatment.kb.get_fact(unrelated) is not None
    assert unresolved==100 and control_unchanged
    assert ambiguous_count==ambiguous_unchanged==20
    assert correction_examples==0
    assert persistence_ok


if __name__=='__main__':
    main()

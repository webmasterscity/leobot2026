#!/usr/bin/env python3
"""V3.8: grounded invention of an unnamed relational concept from natural examples.

The experiment freezes leobot/*.py, creates two latent concepts from ordinary
Spanish positive/negative assertions without target-predicate annotations, tests
held-out entities, then measures whether a learned concept reduces the evidence
needed to acquire a new wording.  Controls use the same factual world but either
remember exact episodes only or receive the new wording without prior concepts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter
import tempfile

from leobot import Bot, Atom

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results_v3'/'v38_concept_invention.json'


def code_hash() -> str:
    h=hashlib.sha256()
    for path in sorted((ROOT/'leobot').glob('*.py')):
        h.update(path.name.encode());h.update(b'\0');h.update(path.read_bytes());h.update(b'\0')
    return h.hexdigest()


def v38_bot() -> Bot:
    b=Bot();b.concepts.allow_predicate_invention=False
    return b

def add_fact(bot: Bot, pred: str, a: str, b: str, source='world') -> None:
    bot.kb.add(Atom(pred,(a,b)),source)


def build_world(bot: Bot, heldout: int=200, distractors: int=5000) -> dict:
    # Root training pairs for grandparent-like (parent;parent) concept.
    chains=[('ana','beto','carla'),('diego','elena','fabio'),
            ('gina','hugo','ines'),('juan','kira','luis')]
    for a,m,b in chains:
        add_fact(bot,'parent',a,m);add_fact(bot,'parent',m,b)
    friends=[('gina','oscar'),('juan','paula'),('marta','nora'),('leo','olga')]
    for a,b in friends:add_fact(bot,'friend',a,b)

    positives=[];negatives=[]
    for i in range(heldout//2):
        a,m,b=f'pa{i}',f'pm{i}',f'pb{i}'
        add_fact(bot,'parent',a,m);add_fact(bot,'parent',m,b)
        positives.append((a,b))
        x,y=f'fa{i}',f'fb{i}'
        add_fact(bot,'friend',x,y)
        negatives.append((x,y))
    # Unrelated predicates do not touch labelled entities; a semantic inverted
    # index should keep them out of the concept learner's candidate set.
    for i in range(distractors):
        add_fact(bot,f'junk_{i}',f'jx_{i}',f'jy_{i}','distractor')
    return {'chains':chains,'friends':friends,'positives':positives,'negatives':negatives}


def train_roots(bot: Bot) -> dict:
    a=[];b=[]
    for text in ('Ana enlaza a Carla.','Diego enlaza a Fabio.',
                 'Gina no enlaza a Oscar.','Juan no enlaza a Paula.'):
        a.append(bot.observe_concept_statement(text))
    for text in ('Marta empareja con Nora.','Leo empareja con Olga.',
                 'Ana no empareja con Carla.','Diego no empareja con Fabio.'):
        b.append(bot.observe_concept_statement(text))
    return {'a':a,'b':b}


def evaluate_surface(bot: Bot, surface: str, positives, negatives) -> dict:
    tp=fp=unknown_pos=negative_not_asserted=0
    times=[]
    for a,b in positives:
        t=perf_counter();r=bot.query_concept(surface.format(a=a,b=b)+'?');times.append((perf_counter()-t)*1000)
        if r['status']=='entailed':tp+=1
        else:unknown_pos+=1
    for a,b in negatives:
        t=perf_counter();r=bot.query_concept(surface.format(a=a,b=b)+'?');times.append((perf_counter()-t)*1000)
        if r['status']=='entailed':fp+=1
        else:negative_not_asserted+=1
    return {'positives':len(positives),'negatives':len(negatives),'entailed_true':tp,
            'missed_true':unknown_pos,'false_positive':fp,'negative_not_asserted':negative_not_asserted,
            'median_query_ms':median(times) if times else 0.0}



def inverse_structure_reserve() -> dict:
    b=v38_bot()
    for pred,args in [
        ('teach',('mentor1','alumno1')),('teach',('mentor2','alumno2')),
        ('teach',('mentor3','alumno3')),('teach',('mentor4','alumno4')),
        ('other',('x1','y1')),('other',('x2','y2')),
    ]:
        b.kb.add(Atom(pred,args),'reserve')
    reports=[]
    for text in ('Alumno1 sigue a Mentor1.','Alumno2 sigue a Mentor2.',
                 'X1 no sigue a Y1.','X2 no sigue a Y2.'):
        reports.append(b.observe_concept_statement(text))
    held=[b.query_concept('Alumno3 sigue a Mentor3?')['status'],
          b.query_concept('Alumno4 sigue a Mentor4?')['status']]
    return {'status':reports[-1]['status'],
            'selected_program':reports[-1].get('learning',{}).get('selected'),
            'heldout_statuses':held}


def concept_hierarchy_transfer() -> dict:
    def add_alt_world(bot):
        for prefix in ('a','b','c','d','e','f'):
            ns=[f'{prefix}{i}' for i in range(5)]
            bot.kb.add(Atom('r',(ns[0],ns[1])),'hierarchy')
            bot.kb.add(Atom('s',(ns[1],ns[2])),'hierarchy')
            bot.kb.add(Atom('r',(ns[2],ns[3])),'hierarchy')
            bot.kb.add(Atom('s',(ns[3],ns[4])),'hierarchy')
        for x,y in (('n1','n2'),('n3','n4'),('n5','n6'),('n7','n8')):
            bot.kb.add(Atom('other',(x,y)),'hierarchy')

    full=v38_bot();full.concepts.max_relation_length=2;add_alt_world(full)
    for text in ('A0 enlaza a A2.','B0 enlaza a B2.',
                 'N1 no enlaza a N2.','N3 no enlaza a N4.'):
        base=full.observe_concept_statement(text)
    for text in ('C0 abarca a C4.','D0 abarca a D4.',
                 'N5 no abarca a N6.','N7 no abarca a N8.'):
        higher=full.observe_concept_statement(text)

    control=v38_bot();control.concepts.max_relation_length=2;add_alt_world(control)
    for text in ('C0 abarca a C4.','D0 abarca a D4.',
                 'N5 no abarca a N6.','N7 no abarca a N8.'):
        no_library=control.observe_concept_statement(text)
    return {
        'base_status':base['status'],
        'base_program':base.get('learning',{}).get('selected'),
        'higher_with_prior_status':higher['status'],
        'higher_with_prior_program':higher.get('learning',{}).get('selected'),
        'higher_with_prior_heldout':full.query_concept('E0 abarca a E4?')['status'],
        'higher_from_scratch_status':no_library['status'],
        'higher_from_scratch_program':no_library.get('learning',{}).get('selected'),
        'higher_from_scratch_heldout':control.query_concept('E0 abarca a E4?')['status'],
        'max_relation_length':2,
    }

def main() -> None:
    before_hash=code_hash()
    full=v38_bot();world=build_world(full)
    roots=train_roots(full)
    root_a=roots['a'][-1];root_b=roots['b'][-1]
    held=evaluate_surface(full,'{a} enlaza a {b}',world['positives'],world['negatives'])

    # Exact episodic cache cannot answer any held-out pair by construction.
    training_episodes={
        'ana enlaza a carla','diego enlaza a fabio','gina no enlaza a oscar','juan no enlaza a paula',
        'marta empareja con nora','leo empareja con olga','ana no empareja con carla','diego no empareja con fabio',
    }
    exact_cache_hits=sum(f'{a} enlaza a {b}' in training_episodes for a,b in world['positives'])

    # Prior concept -> new wording with only 1 positive + 1 negative example.
    alias_train=[
        full.observe_concept_statement('Gina conecta de lejos con Ines.'),
        full.observe_concept_statement('Marta no conecta de lejos con Nora.'),
    ]
    alias_eval=evaluate_surface(full,'{a} conecta de lejos con {b}',world['positives'],world['negatives'])

    # Same factual information and same two alias utterances, but no root concept
    # learning.  The ordinary concept learner needs 2+2 and therefore cannot
    # promote from these two examples alone.
    control=v38_bot();build_world(control)
    control_alias=[
        control.observe_concept_statement('Gina conecta de lejos con Ines.'),
        control.observe_concept_statement('Marta no conecta de lejos con Nora.'),
    ]
    control_eval=evaluate_surface(control,'{a} conecta de lejos con {b}',world['positives'],world['negatives'])

    # Persist learned root + alias and query an unseen pair after restart.
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'concept_state.json';full.save(path);loaded=Bot.load(path)
        persistence=loaded.query_concept(f'{world["positives"][7][0]} conecta de lejos con {world["positives"][7][1]}?')['status']

    # Counterevidence should withdraw only the alias, preserving the root concept.
    root_before=full.query_concept('Juan enlaza a Luis?')['status']
    counter=full.observe_concept_statement('Leo conecta de lejos con Olga.')
    alias_after=full.query_concept('Juan conecta de lejos con Luis?')['status']
    root_after=full.query_concept('Juan enlaza a Luis?')['status']

    # End-to-end conversation query on a separately learned copy, to ensure chat
    # routing does not get swallowed by the generic grounding version-space.
    chat=v38_bot();build_world(chat,distractors=0);train_roots(chat)
    chat_query=chat.respond('¿Gina enlaza a Ines?')

    after_hash=code_hash()
    result={
        'version':'0.3.8',
        'experiment':'grounded_invention_of_previously_unnamed_relational_concepts',
        'code_hash_before':before_hash,
        'root_concept_a':{
            'status':root_a['status'],'opaque_target':root_a['target'],
            'selected_program':root_a.get('learning',{}).get('selected'),
            'predicate_candidates_total':root_a.get('learning',{}).get('predicate_candidates_total'),
            'predicate_selected':root_a.get('learning',{}).get('predicate_selected'),
            'candidates':root_a.get('learning',{}).get('candidates'),
            'ms':root_a.get('learning',{}).get('ms'),
            'surface_predicate_preexisted':'enlaza' in full.kb.arity,
        },
        'root_concept_b':{
            'status':root_b['status'],'opaque_target':root_b['target'],
            'selected_program':root_b.get('learning',{}).get('selected'),
        },
        'heldout_transfer':held,
        'exact_episode_cache_hits':exact_cache_hits,
        'distractor_predicates':5000,
        'new_surface_with_prior_concept':{
            'training_statuses':[x['status'] for x in alias_train],
            'evaluation':alias_eval,
        },
        'new_surface_from_scratch_same_two_examples':{
            'training_statuses':[x['status'] for x in control_alias],
            'evaluation':control_eval,
        },
        'persistence_after_restart':persistence,
        'counterevidence':{
            'status':counter['status'],'alias_query_after':alias_after,
            'root_before':root_before,'root_after':root_after,
        },
        'conversation_route':{'status':chat_query['status'],'text':chat_query['text']},
        'structural_reserve_inverse':inverse_structure_reserve(),
        'concept_hierarchy':concept_hierarchy_transfer(),
        'code_hash_after':after_hash,
        'code_unchanged_during_evaluation':before_hash==after_hash,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

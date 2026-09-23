"""Fixed, honest AGI evidence board for a frozen Leobot tag.

Only the MLQA Spanish slice is executed here. Other rows explicitly retain
their evidence level or remain unmeasured; no score is inferred from a missing
task interface. See prereg/agi-board-1.md.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import resource
import subprocess
import time
import unicodedata
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path

from leobot import Bot


ROOT=Path(__file__).resolve().parents[1]
SEED=int('644c5552',16)
MLQA_URL='https://dl.fbaipublicfiles.com/MLQA/MLQA_V1.zip'
MLQA_ARCHIVE_SHA='246e8089933d13007fe80684d5c5c0713d6834cf8b3b4a0ec7c66f0a0d2baac8'
MLQA_MEMBER='MLQA_V1/dev/dev-context-es-question-es.json'


def canonical(text):
    decomposed=unicodedata.normalize('NFKD',str(text).casefold())
    plain=''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ' '.join(''.join(ch if ch.isalnum() else ' ' for ch in plain).split())


def mlqa_cases():
    with urllib.request.urlopen(MLQA_URL,timeout=20) as response:
        data=response.read()
    actual=sha256(data).hexdigest()
    if actual!=MLQA_ARCHIVE_SHA:
        raise RuntimeError(f'MLQA cambió: {actual}')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document=json.loads(archive.read(MLQA_MEMBER))
    cases=[]
    for article in document['data']:
        for paragraph in article['paragraphs']:
            context=paragraph['context']
            for question in paragraph['qas']:
                cases.append({'id':question['id'],'context':context,
                              'question':question['question'],
                              'answers':[answer['text'] for answer in question['answers']]})
    ids=sorted(cases,key=lambda row:row['id'])
    if len(ids)<20:
        raise RuntimeError('MLQA contiene menos de 20 preguntas.')
    return random.Random(SEED).sample(ids,20),len(ids)


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def evaluate_spanish(cases):
    statuses={};rows=[];exact=with_evidence=0
    started=time.process_time()
    for row in cases:
        bot=Bot()
        bot.ingest_document_text(row['context'],source=f'mlqa:{row["id"]}')
        answer=bot.respond(row['question'])
        status=answer.get('status','missing')
        matched=canonical(answer.get('text','')) in {
            canonical(value) for value in row['answers']}
        exact+=int(matched)
        with_evidence+=int(status in ('supported','refuted','bindings','entailed',
                                      'contradicted','contested'))
        statuses[status]=statuses.get(status,0)+1
        rows.append({'id':row['id'],'status':status,'exact_match':matched})
    return {'exact_match':exact,'with_evidence':with_evidence,'total':len(cases),
            'statuses':statuses,'cases':rows,
            'cpu_s':round(time.process_time()-started,5)}


def run(tag):
    tree=git('rev-parse',f'{tag}:leobot')
    if git('diff','--name-only',tag,'--','leobot'):
        raise RuntimeError('El motor difiere del tag.')
    cases,source_count=mlqa_cases()
    spanish=evaluate_spanish(cases)
    if git('diff','--name-only',tag,'--','leobot'):
        raise RuntimeError('El motor cambió durante el tablero.')
    latency=[]
    for seed in (0,1,2):
        path=ROOT/'results_v3'/f'latency_{tag}_hashseed{seed}.json'
        if path.exists():
            latency.append(json.loads(path.read_text(encoding='utf8')))
    a1=json.loads((ROOT/'results_v3'/'a1_meta_abstraction.json').read_text(encoding='utf8'))
    a1b=json.loads((ROOT/'results_v3'/'a1b_controls.json').read_text(encoding='utf8'))
    board={
        'tag':tag,'engine_tree':tree,'engine_unchanged':True,
        'board_preregistration':'prereg/agi-board-1.md',
        'language_spanish':{
            'battery':'MLQA dev-context-es-question-es, 20 fixed public cases',
            'source':'https://github.com/facebookresearch/MLQA',
            'archive_sha256':MLQA_ARCHIVE_SHA,'source_questions':source_count,
            'sample_seed':SEED,'result':spanish,'frontier_same_protocol':None,
            'evidence_level':'public development diagnostic, not independent final reserve'},
        'deductive_relational':{'battery':'A-1 internal structural reserve',
                                'results':[row['treatment']['correct'] for row in a1['orders']],
                                'out_of':[160]*3,'frontier_same_protocol':None,
                                'evidence_level':'internal, narrow numeric family'},
        'causal_reasoning':{'result':None,'reason':'no fixed independent causal battery'},
        'few_shot_abstraction':{'battery':'A-1 internal structural reserve',
                                 'treatment':[row['treatment']['correct'] for row in a1['orders']],
                                 'same_information_ablation':[row['ablation_same_information']['correct']
                                                              for row in a1['orders']],
                                 'frontier_same_protocol':None,
                                 'evidence_level':'internal, one repeated structure'},
        'new_domain_transfer':{'result':'no_transfer','educated_examples':3,
                               'fresh_examples':3,'evidence_level':'historical internal control'},
        'planning_and_tools':{'result':None,'reason':'no fixed public task with equal tools'},
        'useful_conversation':{'result':'8/13','evidence_level':'visible internal diagnostic'},
        'self_correction_uncertainty':{
            'dependent_withdrawal':[row['view_after_counterevidence_restart'] is None
                                    for row in a1b['orders']],
            'evidence_level':'internal meta-rule control'},
        'efficiency':{
            'facts':min((row['build']['facts'] for row in latency),default=None),
            'known_p95_ms_worst':max((row['summary']['known']['p95_ms'] for row in latency),
                                     default=None),
            'reasoning_p95_ms_worst':max((row['summary']['reasoning']['p95_ms']
                                        for row in latency),default=None),
            'peak_rss_kib_worst':max((row['peak_rss_kib'] for row in latency),default=None),
            'all_gates_pass':bool(latency) and all(all(row['limits'].values()) for row in latency),
            'evidence_level':'fixed local workload, single core'},
        'arc_agi_3':{
            'source':'https://arcprize.org/arc-agi/3',
            'result':None,
            'reason':'Leobot no tiene interfaz operacional de marcos y acciones para estos juegos',
            'frontier_same_protocol':None},
        'main_agi_obstacle':'adquisición de significado desde texto libre y entradas nuevas',
        'numeric_frontier_gap':None,
        'gap_reason':'no hay medición de Leobot y modelos frontier bajo las mismas baterías y condiciones',
        'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'pythonhashseed':os.environ.get('PYTHONHASHSEED'),
    }
    d1_paths=[ROOT/'results_v3'/f'd1_chain_order{order}.json'
              for order in (17,53,97)]
    if all(path.exists() for path in d1_paths):
        d1_rows=[json.loads(path.read_text(encoding='utf8')) for path in d1_paths]
        if all(row.get('engine_unchanged') and row.get('frozen_engine_tree')==tree
               for row in d1_rows):
            board['cross_modal_chain']={
                'battery':'D-1, cadena interna texto → acción → procedimiento',
                'preregistration':'prereg/D-1-cadena-entre-modalidades.md',
                'b_heldout_correct':[row['variants']['a_b']['b_score']['correct']
                                     for row in d1_rows],
                'c_heldout_correct':[row['variants']['a_b']['c_score']['correct']
                                     for row in d1_rows],
                'c_controls_unresolved':[all(row['variants'][name]['c_status']!=
                                             'procedure_learned' for name in
                                             ('a_only','b_only','fresh',
                                              'same_information_no_transfer'))
                                         for row in d1_rows],
                'c2_learner_candidates_saved':[
                    -row['c2_transfer']['candidates_delta'] for row in d1_rows],
                'frontier_same_protocol':None,
                'evidence_level':'reserva interna sintética; frases templadas y hechos de base estructurados',
            }
    path=ROOT/'results_v3'/f'agi_board_{tag}.json'
    path.write_text(json.dumps(board,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'tag':tag,'spanish':spanish['exact_match'],
                      'evidence':spanish['with_evidence'],'cases':spanish['total'],
                      'statuses':spanish['statuses'],'arc_agi_3':'no evaluado',
                      'frontier_gap':'no comparable'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--tag',default='estable-A-1')
    run(parser.parse_args().tag)

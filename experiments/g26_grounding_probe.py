"""Preregistered G-26: grounded meaning probes with a frozen nonneural engine."""
from __future__ import annotations

import json
import os
import random
import resource
import subprocess
import tempfile
import time
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


ROOT = Path(__file__).resolve().parents[1]
PREREG = 'prereg/G-26-consulta-de-significado-rival.md'


def motor_tree() -> str:
    return subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'],
                                   cwd=ROOT, text=True).strip()


def family(rng: random.Random, index: int, renamed: bool = False) -> dict:
    """Create an unseen vocabulary with identical structural evidence."""
    alphabet = 'abcdefghjkmnpqrstuvwxyz'
    def word():
        return ''.join(rng.choice(alphabet) for _ in range(9))
    prefix = 'x' if renamed else ''
    surface = prefix + word()
    pred = [prefix + 'rel_' + word(), prefix + 'rel_' + word()]
    entities = [(prefix + start + word(), prefix + end + word())
                for start, end in [('m','n'), ('p','q'), ('a','b'), ('z','y'), ('k','l')]]
    return {'surface': surface, 'pred': pred, 'entities': entities,
            'reverse': bool(index % 2), 'target': index % 2}


def utterance(spec: dict, pair: tuple[str, str]) -> str:
    a, b = pair
    return f'{b} {spec["surface"]} {a}' if spec['reverse'] else f'{a} {spec["surface"]} {b}'


def bot_for(spec: dict, *, negative=True, learner=True) -> Bot:
    kb=KnowledgeBase()
    for pair in spec['entities'][:3]:
        for pred in spec['pred']:
            kb.add(Atom(pred,pair),'entorno')
    contrast=spec['entities'][3]
    kb.add(Atom(spec['pred'][0],contrast),'entorno')
    if negative:
        kb.add(Atom('!'+spec['pred'][1],contrast),'entorno')
    return Bot(kb,grounded_language=learner,allow_extensional_grounding=True)


def educate(bot: Bot, spec: dict) -> list[str]:
    return [bot.respond(utterance(spec,pair))['status'] for pair in spec['entities'][:2]]


def run_one(spec: dict) -> dict:
    phases={}; t=time.process_time()
    bot=bot_for(spec)
    education=educate(bot,spec)
    phases['acquisition_cpu_s']=time.process_time()-t
    possible_before=[len(st['possible']) for st in bot.grounding_hypotheses.values()]
    held=utterance(spec,spec['entities'][4])
    before=bot.language.parse(held)['status']
    t=time.process_time(); proposal=bot.propose_grounding_probe()
    phases['proposal_cpu_s']=time.process_time()-t
    same=utterance(spec,spec['entities'][2]); contrast=utterance(spec,spec['entities'][3])
    selected=proposal.get('probe_text')
    answer=(True if selected==same else spec['target']==0 if selected==contrast else None)
    safe=selected==contrast and answer is not None
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'bot.json'
        t=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['restart_before_cpu_s']=time.process_time()-t
        if safe:
            t=time.process_time(); feedback=bot.observe_grounding_probe(proposal['probe_id'],answer)
            phases['feedback_cpu_s']=time.process_time()-t
            t=time.process_time(); bot.save(path); bot=Bot.load(path)
            phases['restart_after_cpu_s']=time.process_time()-t
            t=time.process_time(); parsed=bot.language.parse(held)
            phases['inference_cpu_s']=time.process_time()-t
            t=time.process_time(); contradicted=bot.observe_grounding_probe(proposal['probe_id'],not answer)
            phases['rollback_cpu_s']=time.process_time()-t
            after_rollback=bot.language.parse(held)['status']
        else:
            feedback={'status':'not_run'}; parsed={'status':'not_run'}
            contradicted={'status':'not_run'}; after_rollback='not_run'

    # A one-question passive choice receives the same facts, phrases, and
    # observation interface, but its selector always chooses the first offer.
    passive=bot_for(spec); educate(passive,spec)
    passive.meta_controller.select_epistemic_action=lambda hypotheses,actions: {
        'status':'epistemic_action','chosen_index':0,
        'chosen':{'info_gain_bits':0.0,'value_per_cost':0.0}}
    passive_probe=passive.propose_grounding_probe()
    passive_text=passive_probe.get('probe_text')
    passive_answer=(True if passive_text==same else spec['target']==0
                    if passive_text==contrast else None)
    passive_feedback=passive.observe_grounding_probe(passive_probe['probe_id'],passive_answer) if passive_answer is not None else {'status':'not_run'}
    fresh=bot_for(spec)
    memory=bot_for(spec,learner=False); memory_education=educate(memory,spec)
    incompatible=bot_for(spec,negative=False); educate(incompatible,spec)
    return {'education':education,'before':before,'possible_before':possible_before,
            'chosen_discriminating':safe,'offered':proposal.get('offered',0),
            'probe_status':proposal['status'],'feedback_status':feedback['status'],
            'heldout_correct':parsed.get('status')=='parsed' and
                parsed['frame']['pred']==spec['pred'][spec['target']] and
                parsed['frame']['args']==list(spec['entities'][4]),
            'rollback_status':contradicted['status'],'after_rollback':after_rollback,
            'passive_discriminating':passive_text==contrast,
            'passive_status':passive_feedback['status'],
            'fresh':fresh.propose_grounding_probe()['status'],
            'memory_education':memory_education,
            'memory_parse':memory.language.parse(held)['status'],
            'incompatible':incompatible.propose_grounding_probe()['status'],
            'answer':answer,'target':spec['target'], 'reverse':spec['reverse'],
            'phases':{key:round(value,6) for key,value in phases.items()}}


def main() -> None:
    start_cpu=time.process_time(); start_wall=time.perf_counter()
    tree_before=motor_tree(); seed=int(tree_before[:8],16)
    rng=random.Random(seed)
    rows=[]; rename_rows=[]
    for index in range(12):
        spec=family(rng,index)
        rows.append(run_one(spec))
        renamed=family(rng,index,renamed=True)
        # New words, predicates and entities; same role/order/answer geometry.
        rename_rows.append(run_one(renamed))
    tree_after=motor_tree()
    quality=sum(row['chosen_discriminating'] and row['heldout_correct']
                and row['feedback_status']=='grounding_promoted' for row in rows)
    rollback=sum(row['rollback_status']=='grounding_conflict' and
                 row['after_rollback']=='unrecognized' for row in rows)
    restarts=sum(row['heldout_correct'] for row in rows)
    passive=sum(row['passive_status']=='grounding_promoted' for row in rows)
    incompatible=sum(row['incompatible']=='no_epistemic_action' for row in rows)
    rename_ok=sum(a['chosen_discriminating']==b['chosen_discriminating'] and
                  a['heldout_correct']==b['heldout_correct'] and
                  a['feedback_status']==b['feedback_status']
                  for a,b in zip(rows,rename_rows))
    cpu=time.process_time()-start_cpu; wall=time.perf_counter()-start_wall
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget=cpu<=30 and wall<=45 and rss<=128*1024
    result={'kind':'G26_grounding_probe','preregistration':PREREG,
            'engine_tree':tree_before,'engine_unchanged':tree_before==tree_after,
            'seed':seed,'hashseed':os.environ.get('PYTHONHASHSEED'),
            'examples_per_family':2,'families':12,'rows':rows,'rename_rows':rename_rows,
            'quality_passes':quality,'rollback_passes':rollback,
            'restart_passes':restarts,'passive_promotions':passive,
            'incompatible_abstentions':incompatible,'rename_invariant':rename_ok,
            'cpu_total_s':round(cpu,6),'wall_total_s':round(wall,6),
            'max_rss_kib':rss,'budget_ok':budget,
            'gate_pass':(quality>=10 and rollback==12 and restarts==12 and passive<=6
                         and incompatible==12 and rename_ok==12 and budget
                         and tree_before==tree_after and all(r['before']=='unrecognized'
                         and r['possible_before']==[2] and
                         r['fresh']=='no_epistemic_action' and
                         r['memory_parse']=='unrecognized' for r in rows))}
    out=ROOT/'results_v3'/f'g26_grounding_probe_{seed}_hashseed{result["hashseed"]}.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:result[key] for key in ('engine_tree','seed','quality_passes',
          'rollback_passes','passive_promotions','incompatible_abstentions',
          'rename_invariant','cpu_total_s','max_rss_kib','budget_ok','gate_pass')},
          ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()

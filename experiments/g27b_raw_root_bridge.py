"""G-27b frozen-engine assay: keep the raw root and bridge it to the answered meaning.

Everything reaches the bot as natural text through ``Bot.respond``; the
evaluator reads state and uses ``answer_atom`` only to score.  The environment
answers the bot's own yes/no question from its world table after the proposal.

Three sentences of the new phrase precede the question, so the raw root that
G-1 induced must exist again when the answer arrives.  Controls: the engines
``estable-G-1`` and ``freeze-G-27`` archived into temporary directories and run
in child processes, fresh bot, memory only (``grounded_language=False``), no
explicit negation, a third surface with a single hypothesis, full renaming,
ablation of the bridge register, contradictory answer with rollback, and
save/load before feedback, after use and after rollback.

Run ``python -m experiments.g27b_raw_root_bridge --dev`` for the visible
development seed; without it the seed comes from the frozen engine tree.
"""
from __future__ import annotations

import json
import os
import random
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from leobot.bot import Bot
from leobot.core import Atom
from leobot.language import normalize

from experiments.g27_raw_root_probe import (abstention, answer_for, educate, family,
                                            relation, third, tree)


ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-27b-raiz-cruda-y-puente-revocable.md'
ARCHIVED=('estable-G-1','freeze-G-27')
DEV_SEED=2727
EVALUATORS=('experiments/g27b_raw_root_bridge.py','experiments/g27_raw_root_probe.py')


def frozen() -> bool:
    """The fingerprint describes what runs only if engine and evaluators are committed."""
    return not subprocess.check_output(['git','status','--porcelain','--','leobot',*EVALUATORS],
                                       cwd=ROOT,text=True).strip()


def canonical(pair) -> tuple[str, ...]:
    return tuple(normalize(value) for value in pair)


def spoken(spec: dict, pair) -> tuple[str, ...]:
    """Argument order of the third surface as written."""
    args=canonical(pair)
    return tuple(reversed(args)) if spec['reverse'] else args


def collect(bot: Bot, spec: dict) -> list[dict]:
    return [bot.respond(third(spec,pair)) for pair in spec['pairs'][:3]]


def touching(bot: Bot, pred: str | None) -> list[str]:
    return sorted(rid for rid,rule in bot.kb.rules.items()
                  if pred is not None and pred in (rule.head.pred,*(a.pred for a in rule.body)))


def restored_root(bot: Bot, spec: dict, roots: list, responses: list[dict]) -> tuple[bool, str | None]:
    statuses=[row.get('status') for row in responses]
    raw=responses[-1].get('predicate') if responses else None
    ok=(statuses[-1]=='raw_relation_learned' and raw is not None and raw not in roots and
        all(bot.kb.contains(Atom(raw,spoken(spec,pair))) for pair in spec['pairs'][:3]))
    return ok,raw


def route(spec: dict) -> dict:
    """Control sequence for whatever engine ``leobot`` resolves to."""
    import leobot
    bot=Bot(); education=educate(bot,spec); roots=education['roots']
    responses=collect(bot,spec)
    restored,raw=restored_root(bot,spec,roots,responses)
    held=third(spec,spec['pairs'][4])
    row=abstention(bot,spec,held)
    parsed=bot.language.parse(held)
    held_pred=(parsed.get('frame') or {}).get('pred')
    bot.respond(held)
    want=canonical(spec['pairs'][4])
    derived=[bot.answer_atom(Atom(str(root),want))['status'] if root else None for root in roots]
    return {'engine_path':str(Path(leobot.__file__).resolve().parent),
            'third':[r.get('status') for r in responses],'restored':restored,
            'probe':row['probe'],'feedback':row['feedback'],'held_parse':row['held_parse'],
            'rules_on_held':touching(bot,held_pred),'derived':derived}


def quiet(row: dict) -> bool:
    """No bridge and no deduction of either relation for the new pair."""
    return not row['rules_on_held'] and row['derived']==['unknown','unknown']


def archived_main() -> None:
    specs=json.loads(sys.stdin.read())
    print(json.dumps([route(spec) for spec in specs]))


def run_archived(tag: str, specs: list[dict]) -> tuple[list[dict], str]:
    with tempfile.TemporaryDirectory() as directory:
        archive=subprocess.run(['git','archive',tag,'leobot'],cwd=ROOT,check=True,
                               capture_output=True).stdout
        subprocess.run(['tar','-x','-C',directory],input=archive,check=True)
        code=('import sys; sys.path.insert(0,%r); sys.path.insert(1,%r); '
              'from experiments.g27b_raw_root_bridge import archived_main; archived_main()'
              % (directory,str(ROOT)))
        output=subprocess.run([sys.executable,'-c',code],cwd=directory,check=True,
                              input=json.dumps(specs),capture_output=True,text=True).stdout
        rows=json.loads(output)
        inside=all(Path(row['engine_path'])==Path(directory,'leobot').resolve() for row in rows)
    return rows,tree(tag) if inside else 'engine_path_mismatch'


def evaluate(spec: dict) -> dict:
    phases={}
    pairs=spec['pairs']; target=spec['target']
    held=third(spec,pairs[4]); contrast=normalize(third(spec,pairs[3]))
    want=canonical(pairs[4])

    start=time.process_time(); bot=Bot()
    education=educate(bot,spec)
    phases['roots']=time.process_time()-start
    roots=education['roots']
    induced_roots=(education['root_statuses']==['raw_relation_learned']*2 and
                   None not in roots and roots[0]!=roots[1])
    start=time.process_time(); responses=collect(bot,spec)
    phases['collection']=time.process_time()-start
    statuses=[row.get('status') for row in responses]
    restored,raw=restored_root(bot,spec,roots,responses)
    open_clusters=[state for state in bot.grounding_hypotheses.values()
                   if not state.get('conflict')]
    possible_before=[len(state.get('possible',())) for state in open_clusters]
    kept_rivals=(statuses[:2]==['grounding_pending']*2 and possible_before==[2] and
                 not any(state.get('promoted') for state in open_clusters))
    no_bridge_before=raw is not None and not touching(bot,raw)

    start=time.process_time(); proposal=bot.propose_grounding_probe()
    phases['selection']=time.process_time()-start
    probe_text=proposal.get('probe_text')
    chosen=probe_text==contrast
    pending=[state.get('pending_probe') for state in bot.grounding_hypotheses.values()
             if state.get('pending_probe')]
    # Nothing may answer the question before the environment does.
    invented=any(row.get('answer') is not None for row in pending)
    answer=answer_for(spec,probe_text)
    rel=Atom(str(roots[target]),want); other=Atom(str(roots[1-target]),want)
    wrong_order=Atom(str(roots[target]),tuple(reversed(want)))
    inverse=Atom(str(raw),spoken(spec,pairs[6]))
    status=lambda b,atom: b.answer_atom(atom)['status']
    phases['persistence']=0.0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'
        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['persistence']+=time.process_time()-start
        pending_survives=any((state.get('pending_probe') or {}).get('id')==proposal.get('probe_id')
                             for state in bot.grounding_hypotheses.values())
        start=time.process_time()
        feedback=(bot.observe_grounding_probe(proposal['probe_id'],answer)
                  if answer is not None else {'status':'no_environment_answer'})
        phases['feedback']=time.process_time()-start
        rule_ids=sorted(feedback.get('bridge_rule_ids',()))
        bridge=(feedback['status']=='grounding_promoted' and
                feedback.get('construction_count')==0 and len(rule_ids)==2 and
                touching(bot,raw)==rule_ids)

        start=time.process_time()
        parsed=bot.language.parse(held)
        no_collision=(parsed['status']=='parsed' and raw is not None and
                      (parsed.get('frame') or {}).get('pred')==raw)
        stored=bot.respond(held)['status']
        said=bot.respond(relation(spec,target,pairs[6]))['status']
        derived={'target':status(bot,rel),'other':status(bot,other),
                 'wrong_order':status(bot,wrong_order),'inverse':status(bot,inverse)}
        phases['use']=time.process_time()-start
        interpreted=(no_collision and stored=='stored' and said=='stored' and
                     derived=={'target':'hypothesis','other':'unknown',
                               'wrong_order':'unknown','inverse':'hypothesis'})
        raw_atoms=[Atom(str(raw),spoken(spec,pairs[index])) for index in (0,1,2,4)]
        education_atoms=[Atom(str(roots[r]),canonical(pairs[index]))
                         for r in (0,1) for index in (0,1,2)]
        education_atoms.append(Atom(str(roots[0]),canonical(pairs[3])))
        education_atoms.append(Atom('!'+str(roots[1]),canonical(pairs[3])))
        said_atom=Atom(str(roots[target]),canonical(pairs[6]))

        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['persistence']+=time.process_time()-start
        bridge_survives=(bool(rule_ids) and touching(bot,raw)==rule_ids and
                         status(bot,rel)=='hypothesis')
        # Same history and correction with only the bridge register ablated.
        control=Bot.load(path)
        cluster=feedback.get('cluster')
        if cluster in control.grounding_hypotheses:
            control.grounding_hypotheses[cluster]['bridge_rule_ids']=[]
        if answer is not None:
            control.observe_grounding_probe(proposal['probe_id'],not answer)
        control_retained=bool(rule_ids) and status(control,rel)=='hypothesis'

        start=time.process_time()
        correction=(bot.observe_grounding_probe(proposal['probe_id'],not answer)
                    if answer is not None else {'status':'no_environment_answer'})
        phases['rollback']=time.process_time()-start
        start=time.process_time()
        rolled_back=(correction['status']=='grounding_conflict' and
                     correction.get('rules_withdrawn')==2 and not touching(bot,raw) and
                     status(bot,rel)=='unknown' and status(bot,inverse)=='unknown')
        independent_kept=(all(bot.kb.contains(atom) for atom in raw_atoms+education_atoms) and
                          bot.kb.contains(said_atom) and
                          (bot.language.parse(held).get('frame') or {}).get('pred')==raw)
        phases['inference']=time.process_time()-start
        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['persistence']+=time.process_time()-start
        persisted=(not touching(bot,raw) and status(bot,rel)=='unknown' and
                   all(bot.kb.contains(atom) for atom in raw_atoms) and bot.kb.contains(said_atom))

    fresh_bot=Bot()
    fresh={'probe':fresh_bot.propose_grounding_probe()['status'],
           'held_parse':fresh_bot.language.parse(held)['status']}

    def control_route(bot: Bot, **options) -> dict:
        education=educate(bot,spec,**options); control_roots=education['roots']
        collect(bot,spec)
        row=abstention(bot,spec,held)
        held_pred=(bot.language.parse(held).get('frame') or {}).get('pred')
        bot.respond(held)
        return {'probe':row['probe'],'feedback':row['feedback'],
                'rules_on_held':touching(bot,held_pred),
                'derived':[bot.answer_atom(Atom(str(root),want))['status'] if root else None
                           for root in control_roots]}

    memory=control_route(Bot(grounded_language=False))
    no_negation=control_route(Bot(),negation=False)
    single=control_route(Bot(),rel1_pairs=(7,8,9))
    return {'root_statuses':education['root_statuses'],'contrast':education['contrast'],
            'third':statuses,'raw_root':raw,'possible_before':possible_before,
            'induced_roots':induced_roots,'restored':restored,'kept_rivals':kept_rivals,
            'no_bridge_before':no_bridge_before,
            'probe':proposal.get('status'),'probe_text':probe_text,
            'chosen_discriminating':chosen,'offered':proposal.get('offered',0),
            'invented':invented,'environment_answer':answer,
            'pending_survives_restart':pending_survives,
            'feedback':feedback['status'],'bridge':bridge,'bridge_rule_ids':rule_ids,
            'no_collision':no_collision,'stored':stored,'said':said,'derived':derived,
            'interpreted':interpreted,'bridge_survives_restart':bridge_survives,
            'control_retained':control_retained,'correction':correction['status'],
            'rules_withdrawn':correction.get('rules_withdrawn'),'rolled_back':rolled_back,
            'independent_kept':independent_kept,'persisted':persisted,
            'fresh':fresh,'memory':memory,'no_negation':no_negation,'single':single,
            'target':target,'reverse':spec['reverse'],
            'phases':{key:round(value,6) for key,value in phases.items()}}


def abstained(row: dict) -> bool:
    return row['feedback'] is None and quiet(row)


SCORED=('induced_roots','restored','kept_rivals','no_bridge_before','chosen_discriminating',
        'bridge','interpreted','rolled_back','independent_kept','persisted',
        'bridge_survives_restart','pending_survives_restart','invented','control_retained')


def main() -> None:
    dev='--dev' in sys.argv[1:]
    cpu_start=time.process_time(); wall_start=time.perf_counter()
    before=tree(); clean_before=frozen()
    seed=DEV_SEED if dev else int(before[:8],16)
    rng=random.Random(seed)
    specs=[]; renamed_specs=[]
    for index in range(12):
        specs.append(family(rng,index))
        renamed_specs.append(family(rng,index,renamed=True))
    rows=[evaluate(spec) for spec in specs]
    renamed=[evaluate(spec) for spec in renamed_specs]
    archived={tag:run_archived(tag,specs) for tag in ARCHIVED}
    g1_rows,g1_tree=archived['estable-G-1']
    g27_rows,g27_tree=archived['freeze-G-27']
    after=tree(); clean=clean_before and frozen()

    restored=sum(r['induced_roots'] and r['restored'] and r['kept_rivals'] and
                 r['no_bridge_before'] for r in rows)
    g1_restored=sum(row['restored'] for row in g1_rows)
    g27_restored=sum(row['restored'] for row in g27_rows)
    asked=sum(r['chosen_discriminating'] and r['bridge'] and r['interpreted'] for r in rows)
    rolled_back=sum(r['rolled_back'] for r in rows)
    independent=sum(r['independent_kept'] for r in rows)
    restarts=sum(r['pending_survives_restart'] and r['bridge_survives_restart'] and
                 r['persisted'] for r in rows)
    rename_invariant=sum(all(a[key]==b[key] for key in SCORED) for a,b in zip(rows,renamed))
    incompatible=sum(abstained(r['no_negation']) and abstained(r['single']) for r in rows)
    memory_quiet=sum(abstained(r['memory']) for r in rows)
    g1_quiet=sum(quiet(row) for row in g1_rows)
    fresh_quiet=sum(r['fresh']=={'probe':'no_epistemic_action','held_parse':'unrecognized'}
                    for r in rows)
    honest=sum(not r['invented'] for r in rows+renamed)
    ablated=sum(r['control_retained'] for r in rows)

    cpu=time.process_time()-cpu_start
    children=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_children=children.ru_utime+children.ru_stime
    wall=time.perf_counter()-wall_start
    rss=max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children.ru_maxrss)
    offered=max(r['offered'] for r in rows+renamed)
    budget=cpu+cpu_children<=30 and wall<=45 and rss<=128*1024 and offered<=256
    trees_ok='engine_path_mismatch' not in (g1_tree,g27_tree)
    result={'kind':'G27b_raw_root_bridge','preregistration':PREREG,'development':dev,
            'engine_tree':before,'engine_unchanged':before==after,'engine_committed':clean,
            'seed':seed,'hashseed':os.environ.get('PYTHONHASHSEED'),
            'families':12,'rows':rows,'rename_rows':renamed,
            'g1_engine_tree':g1_tree,'g1_rows':g1_rows,
            'g27_engine_tree':g27_tree,'g27_rows':g27_rows,
            'restored_and_pending':restored,'g1_restored':g1_restored,
            'g27_restored':g27_restored,'asked_and_bridged':asked,
            'rolled_back':rolled_back,'independent_kept':independent,'restarts':restarts,
            'rename_invariant':rename_invariant,'incompatible_abstained':incompatible,
            'memory_abstained':memory_quiet,'g1_no_bridge':g1_quiet,'fresh_quiet':fresh_quiet,
            'no_invented_answers':honest,'ablated_retained':ablated,'max_offered':offered,
            'cpu_total_s':round(cpu+cpu_children,6),'cpu_children_s':round(cpu_children,6),
            'wall_total_s':round(wall,6),'max_rss_kib':rss,'budget_ok':budget,
            'gate_pass':(restored==12 and restored>=g1_restored and asked>=10 and
                         rolled_back==12 and independent==12 and restarts==12 and
                         rename_invariant==12 and incompatible==12 and memory_quiet==12 and
                         g1_quiet==12 and fresh_quiet==12 and honest==24 and ablated==12 and
                         budget and before==after and clean and trees_ok)}
    name='g27b_raw_root_bridge_dev' if dev else f'g27b_raw_root_bridge_{seed}'
    out=ROOT/'results_v3'/f'{name}_hashseed{result["hashseed"]}.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:result[key] for key in (
        'engine_tree','seed','restored_and_pending','g1_restored','g27_restored',
        'asked_and_bridged','rolled_back','independent_kept','restarts','rename_invariant',
        'incompatible_abstained','memory_abstained','g1_no_bridge','fresh_quiet',
        'no_invented_answers','ablated_retained','engine_committed','cpu_total_s',
        'wall_total_s','max_rss_kib','budget_ok','gate_pass')},sort_keys=True))


if __name__=='__main__':
    main()

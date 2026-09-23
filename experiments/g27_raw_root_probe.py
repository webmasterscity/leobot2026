"""G-27 frozen-engine assay: ask about a phrase using roots induced from raw text.

Everything reaches the bot as natural text through ``Bot.respond``; the
evaluator only reads the knowledge base to score.  The environment answers the
bot's own yes/no question from its world table after the proposal.

Controls: the stable G-1 engine (``estable-G-1`` archived into a temporary
directory and run in a child process), fresh bot, memory only
(``grounded_language=False``), two incompatible structures -- no explicit
negation, and a third surface whose pairs support a single hypothesis
(co-occurrence without a rival) -- full renaming, contradictory answer with
rollback, and save/load before feedback, after use and after rollback.

Reported outside the gate: a third sentence of the new phrase on the same pairs.
G-1 may induce a new opaque root there and store the facts; the collect-only
route keeps them as pending observations until the question is answered.

Run ``python -m experiments.g27_raw_root_probe --dev`` for the visible
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


ROOT=Path(__file__).resolve().parents[1]
PREREG='prereg/G-27-pregunta-desde-relaciones-crudas.md'
G1_TAG='estable-G-1'
DEV_SEED=27
ALPHABET='abcdefghjkmnpqrstuvwxyz'


def tree(ref: str = 'HEAD') -> str:
    return subprocess.check_output(['git','rev-parse',f'{ref}:leobot'],cwd=ROOT,text=True).strip()


def frozen() -> bool:
    """The fingerprint describes what runs only if engine and evaluator are committed."""
    return not subprocess.check_output(
        ['git','status','--porcelain','--','leobot','experiments/g27_raw_root_probe.py'],
        cwd=ROOT,text=True).strip()


def family(rng: random.Random, index: int, renamed: bool = False) -> dict:
    """Fresh vocabulary; target relation and role order alternate independently."""
    prefix='x' if renamed else ''
    def word() -> str:
        return prefix+''.join(rng.choice(ALPHABET) for _ in range(9))
    verbs=[word() for _ in range(3)]
    # 0-2 education, 3 contrast, 4 new pair, 5-6 independent source, 7-9 rel1 only.
    pairs=[(word().capitalize(),word().capitalize()) for _ in range(10)]
    return {'verbs':verbs,'pairs':pairs,'target':index%2,'reverse':bool((index//2)%2)}


def relation(spec: dict, rel: int, pair, negated: bool = False) -> str:
    a,b=pair
    return f'{a} no {spec["verbs"][rel]} {b}' if negated else f'{a} {spec["verbs"][rel]} {b}'


def third(spec: dict, pair) -> str:
    a,b=pair
    return f'{b} {spec["verbs"][2]} {a}' if spec['reverse'] else f'{a} {spec["verbs"][2]} {b}'


def world(spec: dict) -> dict[str, bool]:
    """Truth of the third surface for pairs whose facts the bot has read."""
    truth={normalize(third(spec,pair)):True for pair in spec['pairs'][:3]}
    truth[normalize(third(spec,spec['pairs'][3]))]=spec['target']==0
    return truth


def educate(bot: Bot, spec: dict, *, negation: bool = True,
            rel1_pairs: tuple[int, ...] = (0,1,2)) -> dict:
    """Two raw relations, a contrast pair, then two sentences of a third surface."""
    roots=[]; statuses=[]
    for rel,indices in ((0,(0,1,2)),(1,rel1_pairs)):
        last={}
        for index in indices:
            last=bot.respond(relation(spec,rel,spec['pairs'][index]))
        statuses.append(last.get('status'))
        roots.append(last.get('predicate'))
    contrast=[bot.respond(relation(spec,0,spec['pairs'][3]))['status']]
    if negation:
        contrast.append(bot.respond(relation(spec,1,spec['pairs'][3],negated=True))['status'])
    return {'roots':roots,'root_statuses':statuses,'contrast':contrast}


def collect(bot: Bot, spec: dict) -> list[str]:
    return [bot.respond(third(spec,pair))['status'] for pair in spec['pairs'][:2]]


def answer_for(spec: dict, probe_text: str | None) -> bool | None:
    return world(spec).get(probe_text) if probe_text is not None else None


def abstention(bot: Bot, spec: dict, held: str) -> dict:
    """Ask for a probe, answer it only from the world, and check the new pair."""
    proposal=bot.propose_grounding_probe()
    feedback=None
    if proposal.get('status')=='epistemic_action':
        answer=answer_for(spec,proposal.get('probe_text'))
        if answer is not None:
            feedback=bot.observe_grounding_probe(proposal['probe_id'],answer)['status']
    parsed=bot.language.parse(held)
    return {'probe':proposal.get('status'),'feedback':feedback,'held_parse':parsed['status'],
            'learned':parsed['status']=='parsed'}


def third_sentence(spec: dict) -> dict:
    """Diagnostic outside the gate: one more sentence of the phrase, same pairs."""
    bot=Bot()
    educate(bot,spec); collect(bot,spec)
    before=len(bot.kb.facts)
    status=bot.respond(third(spec,spec['pairs'][2]))['status']
    return {'status':status,'facts_added':len(bot.kb.facts)-before}


def g1_route(spec: dict) -> dict:
    """Same text sequence for whatever engine ``leobot`` resolves to."""
    import leobot
    bot=Bot()
    education=educate(bot,spec)
    statuses=collect(bot,spec)
    held=third(spec,spec['pairs'][4])
    return {'engine_path':str(Path(leobot.__file__).resolve().parent),
            'root_statuses':education['root_statuses'],'third':statuses,
            **abstention(bot,spec,held),'third_sentence':third_sentence(spec)}


def g1_control_main() -> None:
    specs=json.loads(sys.stdin.read())
    print(json.dumps([g1_route(spec) for spec in specs]))


def run_g1_control(specs: list[dict]) -> tuple[list[dict], str]:
    with tempfile.TemporaryDirectory() as directory:
        archive=subprocess.run(['git','archive',G1_TAG,'leobot'],cwd=ROOT,check=True,
                               capture_output=True).stdout
        subprocess.run(['tar','-x','-C',directory],input=archive,check=True)
        code=('import sys; sys.path.insert(0,%r); sys.path.insert(1,%r); '
              'from experiments.g27_raw_root_probe import g1_control_main; g1_control_main()'
              % (directory,str(ROOT)))
        output=subprocess.run([sys.executable,'-c',code],cwd=directory,check=True,
                              input=json.dumps(specs),capture_output=True,text=True).stdout
        rows=json.loads(output)
        inside=all(Path(row['engine_path'])==Path(directory,'leobot').resolve() for row in rows)
    return rows,tree(G1_TAG) if inside else 'engine_path_mismatch'


def evaluate(spec: dict) -> dict:
    phases={}
    pairs=spec['pairs']; target=spec['target']
    held=third(spec,pairs[4]); contrast=normalize(third(spec,pairs[3]))

    start=time.process_time(); bot=Bot()
    education=educate(bot,spec)
    phases['roots']=time.process_time()-start
    roots=education['roots']
    induced_roots=(education['root_statuses']==['raw_relation_learned']*2 and
                   None not in roots and roots[0]!=roots[1])
    start=time.process_time(); statuses=collect(bot,spec)
    phases['collection']=time.process_time()-start
    open_clusters=[state for state in bot.grounding_hypotheses.values()
                   if not state.get('conflict')]
    possible_before=[len(state.get('possible',())) for state in open_clusters]
    promoted_before=any(state.get('promoted') for state in open_clusters)
    before=bot.language.parse(held)['status']
    kept_rivals=(statuses==['grounding_pending']*2 and possible_before==[2] and
                 not promoted_before and before=='unrecognized')

    start=time.process_time(); proposal=bot.propose_grounding_probe()
    phases['selection']=time.process_time()-start
    probe_text=proposal.get('probe_text')
    chosen=probe_text==contrast
    pending=[state.get('pending_probe') for state in bot.grounding_hypotheses.values()
             if state.get('pending_probe')]
    # Nothing may answer the question before the environment does.
    invented=any(row.get('answer') is not None for row in pending)
    answer=answer_for(spec,probe_text)
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

        start=time.process_time(); parsed=bot.language.parse(held)
        phases['inference']=time.process_time()-start
        frame=parsed.get('frame') or {}
        want=[normalize(value) for value in pairs[4]]
        interpreted=(parsed['status']=='parsed' and roots[target] is not None and
                     frame.get('pred')==roots[target] and frame.get('args')==want)
        start=time.process_time()
        stored=bot.respond(held)
        dependent_id=stored.get('id')
        dependent_atom=Atom(str(roots[target]),tuple(want))
        tracked=bot.grounding_fact_dependencies.get(dependent_id) is not None
        # Pair 5 is said through the learned phrase and then again through the
        # raw relation; pair 6 only through the raw relation.
        both_texts=[third(spec,pairs[5]),relation(spec,target,pairs[5])]
        both=[bot.respond(text)['status'] for text in both_texts]
        only_raw=bot.respond(relation(spec,target,pairs[6]))['status']
        phases['use']=time.process_time()-start
        both_atom=Atom(str(roots[target]),tuple(normalize(v) for v in pairs[5]))
        raw_atom=Atom(str(roots[target]),tuple(normalize(v) for v in pairs[6]))
        education_atoms=[Atom(str(roots[rel]),tuple(normalize(v) for v in pairs[index]))
                         for rel in (0,1) for index in (0,1,2)]
        education_atoms.append(Atom(str(roots[0]),tuple(normalize(v) for v in pairs[3])))
        education_atoms.append(Atom('!'+str(roots[1]),tuple(normalize(v) for v in pairs[3])))

        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['persistence']+=time.process_time()-start
        dependency_survives=bot.grounding_fact_dependencies.get(dependent_id) is not None
        # Same history and correction with only the dependency register ablated.
        control=Bot.load(path)
        control.grounding_fact_dependencies.pop(dependent_id,None)
        cluster=feedback.get('cluster')
        if cluster in control.grounding_hypotheses:
            control.grounding_hypotheses[cluster]['derived_fact_ids']=[]
        if answer is not None:
            control.observe_grounding_probe(proposal['probe_id'],not answer)
        control_retained=dependent_id is not None and control.kb.get_fact(dependent_id) is not None

        start=time.process_time()
        correction=(bot.observe_grounding_probe(proposal['probe_id'],not answer)
                    if answer is not None else {'status':'no_environment_answer'})
        phases['rollback']=time.process_time()-start
        start=time.process_time()
        dependent_gone=(dependent_id is not None and bot.kb.get_fact(dependent_id) is None and
                        not bot.kb.contains(dependent_atom))
        unknown_surface=bot.language.parse(held)['status']=='unrecognized'
        independent_kept=(bot.kb.contains(both_atom) and bot.kb.contains(raw_atom) and
                          all(bot.kb.contains(atom) for atom in education_atoms))
        phases['inference']+=time.process_time()-start
        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['persistence']+=time.process_time()-start
        persisted=(not bot.kb.contains(dependent_atom) and bot.kb.contains(both_atom) and
                   bot.kb.contains(raw_atom) and
                   bot.language.parse(held)['status']=='unrecognized')

    fresh_bot=Bot()
    fresh={'probe':fresh_bot.propose_grounding_probe()['status'],
           'held_parse':fresh_bot.language.parse(held)['status']}
    memory_bot=Bot(grounded_language=False)
    memory_education=educate(memory_bot,spec)
    memory={'root_statuses':memory_education['root_statuses'],
            'third':collect(memory_bot,spec),**abstention(memory_bot,spec,held)}
    no_negation_bot=Bot()
    educate(no_negation_bot,spec,negation=False)
    no_negation={'third':collect(no_negation_bot,spec),
                 **abstention(no_negation_bot,spec,held)}
    single_bot=Bot()
    single_education=educate(single_bot,spec,rel1_pairs=(7,8,9))
    single={'root_statuses':single_education['root_statuses'],
            'third':collect(single_bot,spec),**abstention(single_bot,spec,held)}
    return {'root_statuses':education['root_statuses'],'contrast':education['contrast'],
            'third':statuses,'possible_before':possible_before,
            'promoted_before':promoted_before,'before':before,
            'induced_roots':induced_roots,'kept_rivals':kept_rivals,
            'probe':proposal.get('status'),'probe_text':probe_text,
            'chosen_discriminating':chosen,'offered':proposal.get('offered',0),
            'invented':invented,'environment_answer':answer,
            'pending_survives_restart':pending_survives,
            'feedback':feedback['status'],'interpreted':interpreted,
            'stored':stored['status'],'tracked':tracked,'both':both,'only_raw':only_raw,
            'dependency_survives_restart':dependency_survives,
            'control_retained':control_retained,'correction':correction['status'],
            'facts_withdrawn':correction.get('facts_withdrawn'),
            'dependent_gone':dependent_gone,'unknown_surface':unknown_surface,
            'independent_kept':independent_kept,'persisted':persisted,
            'fresh':fresh,'memory':memory,'no_negation':no_negation,'single':single,
            'third_sentence':third_sentence(spec),
            'target':target,'reverse':spec['reverse'],
            'phases':{key:round(value,6) for key,value in phases.items()}}


def abstained(row: dict) -> bool:
    return row['feedback'] is None and not row['learned']


SCORED=('induced_roots','kept_rivals','chosen_discriminating','interpreted','tracked',
        'dependent_gone','independent_kept','persisted','dependency_survives_restart',
        'pending_survives_restart','invented','unknown_surface')


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
    g1_rows,g1_tree=run_g1_control(specs)
    after=tree(); clean=clean_before and frozen()

    induced=sum(r['induced_roots'] and r['kept_rivals'] for r in rows)
    asked=sum(r['chosen_discriminating'] and r['feedback']=='grounding_promoted' and
              r['interpreted'] and r['stored']=='stored' and r['tracked'] for r in rows)
    rolled_back=sum(r['correction']=='grounding_conflict' and r['dependent_gone'] and
                    r['unknown_surface'] for r in rows)
    independent=sum(r['independent_kept'] for r in rows)
    restarts=sum(r['pending_survives_restart'] and r['dependency_survives_restart'] and
                 r['persisted'] for r in rows)
    rename_invariant=sum(all(a[key]==b[key] for key in SCORED) for a,b in zip(rows,renamed))
    incompatible=sum(abstained(r['no_negation']) and abstained(r['single']) for r in rows)
    memory_quiet=sum(abstained(r['memory']) for r in rows)
    g1_quiet=sum(not row['learned'] for row in g1_rows)
    fresh_quiet=sum(r['fresh']=={'probe':'no_epistemic_action','held_parse':'unrecognized'}
                    for r in rows)
    honest=sum(not r['invented'] for r in rows+renamed)
    ablated=sum(r['control_retained'] for r in rows)
    third_stored=sum(r['third_sentence']['facts_added']>0 for r in rows)
    g1_third_stored=sum(row['third_sentence']['facts_added']>0 for row in g1_rows)

    cpu=time.process_time()-cpu_start
    children=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_children=children.ru_utime+children.ru_stime
    wall=time.perf_counter()-wall_start
    rss=max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children.ru_maxrss)
    offered=max(r['offered'] for r in rows+renamed)
    budget=cpu+cpu_children<=30 and wall<=45 and rss<=128*1024 and offered<=256
    result={'kind':'G27_raw_root_probe','preregistration':PREREG,'development':dev,
            'engine_tree':before,'engine_unchanged':before==after,'engine_committed':clean,
            'seed':seed,'hashseed':os.environ.get('PYTHONHASHSEED'),
            'families':12,'rows':rows,'rename_rows':renamed,
            'g1_engine_tree':g1_tree,'g1_rows':g1_rows,
            'induced_and_pending':induced,'asked_and_interpreted':asked,
            'rolled_back':rolled_back,'independent_kept':independent,'restarts':restarts,
            'rename_invariant':rename_invariant,'incompatible_abstained':incompatible,
            'memory_abstained':memory_quiet,'g1_not_learned':g1_quiet,'fresh_quiet':fresh_quiet,
            'no_invented_answers':honest,'ablated_retained':ablated,'max_offered':offered,
            'third_sentence_stored':third_stored,'g1_third_sentence_stored':g1_third_stored,
            'cpu_total_s':round(cpu+cpu_children,6),'cpu_children_s':round(cpu_children,6),
            'wall_total_s':round(wall,6),'max_rss_kib':rss,'budget_ok':budget,
            'gate_pass':(induced>=10 and asked>=10 and rolled_back==12 and
                         independent==12 and restarts==12 and rename_invariant==12 and
                         incompatible==12 and memory_quiet==12 and g1_quiet==12 and
                         fresh_quiet==12 and honest==24 and budget and before==after and clean and
                         g1_tree!='engine_path_mismatch')}
    name='g27_raw_root_probe_dev' if dev else f'g27_raw_root_probe_{seed}'
    out=ROOT/'results_v3'/f'{name}_hashseed{result["hashseed"]}.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:result[key] for key in (
        'engine_tree','seed','induced_and_pending','asked_and_interpreted','rolled_back',
        'independent_kept','restarts','rename_invariant','incompatible_abstained',
        'memory_abstained','g1_not_learned','fresh_quiet','no_invented_answers',
        'ablated_retained','third_sentence_stored','g1_third_sentence_stored',
        'engine_committed','cpu_total_s','wall_total_s','max_rss_kib','budget_ok',
        'gate_pass')},sort_keys=True))


if __name__=='__main__':
    main()

"""G-26b frozen-engine assay: retract conclusions derived from a learned phrase."""
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
from leobot.core import Atom
from .g26_grounding_probe import bot_for, educate, family, utterance


ROOT=Path(__file__).resolve().parents[1]


def tree() -> str:
    return subprocess.check_output(['git','rev-parse','HEAD:leobot'],cwd=ROOT,text=True).strip()


def evaluate(spec: dict) -> dict:
    phases={}; start=time.process_time()
    bot=bot_for(spec)
    education=educate(bot,spec)
    phases['acquisition']=time.process_time()-start
    fresh=bot_for(spec).propose_grounding_probe()['status']
    incompatible=bot_for(spec,negative=False)
    educate(incompatible,spec)
    incompatible_status=incompatible.propose_grounding_probe()['status']
    memory=bot_for(spec,learner=False)
    educate(memory,spec)
    held=utterance(spec,spec['entities'][4])
    before=bot.language.parse(held)['status']
    start=time.process_time(); proposal=bot.propose_grounding_probe()
    phases['selection']=time.process_time()-start
    contrast=utterance(spec,spec['entities'][3])
    chosen=proposal.get('probe_text')==contrast
    answer=spec['target']==0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'bot.json'
        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['restart_before']=time.process_time()-start
        start=time.process_time()
        feedback=bot.observe_grounding_probe(proposal['probe_id'],answer)
        phases['feedback']=time.process_time()-start
        start=time.process_time()
        stored=bot.respond(held)
        phases['storage']=time.process_time()-start
        target=spec['pred'][spec['target']]
        dependent_atom=Atom(target,spec['entities'][4])
        dependent_id=stored.get('id')
        tracked=bot.grounding_fact_dependencies.get(dependent_id) is not None
        supported=bot.answer_atom(dependent_atom)['status']=='supported'

        independently_supported=tuple(value+'x' for value in spec['entities'][4])
        independent_text=utterance(spec,independently_supported)
        second=bot.respond(independent_text)
        independent_atom=Atom(target,independently_supported)
        independent_id=bot.kb.add(independent_atom,'fuente independiente')
        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['restart_after_use']=time.process_time()-start
        dependency_survives_restart=bot.grounding_fact_dependencies.get(dependent_id) is not None
        # Same observations and correction, with only the dependency register
        # ablated.  The obsolete derived fact should then remain as a false claim.
        control=Bot.load(path)
        control.grounding_fact_dependencies.pop(dependent_id,None)
        control.grounding_hypotheses[feedback['cluster']]['derived_fact_ids']=[]
        control.observe_grounding_probe(proposal['probe_id'],not answer)
        control_retained=control.kb.get_fact(dependent_id) is not None
        start=time.process_time(); correction=bot.observe_grounding_probe(proposal['probe_id'],not answer)
        phases['rollback']=time.process_time()-start
        start=time.process_time()
        dependent_gone=bot.kb.get_fact(dependent_id) is None and bot.answer_atom(dependent_atom)['status']=='unknown'
        independent_kept=(bot.kb.get_fact(independent_id) is not None and
                          bot.kb.contains(independent_atom) and
                          bot.kb.get_fact(second['id']) is None)
        unknown_surface=bot.language.parse(held)['status']=='unrecognized'
        phases['inference']=time.process_time()-start
        start=time.process_time(); bot.save(path); bot=Bot.load(path)
        phases['restart_after_rollback']=time.process_time()-start
        persisted=(bot.kb.get_fact(dependent_id) is None and
                   bot.kb.contains(independent_atom) and
                   bot.language.parse(held)['status']=='unrecognized')
    return {'education':education,'before':before,'chosen_discriminating':chosen,
            'offered':proposal.get('offered',0),'feedback':feedback['status'],
            'stored':stored['status'],'tracked':tracked,'supported':supported,
            'second_stored':second['status'],'dependency_survives_restart':dependency_survives_restart,
            'correction':correction['status'],'facts_withdrawn':correction.get('facts_withdrawn'),
            'dependent_gone':dependent_gone,'independent_kept':independent_kept,
            'unknown_surface':unknown_surface,'persisted':persisted,
            'control_retained':control_retained,'fresh':fresh,
            'memory_parse':memory.language.parse(held)['status'],
            'incompatible':incompatible_status,'target':spec['target'],
            'reverse':spec['reverse'],
            'phases':{key:round(value,6) for key,value in phases.items()}}


def main() -> None:
    cpu_start=time.process_time(); wall_start=time.perf_counter()
    before=tree(); seed=int(before[:8],16); rng=random.Random(seed)
    rows=[]; renamed=[]
    for index in range(12):
        rows.append(evaluate(family(rng,index)))
        renamed.append(evaluate(family(rng,index,renamed=True)))
    after=tree()
    quality=sum(r['chosen_discriminating'] and r['feedback']=='grounding_promoted'
                and r['stored']=='stored' and r['tracked'] for r in rows)
    invalidated=sum(r['correction']=='grounding_conflict' and
                    r['dependent_gone'] and r['unknown_surface'] for r in rows)
    independent=sum(r['independent_kept'] for r in rows)
    persisted=sum(r['dependency_survives_restart'] and r['persisted'] for r in rows)
    ablated=sum(not r['control_retained'] for r in rows)
    renamed_same=sum(a['chosen_discriminating']==b['chosen_discriminating'] and
                     a['dependent_gone']==b['dependent_gone'] and
                     a['independent_kept']==b['independent_kept']
                     for a,b in zip(rows,renamed))
    cpu=time.process_time()-cpu_start; wall=time.perf_counter()-wall_start
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    budget=cpu<=30 and wall<=45 and rss<=128*1024
    result={'kind':'G26b_grounding_dependencies',
            'preregistration':'prereg/G-26b-dependencias-de-frases-aprendidas.md',
            'engine_tree':before,'engine_unchanged':before==after,
            'seed':seed,'hashseed':os.environ.get('PYTHONHASHSEED'),
            'families':12,'examples_per_family':2,'rows':rows,'rename_rows':renamed,
            'quality_passes':quality,'invalidated':invalidated,
            'independent_kept':independent,'persisted':persisted,
            'ablated_invalidations':ablated,'rename_invariant':renamed_same,
            'cpu_total_s':round(cpu,6),'wall_total_s':round(wall,6),
            'max_rss_kib':rss,'budget_ok':budget,
            'gate_pass':(quality>=10 and invalidated==12 and independent==12
                         and persisted==12 and ablated==0 and renamed_same==12
                         and budget and before==after and all(
                             r['fresh']=='no_epistemic_action' and
                             r['memory_parse']=='unrecognized' and
                             r['incompatible']=='no_epistemic_action' and
                             r['before']=='unrecognized' for r in rows))}
    out=ROOT/'results_v3'/f'g26b_grounding_dependencies_{seed}_hashseed{result["hashseed"]}.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:result[key] for key in ('engine_tree','seed','quality_passes',
                        'invalidated','independent_kept','persisted',
                        'ablated_invalidations','rename_invariant',
                        'cpu_total_s','max_rss_kib','budget_ok','gate_pass')},
                     sort_keys=True))


if __name__=='__main__':
    main()

from __future__ import annotations

import hashlib
import json
import random
import statistics
import tempfile
import time
from pathlib import Path

from leobot import Bot
from experiments.v59_architecture_freeze import teach_role_set
from experiments.v60_meta_dependency_experiment import ROLE_SETS, LABELS, diagnostic_rows, target

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results_v3' / 'v64_rbf_meta_router.json'
PAIRS = [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / 'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def educate_search_history(bot: Bot) -> None:
    for i, roles in enumerate(ROLE_SETS):
        teach_role_set(bot, i, roles)
    bot.programs.max_candidates = 150
    for label, roles in zip(LABELS, ROLE_SETS):
        for state in diagnostic_rows(roles):
            bot.observe_transition(f'Formula {label}.', state, (target(state, roles),))


def pollute_four_arity_library(bot: Bot) -> None:
    """Populate plausible but irrelevant 4-arity skills via ordinary learning.

    These are not hidden answers.  They make auto_library a realistic wrong first
    choice for the new 4:2 structural class, so the router has something causal to
    optimize rather than winning against an empty baseline.
    """
    rows = [(2,3,5,7),(4,6,8,10),(3,5,7,9),(6,2,4,8),(9,3,2,5),(1,4,6,8)]
    funcs = []
    for a in range(4):
        for c in (-1, 1):
            funcs.append(lambda x, a=a, c=c: x[a] + c)
    for a, c in [(0,1),(1,2),(2,3),(0,2),(1,3),(0,3)]:
        funcs.append(lambda x, a=a, c=c: x[a] + x[c])
    for idx, fn in enumerate(funcs):
        name = f'junk{idx}'
        for row in rows:
            bot.programs.add_example(name, row, fn(row), concepts={'cruce','cuatro'})
        rep = bot.programs.fit(name, library=[])
        if rep.get('status') != 'learned_hypothesis':
            raise RuntimeError(f'failed to seed learned distractor {idx}: {rep}')


def diagnostic_rows4(pair: tuple[int,int]):
    base=[2,3,5,7]; rows=[tuple(base)]
    for k in range(4):
        if k not in pair:
            q=base.copy(); q[k]+=11; rows.append(tuple(q))
    for k in pair:
        q=base.copy(); q[k]+=2; rows.append(tuple(q))
    return rows


def heldout(bot: Bot, pair: tuple[int,int], seed: int, n: int = 100) -> int:
    rng = random.Random(seed)
    ok = 0
    for _ in range(n):
        row=tuple(rng.randint(-100,100) for _ in range(4))
        expected=(row[pair[0]] * row[pair[1]] + 1,)
        ok += bot.execute_transition('Cruce cuatro.', row).get('result') == expected
    return ok


def attempt_cost(report: dict) -> int:
    return sum(int(x.get('candidates') or 0) for x in report.get('meta_dependency_attempts', ()))


def run_pair(pair: tuple[int,int], seed: int) -> dict:
    treatment=Bot(); control=Bot(); control.procedures.rbf_strategy_enabled=False
    for b in (treatment,control):
        educate_search_history(b)
        pollute_four_arity_library(b)
        b.programs.max_candidates=150
    tr=cr=None
    for state in diagnostic_rows4(pair):
        y=(state[pair[0]]*state[pair[1]]+1,)
        tr=treatment.observe_transition('Cruce cuatro.', state, y)
        cr=control.observe_transition('Cruce cuatro.', state, y)
    td=tr['reports'][0]; cd=cr['reports'][0]
    return {
        'pair': list(pair),
        'treatment_status': tr.get('status'),
        'control_status': cr.get('status'),
        'rbf_used': bool(td.get('meta_dependency_rbf_route',{}).get('used')),
        'rbf_scores': td.get('meta_dependency_rbf_route',{}).get('scores',[]),
        'treatment_order': td.get('meta_dependency_strategy_order'),
        'control_order': cd.get('meta_dependency_strategy_order'),
        'treatment_candidates': attempt_cost(td),
        'control_candidates': attempt_cost(cd),
        'treatment_heldout': heldout(treatment,pair,seed,100),
        'control_heldout': heldout(control,pair,seed,100),
        'router_observations': treatment.procedures.rbf_strategy_router.observations,
        'router_distilled': treatment.procedures.rbf_strategy_router.distilled,
        'router_nodes': sum(len(v) for v in treatment.procedures.rbf_strategy_router.nodes.values()),
    }


def one_role_control() -> dict:
    treatment=Bot(); control=Bot(); control.procedures.rbf_strategy_enabled=False
    for b in (treatment,control):
        educate_search_history(b); b.programs.max_candidates=150
    base=[2,3,5,7]; rows=[tuple(base)]
    for k in (1,2,3):
        q=base.copy();q[k]+=11;rows.append(tuple(q))
    q=base.copy();q[0]+=2;rows.append(tuple(q))
    tr=cr=None
    for state in rows:
        y=(state[0]*state[0]+1,)
        tr=treatment.observe_transition('Cuadrado nuevo.',state,y)
        cr=control.observe_transition('Cuadrado nuevo.',state,y)
    td=tr['reports'][0];cd=cr['reports'][0]
    rng=random.Random(646401); tok=cok=0
    for _ in range(100):
        row=tuple(rng.randint(-100,100) for _ in range(4)); expected=(row[0]*row[0]+1,)
        tok += treatment.execute_transition('Cuadrado nuevo.',row).get('result')==expected
        cok += control.execute_transition('Cuadrado nuevo.',row).get('result')==expected
    return {
        'treatment_status':tr.get('status'),'control_status':cr.get('status'),
        'treatment_order':td.get('meta_dependency_strategy_order'),
        'control_order':cd.get('meta_dependency_strategy_order'),
        'rbf_used':bool(td.get('meta_dependency_rbf_route',{}).get('used')),
        'treatment_candidates':attempt_cost(td),'control_candidates':attempt_cost(cd),
        'treatment_heldout':tok,'control_heldout':cok,
    }


def persistence_and_overhead() -> dict:
    bot=Bot(); educate_search_history(bot)
    x=bot.procedures._dependency_rbf_features(4,(0,3),5)
    timings=[]
    for _ in range(5000):
        s=time.perf_counter_ns()
        bot.procedures.rbf_strategy_router.rank(x,['auto_library','no_library'])
        timings.append((time.perf_counter_ns()-s)/1000.0)
    before=bot.procedures.rbf_strategy_router.as_dict()
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'state.json';bot.save(p);loaded=Bot.load(p)
        route=loaded.procedures.rbf_strategy_router.rank(x,['auto_library','no_library'])
        persisted=(loaded.procedures.rbf_strategy_enabled and route.get('used') and route.get('order',[None])[0]=='no_library')
    timings.sort()
    return {
        'persisted':bool(persisted),
        'router_observations':before['observations'],
        'router_distilled':before['distilled'],
        'router_nodes':sum(len(v) for v in before['nodes'].values()),
        'rank_median_us':statistics.median(timings),
        'rank_p95_us':timings[int(len(timings)*0.95)-1],
    }


def main():
    h0=code_hash();t0=time.perf_counter()
    rows=[run_pair(pair,646400+i) for i,pair in enumerate(PAIRS)]
    tc=sum(r['treatment_candidates'] for r in rows)
    cc=sum(r['control_candidates'] for r in rows)
    savings=(1.0-tc/cc)*100 if cc else 0.0
    result={
        'version':'V6.4-rbf-meta-router',
        'purpose':'non_neural_rbf_as_auxiliary_meta_search_router_not_text_generator',
        'code_hash_before':h0,
        'independent_pair_trials':rows,
        'treatment_candidates_total':tc,
        'control_candidates_total':cc,
        'candidate_savings_percent':savings,
        'treatment_heldout_total':sum(r['treatment_heldout'] for r in rows),
        'control_heldout_total':sum(r['control_heldout'] for r in rows),
        'negative_one_role_control':one_role_control(),
        'persistence_and_overhead':persistence_and_overhead(),
    }
    result['code_hash_after']=code_hash();result['code_unchanged']=result['code_hash_after']==h0
    result['elapsed_ms']=(time.perf_counter()-t0)*1000
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

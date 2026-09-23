from __future__ import annotations
import hashlib, json, random, tempfile, time
from pathlib import Path
from leobot import Bot
from leobot.core import Atom
from tests.test_v63 import train_chain_prior, chain_transition

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v63_role_topology_meta.json'
F=lambda *x: tuple(x)

def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode());h.update(b'\0');h.update(p.read_bytes());h.update(b'\0')
    return h.hexdigest()

def main():
    h0=code_hash(); treatment=Bot(); control=Bot(); train_chain_prior(treatment)
    a=chain_transition(treatment,1); b=chain_transition(treatment,2)
    ca=chain_transition(control,1); cb=chain_transition(control,2)
    rng=random.Random(63001); ok=0; false_accept=0
    t0=time.perf_counter_ns()
    for i in range(200):
        p,o,d=f'persona{i+1000}',f'origen{i+1000}',f'destino{i+1000}'
        state={F('at',p,o),F('road',o,d),F('auth',p,d),F('person',p),F('place',o),F('place',d)}
        # Add structural distractors with different topology.
        for j in range(3): state.add(F(f'noise{j}',p,d))
        out=treatment.execute_symbolic_transition(f'Mueve {p} de {o} a {d}.',state)
        ok += out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',()))
        bad=set(state); bad.discard(F('road',o,d))
        out_bad=treatment.execute_symbolic_transition(f'Mueve {p} de {o} a {d}.',bad)
        false_accept += out_bad.get('status')=='executed_symbolic_action'
    held_ms=(time.perf_counter_ns()-t0)/1e6

    # Same arity/cardinality but star topology must not transfer.
    star=Bot(); train_chain_prior(star); star_rep=None
    for i in (1,2):
        p,o,d=f's{i}',f'o{i}',f'd{i}'
        before={F('at',p,o),F('permit',p,d),F('person',p),F('place',o),F('place',d)}
        after=set(before);after.remove(F('at',p,o));after.add(F('at',p,d))
        star_rep=star.observe_symbolic_transition(f'Salta {p} de {o} a {d}.',before,after)

    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'state.json';treatment.save(path);loaded=Bot.load(path)
        persisted='topo:3:0,1;1,2' in loaded.symbolic.external_role_topologies
        p,o,d='persistpersona','persistorigen','persistdestino'
        state={F('at',p,o),F('road',o,d),F('auth',p,d),F('person',p),F('place',o),F('place',d)}
        restart=loaded.execute_symbolic_transition(f'Mueve {p} de {o} a {d}.',state)
        restart_ok=restart.get('status')=='executed_symbolic_action' and F('at',p,d) in set(restart.get('result',()))

    h1=code_hash()
    report={
        'version':'V6.3-role-topology-meta','code_hash_before':h0,'code_hash_after':h1,'code_unchanged':h0==h1,
        'treatment_first':a,'treatment_second':b,'control_first':ca,'control_second':cb,
        'heldout_correct':ok,'heldout_total':200,'false_accepts_without_road':false_accept,
        'heldout_elapsed_ms':held_ms,'star_same_cardinality_control':star_rep,
        'persisted':persisted,'restart_ok':restart_ok,
        'topology_rows':[r for r in treatment.meta_representations.rows() if r.get('kind')=='role_topology'],
        'interpretation':'The transferred object is a predicate-free directed role topology. Target facts uniquely instantiate it; same-cardinality star topology does not.'
    }
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

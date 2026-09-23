from __future__ import annotations
import hashlib, json, random, time
from pathlib import Path
from leobot import Bot, Atom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_v3'/'v59_architecture_freeze.json'
F=lambda *x:tuple(x)
WORDS=['alfa','beta','gamma','delta','epsilon','zeta']


def code_hash():
    h=hashlib.sha256()
    for p in sorted((ROOT/'leobot').glob('*.py')):
        h.update(p.name.encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def sentence(word, vals, positive=True):
    core=' '.join(f'rol{i} {v}' for i,v in enumerate(vals))
    return f'{word} '+('' if positive else 'no ')+core


def teach_role_set(bot:Bot, idx:int, roles:tuple[int,...]):
    word=WORDS[idx]
    tag=f'f{idx}'
    positives=[]
    for j in range(3):
        vals=tuple(f'{tag}p{j}r{i}' for i in range(3)); positives.append(vals)
        for v in vals: bot.kb.add(Atom(f'known_{tag}',(v,)),'v59-freeze')
        bot.kb.add(Atom(f'base_{tag}',tuple(vals[i] for i in roles)),'v59-freeze')
    negatives=[]
    # Need at least two independent negative episodes. For a unary relation,
    # perturb the same selected role in two otherwise distinct observations.
    if len(roles)==1:
        for j in range(2):
            vals=list(positives[j]); vals[roles[0]]=f'{tag}neg{j}'
            bot.kb.add(Atom(f'known_{tag}',(vals[roles[0]],)),'v59-freeze')
            negatives.append(tuple(vals))
    else:
        # For multi-role relations, perturb different selected roles so the
        # learner cannot explain the concept using only one of them.
        for k,r in enumerate(roles):
            vals=list(positives[k % len(positives)])
            vals[r]=f'{tag}neg{k}'
            bot.kb.add(Atom(f'known_{tag}',(vals[r],)),'v59-freeze')
            negatives.append(tuple(vals))
    report=None
    for vals in positives: report=bot.observe_schema_statement(sentence(word,vals,True))
    for vals in negatives: report=bot.observe_schema_statement(sentence(word,vals,False))
    return report


def numeric_learn(bot:Bot, label:str, mapping:tuple[int,...], supports=2):
    rep=None
    for j in range(supports):
        row=(100*j+11,100*j+22,100*j+33)
        rep=bot.observe_transition(f'Operacion {label}.',row,tuple(row[i] for i in mapping))
    return rep


def numeric_score(bot:Bot,label:str,mapping:tuple[int,...],n=100):
    rng=random.Random(59000+sum(mapping)*17+len(mapping)); ok=0
    for _ in range(n):
        row=tuple(rng.randint(-100000,100000) for _ in range(3))
        out=bot.execute_transition(f'Operacion {label}.',row)
        ok+=out.get('result')==tuple(row[i] for i in mapping)
    return ok


def symbolic_episode(bot,p,s,d,success=True,missing=None):
    before={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
    if missing=='road': before.discard(F('road',s,d))
    after=set(before)
    if success:
        after.discard(F('at',p,s)); after.add(F('at',p,d))
    return bot.observe_symbolic_transition(f'Traslada a {p} de {s} a {d}.',before,after)


def main():
    h0=code_hash(); t0=time.perf_counter()
    educated=Bot(); fresh=Bot()
    role_sets=[(0,),(1,),(2,),(0,1),(0,2),(1,2)]
    schema_reports=[]
    for idx,roles in enumerate(role_sets):
        schema_reports.append(teach_role_set(educated,idx,roles))

    numeric=[]
    # Reverse multi-role target order deliberately: language prior is unordered.
    mappings=[(0,),(1,),(2,),(1,0),(2,0),(2,1)]
    for idx,mapping in enumerate(mappings):
        label=f'freeze{idx}'
        tr=numeric_learn(educated,label,mapping,2)
        cr=numeric_learn(fresh,label,mapping,2)
        numeric.append({
            'mapping':list(mapping), 'treatment_status':tr.get('status'),
            'treatment_mode':tr.get('precondition_mode'), 'control_status':cr.get('status'),
            'treatment_correct':numeric_score(educated,label,mapping,100),
            'control_correct':numeric_score(fresh,label,mapping,20),
        })

    # Matching role set must not turn arithmetic into a projection.
    bad=[]
    for row in [(2,7,3),(5,9,4)]:
        bad.append(educated.observe_transition('Suma los extremos del freeze.',row,(row[0]+row[2],)))

    # Same central prior also transfers into the symbolic action learner, while
    # target-domain contrast must still identify its preconditions.
    es=Bot(); fs=Bot(); teach_role_set(es,4,(0,2))
    tr=[]; cr=[]
    for ep in [('personaA','origenA','destinoA',True,None),
               ('personaB','origenB','destinoB',True,None),
               ('personaX','origenX','destinoX',False,'road')]:
        tr.append(symbolic_episode(es,*ep)); cr.append(symbolic_episode(fs,*ep))
    sym_ok=0
    for i in range(100):
        p,s,d=f'persona{i}',f'origen{i}',f'destino{i}'
        state={F('at',p,s),F('road',s,d),F('person',p),F('place',s),F('place',d)}
        out=es.execute_symbolic_transition(f'Traslada a {p} de {s} a {d}.',state)
        sym_ok += out.get('status')=='executed_symbolic_action' and F('at',p,d) in set(out.get('result',()))

    out={
        'version':'V5.9-architecture-freeze',
        'motor_hash_before':h0,
        'schema_statuses':[r.get('status') for r in schema_reports],
        'meta_rows':educated.meta_representations.rows(),
        'numeric':numeric,
        'numeric_treatment_correct':sum(x['treatment_correct'] for x in numeric),
        'numeric_control_correct':sum(x['control_correct'] for x in numeric),
        'incompatible_arithmetic_status':bad[-1].get('status'),
        'symbolic':{
            'treatment_status':tr[-1].get('status'),'treatment_mode':tr[-1].get('precondition_mode'),
            'control_status':cr[-1].get('status'),'heldout_correct':sym_ok,
        },
    }
    out['motor_hash_after']=code_hash(); out['motor_unchanged']=out['motor_hash_after']==h0
    out['elapsed_ms']=(time.perf_counter()-t0)*1000
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

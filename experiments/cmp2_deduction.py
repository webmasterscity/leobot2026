"""CMP-2: multi-step deduction with the same information, Leobot versus a Claude subagent.

See prereg/cmp-2-deduccion-con-la-misma-informacion.md.
python3 -m experiments.cmp2_deduction --generate OUT_TASK.txt   (task text, no answers)
python3 -m experiments.cmp2_deduction --score SUBAGENT.json
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

from leobot import Bot
from leobot.core import Atom, Rule

ROOT=Path(__file__).resolve().parents[1]
RULES=['abuelo(?x,?z) :- padre(?x,?y), padre(?y,?z)',
       'bisabuelo(?x,?w) :- abuelo(?x,?y), padre(?y,?w)',
       'ancestro(?x,?y) :- padre(?x,?y)',
       'ancestro(?x,?z) :- padre(?x,?y), ancestro(?y,?z)']


def world(seed=2024):
    rng=random.Random(seed); facts=[]; n=0
    def new():
        nonlocal n; n+=1; return f'p{n:04d}'
    for _ in range(12):
        generation=[new() for _ in range(3)]
        for _ in range(5):
            children=[new() for _ in range(rng.randint(3,6))]
            for child in children:
                for parent in rng.sample(generation,rng.choice((1,2))):
                    facts.append((parent,child))
            generation=children
    return sorted(set(facts))


def closure(facts):
    children={}
    for p,c in facts: children.setdefault(p,set()).add(c)
    def grand(x): return {z for y in children.get(x,()) for z in children.get(y,())}
    def great(x): return {w for y in grand(x) for w in children.get(y,())}
    def anc(x):
        seen=set(); stack=list(children.get(x,()))
        while stack:
            y=stack.pop()
            if y not in seen: seen.add(y); stack.extend(children.get(y,()))
        return seen
    return {'abuelo':grand,'bisabuelo':great,'ancestro':anc}


def questions(facts,seed=2025):
    rel=closure(facts); people=sorted({x for f in facts for x in f}); rng=random.Random(seed); qs=[]
    while len([q for q in qs if q['kind']=='yesno'])<20:
        r=rng.choice(('ancestro','ancestro','abuelo','bisabuelo')); x=rng.choice(people); y=rng.choice(people)
        truth=y in rel[r](x); want=len([q for q in qs if q['kind']=='yesno' and q['truth']])<10
        if truth==want and x!=y and not any(q.get('atom')==(r,x,y) for q in qs):
            qs.append({'kind':'yesno','atom':(r,x,y),'truth':truth})
    while len([q for q in qs if q['kind']=='list'])<20:
        r=rng.choice(('ancestro','ancestro','abuelo','bisabuelo')); x=rng.choice(people); ans=rel[r](x)
        if 1<=len(ans)<=60 and not any(q.get('atom')==(r,x) for q in qs):
            qs.append({'kind':'list','atom':(r,x),'truth':sorted(ans)})
    return qs


def task_text(facts,qs):
    lines=['# Hechos (padre(a, b): a es padre o madre de b)']+[f'padre({p}, {c})' for p,c in facts]
    lines+=['','# Reglas (la cabeza se cumple si se cumplen todas las condiciones)']+RULES
    lines+=['','# Preguntas']
    for i,q in enumerate(qs):
        if q['kind']=='yesno':
            r,x,y=q['atom']; lines.append(f'Q{i}: ¿Se cumple {r}({x}, {y})? Responde true o false.')
        else:
            r,x=q['atom']; lines.append(f'Q{i}: Lista todos los ?y tales que {r}({x}, ?y).')
    return '\n'.join(lines)+'\n'


def leobot_answers(facts,qs):
    bot=Bot()
    for p,c in facts: bot.kb.add(Atom('padre',(p,c)),'cmp2')
    for i,text in enumerate(RULES):
        head,body=text.split(':-')
        atoms=[Atom.parse(a.strip()+(')' if not a.strip().endswith(')') else '')) for a in body.split('),')]
        bot.kb.add_rule(Rule(f'cmp2_{i}',Atom.parse(head.strip()),tuple(atoms)))
    out=[]; times=[]
    for q in qs:
        started=time.perf_counter()
        if q['kind']=='yesno':
            r,x,y=q['atom']; res=bot.answer_atom(Atom(r,(x,y))); out.append(res.get('status')=='supported')
        else:
            r,x=q['atom']; res=bot.answer_atom(Atom(r,(x,'?y')))
            out.append(sorted({p['atom']['args'][1] for p in res.get('proofs',())}) if res.get('status')=='bindings' else [])
        times.append((time.perf_counter()-started)*1000)
    return out,times


def score(answers,qs):
    yn=[a==q['truth'] for a,q in zip(answers,qs) if q['kind']=='yesno']
    ls=[(set(a or ()),set(q['truth'])) for a,q in zip(answers,qs) if q['kind']=='list']
    exact=[p==g for p,g in ls]
    f1=[2*len(p&g)/max(1,len(p)+len(g)) for p,g in ls]
    return {'yesno_accuracy':round(sum(yn)/len(yn),4),'list_exact':round(sum(exact)/len(exact),4),
            'list_f1':round(sum(f1)/len(f1),4),'mean_exact':round((sum(yn)/len(yn)+sum(exact)/len(exact))/2,4)}


def main():
    facts=world(); qs=questions(facts)
    if sys.argv[1]=='--generate':
        Path(sys.argv[2]).write_text(task_text(facts,qs),encoding='utf8')
        print(len(facts),'hechos',len(qs),'preguntas'); return
    sub=json.loads(Path(sys.argv[2]).read_text(encoding='utf8'))
    sub_answers=[]
    for i,q in enumerate(qs):
        v=sub.get(f'Q{i}')
        if q['kind']=='yesno':
            sub_answers.append(v is True or str(v).lower()=='true')
        else:
            sub_answers.append(sorted(v) if isinstance(v,list) else [])
    tree=subprocess.check_output(('git','rev-parse','HEAD:leobot'),cwd=ROOT,text=True).strip()
    leo,times=leobot_answers(facts,qs)
    result={'kind':'CMP2','engine_tree':tree,'facts':len(facts),'questions':len(qs),
            'leobot':score(leo,qs),'subagent':score(sub_answers,qs),
            'leobot_p95_ms':round(sorted(times)[int(0.95*len(times))-1],3),'leobot_total_ms':round(sum(times),2)}
    (ROOT/'results_v3'/'cmp2_deduction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()

"""CMP-2b / G-36 confirmation: new world seeded from the frozen engine hash.

See prereg/G-36-contradicciones-solo-donde-son-posibles.md.
python3 -m experiments.cmp2b_new_world SUBAGENT_ANSWERS.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

from experiments.cmp2_deduction import world, questions, leobot_answers, score

ROOT=Path(__file__).resolve().parents[1]
CHILD="""
import json,sys
sys.path.insert(0,sys.argv[1]); sys.path.insert(1,sys.argv[2])
import leobot
from experiments.cmp2_deduction import world,questions,leobot_answers,score
f=world(int(sys.argv[3])); q=questions(f,int(sys.argv[4])); a,t=leobot_answers(f,q)
print(json.dumps({'score':score(a,q),'incomplete_lists':0,'engine_path':leobot.__file__}))
"""


def git(*args):
    return subprocess.check_output(('git',*args),cwd=ROOT,text=True).strip()


def main():
    tree=git('rev-parse','HEAD:leobot'); frozen=git('rev-parse','freeze-G-36:leobot')
    ws,qs=int(frozen[:8],16),int(frozen[8:16],16)
    facts=world(ws); qlist=questions(facts,qs)
    leo,times=leobot_answers(facts,qlist)
    sub=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    sub_answers=[(sub.get(f'Q{i}') is True or str(sub.get(f'Q{i}')).lower()=='true') if q['kind']=='yesno'
                 else (sorted(sub.get(f'Q{i}')) if isinstance(sub.get(f'Q{i}'),list) else [])
                 for i,q in enumerate(qlist)]
    with tempfile.TemporaryDirectory() as directory:
        tarfile.open(fileobj=BytesIO(subprocess.check_output(('git','archive','estable-G-5','leobot'),cwd=ROOT))).extractall(directory)
        out=subprocess.run((sys.executable,'-c',CHILD,directory,str(ROOT),str(ws),str(qs)),capture_output=True,text=True,
                           check=True,timeout=600,cwd=directory)
        base=json.loads(out.stdout.strip().splitlines()[-1])
        assert base['engine_path'].startswith(directory)
    result={'kind':'CMP2b_G36','engine_tree':tree,'frozen_tree':frozen,'engine_is_frozen':tree==frozen,
            'world_seed':ws,'question_seed':qs,'facts':len(facts),
            'leobot_frozen':score(leo,qlist),'leobot_estable_G5':base['score'],'subagent':score(sub_answers,qlist),
            'leobot_total_ms':round(sum(times),2),
            'gate_pass':tree==frozen and score(leo,qlist)['mean_exact']==1.0}
    (ROOT/'results_v3'/'cmp2b_g36_new_world.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()

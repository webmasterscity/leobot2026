"""Run the complete unittest suite in bounded, reproducible groups."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT=Path(__file__).resolve().parents[1]


def main():
    modules=[path.stem for path in sorted((ROOT/'tests').glob('test_*.py'))]
    environment=os.environ.copy()
    environment['PYTHONPATH']=os.pathsep.join((str(ROOT/'tests'),str(ROOT),
                                             environment.get('PYTHONPATH','')))
    tests=expected=0;started=time.monotonic()
    for offset in range(0,len(modules),4):
        group=modules[offset:offset+4]
        try:
            result=subprocess.run((sys.executable,'-m','unittest',*group,'-q'),
                                  cwd=ROOT,env=environment,text=True,
                                  capture_output=True,timeout=90,check=False)
        except subprocess.TimeoutExpired as error:
            raise SystemExit(f'Pruebas agotaron 90 s en {group}') from error
        output=result.stdout+'\n'+result.stderr
        if result.returncode:
            print(output,file=sys.stderr)
            raise SystemExit(f'Regresión falló en {group}')
        match=re.search(r'Ran (\d+) tests?',output)
        if not match:
            raise SystemExit(f'Falta el conteo de pruebas en {group}')
        tests+=int(match.group(1))
        extra=re.search(r'expected failures=(\d+)',output)
        expected+=int(extra.group(1)) if extra else 0
        print(f'Lote {offset//4+1}: {len(group)} módulos, {match.group(1)} pruebas',flush=True)
    print(f'Completo: {tests} pruebas, {expected} fallos esperados, '
          f'{time.monotonic()-started:.1f} s; {len(modules)} módulos',flush=True)


if __name__=='__main__':
    main()

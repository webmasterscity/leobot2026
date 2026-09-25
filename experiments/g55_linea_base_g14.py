"""Línea base estable-G-14 (motor freeze-G-54r) en un conjunto: cifras y respuestas. Correr con cwd = worktree wt_g14."""
import sys, json, subprocess
from pathlib import Path
sys.path.insert(0, '.')
assert subprocess.check_output(['git', 'rev-parse', 'HEAD:leobot'], text=True).strip() == '5c6f2d59367562c14b5d9158f9ef1532d8fa5f25'
from experiments.g54_conversacion import medir
from experiments.validacion_comun import conversaciones
conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rep, answers = medir(conversaciones(conjunto), base)
out.write_text(json.dumps({'reporte': rep, 'respuestas': answers}, ensure_ascii=False, indent=1), encoding='utf8')
print(json.dumps(rep, ensure_ascii=False))

"""G-113 (diagnóstico «¿no sabía o no pudo?»): curva de aprendizaje del modelo del kiosco según el número de negocios de enseñanza.

python3 -m experiments.g113_curva_aprendizaje SALIDA.json

Para cada banco nuevo (congelado_g103, congelado_g111, congelado_g112) como evaluación, se enseña el modelo G-112 (denso, umbral por
citas malas) con subconjuntos crecientes de negocios: 54, 108 y 216 de los 9 bancos antiguos (orden fijo por semilla 0) y 216 + los
otros dos bancos nuevos.  Medida: útiles con a lo sumo 0,26 N / 0,39 N / 0,65 N citas malas (como G-111b) y útiles en el punto de
operación.  Diagnóstico: si la curva sigue subiendo al final, falta educación («no sabía»); si se aplana, falta capacidad.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ['congelado', 'congelado_g58', 'congelado_g59', 'congelado_g60', 'congelado_g61', 'congelado_g62', 'congelado_g63',
       'congelado_g64', 'desarrollo']
NEW = ['congelado_g103', 'congelado_g111', 'congelado_g112']


def business_dirs(bank):
    return sorted(p for w in sorted((ROOT / 'results_v3/kiosco' / bank).iterdir()) if w.is_dir()
                  for p in sorted(w.iterdir()) if (p / 'conversaciones.json').exists())


def run(job):
    evaluation, size, teach = job
    with tempfile.TemporaryDirectory(dir=ROOT / '.leobot-data') as tmp:
        # One folder per business, linked, so g112_educar sees exactly this subset.
        folder = Path(tmp) / 'ensenanza'
        for k, business in enumerate(teach):
            target = folder / f'W{k // 40}'
            target.mkdir(parents=True, exist_ok=True)
            (target / f'n{k:03d}').symlink_to(business)
        base = Path(tmp) / 'modelo.json'
        env = {'PYTHONHASHSEED': '0', 'PATH': '/usr/bin:/bin'}
        subprocess.run([sys.executable, '-m', 'experiments.g112_educar', '.leobot-data/base_kiosco_nube.json', str(base),
                        *[str(p) for p in sorted(folder.iterdir())]], cwd=ROOT, env=env, check=True, capture_output=True)
        folders = [str(w) for w in sorted((ROOT / 'results_v3/kiosco' / evaluation).iterdir()) if w.is_dir()]
        out = subprocess.run([sys.executable, '-c', CURVE, str(base), *folders], cwd=ROOT, env=env, check=True,
                             capture_output=True, text=True)
        return {'evaluacion': evaluation, 'negocios': size, **json.loads(out.stdout.strip().splitlines()[-1])}


CURVE = '''
import json, sys
from experiments.g111b_evaluar import points, useful_at
from leobot import Bot
bot = Bot.load(sys.argv[1]); rows = points(bot, sys.argv[2:])
n = sum(r["respondible"] for r in rows)
cite = bot._active_model()["cite_from"]
op_useful = sum(r["util"] for r in rows if r["conf"] >= cite); op_bad = sum(not r["util"] for r in rows if 0 <= r["conf"] and r["conf"] >= cite)
print(json.dumps({"N": n, "u26": useful_at(rows, .26 * n), "u39": useful_at(rows, .39 * n), "u65": useful_at(rows, .65 * n),
                  "operacion": [op_useful, op_bad]}))
'''


def main():
    old = [b for bank in OLD for b in business_dirs(bank)]
    random.Random(0).shuffle(old)
    jobs = []
    for evaluation in NEW:
        others = [b for bank in NEW if bank != evaluation for b in business_dirs(bank)]
        for size in (54, 108, 216):
            jobs.append((evaluation, size, old[:size]))
        jobs.append((evaluation, 216 + len(others), old + others))
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(run, jobs))
    Path(sys.argv[1]).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf8')
    for r in results:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()

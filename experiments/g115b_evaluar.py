"""G-115b, desarrollo: útiles y citas malas en el punto de operación (confianza ≥ `cite_from`), por banco y sumadas en seis bancos
gastados; conteo automático por claves (`g111b_evaluar.points`).

python3 -m experiments.g115b_evaluar SALIDA.json NOMBRE=BASE.json ...
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from experiments.g111b_evaluar import points
from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]
BANKS = ['congelado_g103', 'congelado_g111', 'congelado_g112', 'congelado_g114', 'congelado_g114b', 'congelado_g115']


def run(job):
    name, path, bank = job
    bot = Bot.load(path)
    cite = bot._active_model()['cite_from']
    folders = [str(w) for w in sorted((ROOT / 'results_v3/kiosco' / bank).iterdir()) if w.is_dir()]
    rows = points(bot, folders)
    return name, bank, {'N': sum(r['respondible'] for r in rows),
                        'utiles': sum(r['util'] for r in rows if r['conf'] >= cite),
                        'malas': sum(not r['util'] for r in rows if r['conf'] >= 0 and r['conf'] >= cite), 'cite_from': cite}


def main():
    out = Path(sys.argv[1])
    systems = dict(a.split('=', 1) for a in sys.argv[2:])
    report = {}
    with ProcessPoolExecutor(4) as pool:
        for name, bank, entry in pool.map(run, [(n, p, b) for n, p in systems.items() for b in BANKS]):
            report.setdefault(name, {})[bank] = entry
    for name, banks in report.items():
        banks['total'] = {k: sum(banks[b][k] for b in BANKS) for k in ('N', 'utiles', 'malas')}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    for name, banks in report.items():
        print(name, json.dumps({b: [v['utiles'], v['malas'], v['N']] for b, v in banks.items()}))


if __name__ == '__main__':
    main()

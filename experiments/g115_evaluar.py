"""G-115, selección en desarrollo: útiles con a lo sumo 0,26 N / 0,39 N / 0,65 N citas malas (conteo automático por claves) en los
cinco bancos gastados, por banco y sumados.

python3 -m experiments.g115_evaluar SALIDA.json NOMBRE=BASE.json ...
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from experiments.g111b_evaluar import points, useful_at
from leobot import Bot

ROOT = Path(__file__).resolve().parents[1]
BANKS = ['congelado_g103', 'congelado_g111', 'congelado_g112', 'congelado_g114', 'congelado_g114b']
FRACTIONS = (0.26, 0.39, 0.65)


def run(job):
    name, path, bank = job
    bot = Bot.load(path)
    folders = [str(w) for w in sorted((ROOT / 'results_v3/kiosco' / bank).iterdir()) if w.is_dir()]
    return name, bank, points(bot, folders)


def main():
    out = Path(sys.argv[1])
    systems = dict(a.split('=', 1) for a in sys.argv[2:])
    jobs = [(name, path, bank) for name, path in systems.items() for bank in BANKS]
    rows = {}
    with ProcessPoolExecutor(4) as pool:
        for name, bank, found in pool.map(run, jobs):
            rows.setdefault(name, {})[bank] = found
    report = {}
    for name, banks in rows.items():
        entry = {}
        for bank, found in banks.items():
            n = sum(r['respondible'] for r in found)
            entry[bank] = {'N': n, **{str(f): useful_at(found, f * n) for f in FRACTIONS}}
        pooled = [r for bank in BANKS for r in banks[bank]]
        n = sum(r['respondible'] for r in pooled)
        entry['total'] = {'N': n, **{str(f): useful_at(pooled, f * n) for f in FRACTIONS}}
        report[name] = entry
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    for name, entry in report.items():
        print(name, json.dumps({b: [v['0.26'], v['0.39'], v['0.65'], v['N']] for b, v in entry.items()}))


if __name__ == '__main__':
    main()

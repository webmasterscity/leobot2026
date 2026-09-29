"""G-111: enseñanza de G-103 con pares que aparecen en al menos k negocios distintos.

python3 -m experiments.g111_educar BASE.json SALIDA.json CARPETA... --k 10 [--semilla N]
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault('PAIR_SUPPORT', '3')
os.environ.setdefault('PAIR_KEEP', '0.03')
os.environ.setdefault('C_REG', '0.1')
os.environ.setdefault('EPOCHS', '25')

import experiments.g103_educar as g103  # noqa: E402

K = int(sys.argv[sys.argv.index('--k') + 1])
_businesses, _one_turn, _fit = g103.businesses, g103.one_turn, g103.fit
CURRENT = ['']


def businesses(folders):
    for item in _businesses(folders):
        CURRENT[0] = f'{folders[0]}/{item[0]}'
        yield item


def one_turn(*args, **kwargs):
    record = _one_turn(*args, **kwargs)
    if record is not None:
        record['business'] = CURRENT[0]
    return record


def fit(records, use_pairs=True, seed=0):
    seen: dict = {}
    for r in records:
        for _, pairs, _, _ in r['candidates']:
            for key in set(pairs):
                seen.setdefault(key, set()).add(r['business'])
    wide = {key for key, where in seen.items() if len(where) >= K}
    narrowed = [dict(r, candidates=[(d, [p for p in pairs if p in wide], label, space)
                                    for d, pairs, label, space in r['candidates']]) for r in records]
    return _fit(narrowed, use_pairs, seed)


g103.businesses, g103.one_turn, g103.fit = businesses, one_turn, fit

if __name__ == '__main__':
    k = sys.argv.index('--k')
    sys.argv = ['g111_educar'] + sys.argv[1:k] + sys.argv[k + 2:]
    g103.main()

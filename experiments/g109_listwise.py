"""G-109 (desarrollo): el modelo de utilidad de G-103 enseñado por lista (softmax sobre las candidatas de cada turno).

python3 -m experiments.g109_listwise BASE.json SALIDA.json CARPETA... [--sin-pares]

Mismos rasgos, mismos datos y misma calibración que `g103_educar`; solo cambia el objetivo: en cada turno con alguna candidata
correcta, −log de la probabilidad softmax de las correctas entre las candidatas del mismo espacio (ListNet, Cao et al. 2007).
Los turnos sin respuesta no enseñan orden; la calibración isotónica cruzada decide después cuándo citar.
"""
from __future__ import annotations

import math
import os
import random
import sys

os.environ.setdefault('PAIR_SUPPORT', '3')
os.environ.setdefault('PAIR_KEEP', '0.03')
os.environ.setdefault('C_REG', '0.1')
os.environ.setdefault('EPOCHS', '25')

import experiments.g103_educar as g103  # noqa: E402
from leobot.context import DENSE_FEATURES  # noqa: E402


def fit(records, use_pairs=True, seed=0):
    rows = [(dense, pairs, label) for r in records for dense, pairs, label, _ in r['candidates']]
    n_features = len(DENSE_FEATURES)
    mean = [sum(r[0][j] for r in rows) / len(rows) for j in range(n_features)]
    scale = [math.sqrt(sum((r[0][j] - mean[j]) ** 2 for r in rows) / len(rows)) or 1.0 for j in range(n_features)]
    support: dict = {}
    if use_pairs:
        for _, pairs, _ in rows:
            for key in set(pairs):
                if key.count('|') == 1 and g103.family(key) in g103.FAMILIES:
                    support[key] = support.get(key, 0) + 1
    vocabulary = sorted(k for k, v in support.items() if v >= g103.PAIR_SUPPORT)
    index = {k: j for j, k in enumerate(vocabulary)}
    lists = []
    for r in records:
        for space in (0, 1):
            group = [([(x - m) / s for x, m, s in zip(dense, mean, scale)], [index[k] for k in sorted(set(pairs)) if k in index], label)
                     for dense, pairs, label, sp in r['candidates'] if sp == space]
            if group and any(label for _, _, label in group) and not all(label for _, _, label in group):
                lists.append(group)
    w, v = [0.0] * n_features, [0.0] * len(vocabulary)
    gw, gv = [1e-8] * n_features, [1e-8] * len(vocabulary)
    decay = 1.0 / (g103.C * len(lists))
    rng, order = random.Random(seed), list(range(len(lists)))
    for _ in range(g103.EPOCHS):
        rng.shuffle(order)
        for k in order:
            group = lists[k]
            z = [sum(a * c for a, c in zip(w, dense)) + g103.PAIR_SCALE * sum(v[j] for j in pairs) for dense, pairs, _ in group]
            top = max(z)
            e = [math.exp(x - top) for x in z]
            total = sum(e)
            p = [x / total for x in e]
            gold = sum(label for _, _, label in group)
            for (dense, pairs, label), prob in zip(group, p):
                err = prob - label / gold
                for j in range(n_features):
                    g = err * dense[j] + decay * w[j]
                    gw[j] += g * g
                    w[j] -= g103.ETA * g / math.sqrt(gw[j])
                for j in pairs:
                    g = err * g103.PAIR_SCALE + decay * v[j]
                    gv[j] += g * g
                    v[j] -= g103.ETA * g / math.sqrt(gv[j])
    pairs_weights = {k: round(v[j], 3) for k, j in index.items() if abs(v[j]) >= g103.PAIR_KEEP and k.count('|') == 1 and ';' not in k}
    return {'dense': list(DENSE_FEATURES), 'mean': [round(m, 6) for m in mean], 'scale': [round(s, 6) for s in scale],
            'weights': [round(x, 5) for x in w], 'bias': 0.0, 'pairs': pairs_weights, 'pair_scale': g103.PAIR_SCALE}


g103.fit = fit

if __name__ == '__main__':
    sys.argv = ['g109_listwise'] + sys.argv[1:]
    g103.main()

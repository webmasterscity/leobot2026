"""G-110 (diagnóstico de desarrollo): ¿separa mejor la confianza con la ventaja sobre la segunda candidata?

python3 -m experiments.g110_confianza_margen BASE.json CARPETA_ENSEÑANZA...

Con los registros de enseñanza de G-103 (216 negocios) y modelos cruzados por negocio (5 grupos), para cada turno se toma la
puntuación de la candidata elegida (z1), la de la segunda (z2) y si la elegida es correcta (turnos sin respuesta: nunca).
Compara el AUC (validado por grupos) de z1 sola frente a una logística sobre (z1, z1 − z2).  Solo diagnóstico: no cambia la base.
"""
from __future__ import annotations

import math
import os
import sys

os.environ.setdefault('PAIR_SUPPORT', '3')
os.environ.setdefault('PAIR_KEEP', '0.03')
os.environ.setdefault('C_REG', '0.1')

import experiments.g103_educar as g103  # noqa: E402
from leobot import Bot  # noqa: E402


def auc(points):
    pos = [s for s, y in points if y]
    neg = [s for s, y in points if not y]
    if not pos or not neg:
        return None
    ranked = sorted(points)
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        mid = (i + j + 1) / 2
        rank_sum += mid * sum(1 for k in range(i, j) if ranked[k][1])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def logistic(rows, epochs=200):
    w = [0.0] * (len(rows[0][0]) + 1)
    for _ in range(epochs):
        grad = [0.0] * len(w)
        for x, y in rows:
            z = w[0] + sum(a * b for a, b in zip(w[1:], x))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            grad[0] += p - y
            for k, a in enumerate(x):
                grad[k + 1] += (p - y) * a
        w = [a - 0.5 * g / len(rows) for a, g in zip(w, grad)]
    return w


def main():
    bot = Bot.load(sys.argv[1])
    bot.candidate_model = False
    records = g103.extract(bot, sys.argv[2:])
    turns = []
    for fold in range(g103.FOLDS):
        model = g103.fit([r for r in records if r['group'] != fold], False, 0)
        for r in (r for r in records if r['group'] == fold):
            scored = sorted(((g103.z_of(model, d, p), label) for d, p, label, space in r['candidates'] if space == 0),
                            reverse=True)
            if not scored:
                continue
            z1, label = scored[0]
            z2 = scored[1][0] if len(scored) > 1 else z1 - 5.0
            turns.append((r['group'], z1, z1 - z2, int(label and r['answerable'])))
    base = auc([(z1, y) for _, z1, _, y in turns])
    cross = []
    for fold in range(g103.FOLDS):
        train = [((z1, m), y) for g, z1, m, y in turns if g != fold]
        w = logistic(train)
        cross += [(w[0] + w[1] * z1 + w[2] * m, y) for g, z1, m, y in turns if g == fold]
    print({'turnos': len(turns), 'correctas': sum(t[3] for t in turns), 'auc_z1': round(base, 4),
           'auc_z1_margen': round(auc(cross), 4), 'auc_margen_solo': round(auc([(m, y) for _, _, m, y in turns]), 4)})


if __name__ == '__main__':
    main()

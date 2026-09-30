"""G-112: útiles y citas malas de B0 frente al tratamiento a partir de las filas de `g103_evaluar`, con bootstrap por negocio.

python3 -m experiments.g112_evaluar DIR_EVALUACION  (contiene b0.json y tratamiento.json de g103_evaluar)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

GOOD = ('cita_util', 'correcta')
BAD = ('cita_no_util', 'cita_sin_dato', 'contesto_sin_dato', 'equivocada')


def per_business(rows):
    out = {}
    for r in rows:
        row = out.setdefault(r['negocio'], [0, 0, 0])   # útiles, directas+sí/no, malas
        if r['tipo'] in ('directa', 'si_no'):
            row[1] += 1
            row[0] += r['veredicto'] in GOOD
        row[2] += r['veredicto'] in BAD
    return out


def main():
    folder = Path(sys.argv[1])
    b0 = per_business(json.loads((folder / 'b0.json').read_text(encoding='utf8'))['filas'])
    tr = per_business(json.loads((folder / 'tratamiento.json').read_text(encoding='utf8'))['filas'])
    names = sorted(b0)
    total = lambda table, k, pick=None: sum(table[n][k] for n in (pick or names))
    n = total(b0, 1)
    diff = 100 * (total(tr, 0) - total(b0, 0)) / n
    rng, samples = random.Random(0), []
    for _ in range(10000):
        pick = [rng.choice(names) for _ in names]
        m = total(b0, 1, pick) or 1
        samples.append(100 * (total(tr, 0, pick) - total(b0, 0, pick)) / m)
    samples.sort()
    ci = [round(samples[249], 2), round(samples[9749], 2)]
    report = {'N_directas_si_no': n, 'utiles_b0': total(b0, 0), 'utiles_tratamiento': total(tr, 0), 'diferencia_puntos': round(diff, 2),
              'ic95': ci, 'malas_b0': total(b0, 2), 'malas_tratamiento': total(tr, 2),
              'umbral_1': diff >= 2.0 and ci[0] > 0, 'umbral_2': total(tr, 2) <= 1.10 * total(b0, 2)}
    print(json.dumps(report, ensure_ascii=False))
    (folder / 'g112.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()

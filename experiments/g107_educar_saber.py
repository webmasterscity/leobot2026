"""G-106/G-107: enseña a una base el saber general reunido por `g106_saber_general` (solo datos, métodos públicos).

python3 -m experiments.g107_educar_saber BASE.json SABER.json SALIDA.json [--barajar] [--semilla N]

`--barajar` es el control de señal confundida: dentro de cada relación, los destinos se permutan al azar (mismas palabras, mismas
cantidades, relaciones falsas).
"""
from __future__ import annotations

import json
import random
import resource
import sys
import time
from pathlib import Path

from leobot import Bot


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    seed = int(args.pop()) if '--semilla' in sys.argv else 0
    base, source, out = Path(args[0]), Path(args[1]), Path(args[2])
    t0 = time.process_time()
    bot = Bot.load(base)
    data = json.loads(source.read_text(encoding='utf8'))
    edges = data['relaciones']
    if '--barajar' in sys.argv:
        rng, by_rel = random.Random(seed), {}
        for k, (rel, a, b, src) in enumerate(edges):
            by_rel.setdefault(rel, []).append(k)
        shuffled = list(edges)
        for rel, ks in sorted(by_rel.items()):
            tails = [edges[k][2] for k in ks]
            rng.shuffle(tails)
            for k, tail in zip(ks, tails):
                shuffled[k] = [rel, edges[k][1], tail, edges[k][3]]
        edges = shuffled
    kept = sum(bot.observe_relation(a, rel, b, src) for rel, a, b, src in edges)
    for rel, rows in data['plantillas'].items():
        for template in rows:
            bot.observe_relation_template(rel, template)
    for rel, (closed, paths) in data['cierre'].items():
        bot.observe_relation_closure(rel, closed, paths)
    bot.save(out)
    print(json.dumps({'relaciones_leidas': len(edges), 'guardadas': kept, 'terminos': len(bot.knowledge_model['display']),
                      'encadenadas': sorted(bot._knowledge()['chained']), 'cpu_s': round(time.process_time() - t0, 1),
                      'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                      'bytes': out.stat().st_size}, ensure_ascii=False))


if __name__ == '__main__':
    main()

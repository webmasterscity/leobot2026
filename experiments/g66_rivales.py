"""Prototipo G-66 de aprendizaje lineal por preferencias, fuera del motor.

timeout 1200s python3 -m experiments.g66_rivales BASE MFAQ SALIDA
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from leobot import Bot
from experiments import g65_correspondencias as common

WEIGHTS = (0, .25, .5, 1, 2, 4, 8)


def representation(rows, width):
    qdom, adom = Counter(), Counter()
    domains = defaultdict(lambda: [set(), set()])
    for domain, q, a in rows:
        domains[domain][0].update(common.grams(q, width))
        domains[domain][1].update(common.grams(a, 1))
    for q, a in domains.values():
        qdom.update(q)
        adom.update(a)
    qv = {g: i for i, g in enumerate(sorted(g for g, n in qdom.items() if n >= 5))}
    av = {g: i for i, g in enumerate(sorted(g for g, n in adom.items() if n >= 5))}
    encoded, by_domain = [], defaultdict(list)
    support = [Counter() for _ in qv]
    for domain, q, a in rows:
        qs = tuple(sorted(qv[g] for g in common.grams(q, width) if g in qv))
        ans = tuple(sorted(av[g] for g in common.grams(a, 1) if g in av))
        by_domain[domain].append(len(encoded))
        encoded.append((qs, ans))
        for x in qs:
            support[x].update(ans)
    candidates, threshold = sum(map(len, support)), 1
    while sum(sum(n >= threshold for n in row.values()) for row in support) > common.LIMIT:
        threshold += 1
    allowed = [tuple(sorted(a for a, n in row.items() if n >= threshold)) for row in support]
    return qv, av, encoded, by_domain, allowed, {'candidates': candidates, 'minimum_count': threshold}


def train(representation, width, seed):
    qv, av, encoded, by_domain, allowed, stats = representation
    prob = [{a: 0. for a in row} for row in allowed]
    summed = [{a: 0. for a in row} for row in allowed]
    rng, reports = random.Random(seed), []
    start = time.process_time()
    for epoch in range(5):
        begin = time.process_time()
        negatives = {}
        for _, indices in sorted(by_domain.items()):
            if len(indices) < 2:
                continue
            shift = rng.randrange(1, len(indices))
            negatives.update({index: indices[(i+shift) % len(indices)] for i, index in enumerate(indices)})
        order = sorted(negatives)
        rng.shuffle(order)
        mistakes, loss_total = 0, 0.
        for index in order:
            qs, pos = encoded[index]
            _, neg = encoded[negatives[index]]
            differences = {a: 1/math.sqrt(len(pos)) for a in pos}
            if neg:
                scale = 1/math.sqrt(len(neg))
                for a in neg:
                    differences[a] = differences.get(a, 0.)-scale
            features = [(q, a, value) for q in qs for a, value in sorted(differences.items())
                        if value and a in prob[q]]
            norm = sum(value*value for _, _, value in features)
            if not norm:
                continue
            loss = 1 - sum(prob[q][a]*value for q, a, value in features)
            if loss > 0:
                mistakes += 1
                loss_total += loss
                step = min(1., loss/norm)
                for q, a, value in features:
                    prob[q][a] += step*value
        for q, row in enumerate(prob):
            for a, value in row.items():
                summed[q][a] += value/5
        reports.append({'epoch': epoch+1, 'updates': mistakes, 'loss': loss_total,
                        'cpu_s': time.process_time()-begin})
    return {'qv': qv, 'av': av, 'prob': summed, 'width': width}, {
        **stats, 'examples': len(encoded), 'associations': sum(map(len, prob)), 'seed': seed,
        'rounds': reports, 'cpu_s': time.process_time()-start}


def linear_scores(model, units, terms):
    qs = [model['qv'][g] for g in sorted(common.grams(terms, model['width'])) if g in model['qv']]
    rows = [model['prob'][q] for q in qs]
    return [sum(row.get(a, 0.) for row in rows for a in ans)/math.sqrt(max(1, len(ans))) for ans in units]


def main():
    base, corpus, output = map(Path, sys.argv[1:4])
    git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
    before = git('rev-parse', 'HEAD:leobot')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor sin congelar')
    start = time.process_time()
    bot = Bot.load(base)
    examples = common.examples(bot, corpus)
    report = {'engine': before, 'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
              'acquisition_cpu_s': time.process_time()-start, 'models': {}}
    root = Path('results_v3/kiosco')
    fitting = [root/'desarrollo'/letter for letter in 'ABCD']
    separate = [root/'desarrollo'/letter for letter in 'EF'] + sorted((root/'congelado_g59').glob('X*')) \
        + sorted((root/'congelado_g60').glob('Y*'))
    # Reuse the fixed evaluator; only the explicitly supplied model scoring differs.
    common.alignment_scores, common.WEIGHTS = linear_scores, WEIGHTS
    for width, name in ((1, 'words'), (2, 'phrases')):
        begin = time.process_time()
        data = representation(examples, width)
        report[name+'_representation_cpu_s'] = time.process_time()-begin
        for seed in (0, 1, 2):
            model, cost = train(data, width, seed)
            begin = time.process_time()
            fit_rows = common.evaluate(bot, {name: model}, fitting)
            separate_rows = common.evaluate(bot, {name: model}, separate)
            result = {'cost': cost, 'fit': common.summarize(fit_rows),
                      'separate': common.summarize(separate_rows), 'validation_cpu_s': time.process_time()-begin}
            report['models'][f'{name}_{seed}'] = result
            print(name, seed, json.dumps(result), flush=True)
        del data
    report['selected'] = {}
    for name in ('words', 'phrases'):
        models = [report['models'][f'{name}_{seed}'] for seed in (0, 1, 2)]
        weight = max(WEIGHTS, key=lambda w: (sum(m['fit']['models'][name]['correct'][str(w)] for m in models), -w))
        hits = [m['separate']['models'][name]['correct'][str(weight)] for m in models]
        n, baseline = models[0]['separate']['n'], models[0]['separate']['baseline']
        report['selected'][name] = {'weight': weight, 'hits': hits, 'n': n, 'baseline': baseline,
                                    'gate': sum(hits)/3/n >= .6 and (sum(hits)/3-baseline)/n >= .05
                                    and min(hits) >= baseline}
    report['phrase_retention'] = (sum(report['selected']['phrases']['hits'])-
                                  sum(report['selected']['words']['hits']))/3/n >= .02
    report['cpu_s'] = time.process_time()-start
    report['rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    report['engine_after'] = git('rev-parse', 'HEAD:leobot')
    report['engine_unchanged'] = before == report['engine_after'] and not git('status', '--porcelain', '--', 'leobot')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'selected': report['selected'], 'phrase_retention': report['phrase_retention'],
                      'cpu_s': report['cpu_s'], 'rss_mib': report['rss_mib']}), flush=True)


if __name__ == '__main__':
    main()

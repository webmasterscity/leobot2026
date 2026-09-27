"""G-67: selección latente de evidencia humana; no modifica el motor."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from leobot import Bot
from experiments import g65_correspondencias as align
from experiments import g66_rivales as rank
from experiments.g57_educar_kiosco import MFAQ_SHA, calibration_domain, spanish_pairs


def selected_examples(bot, path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != MFAQ_SHA:
        raise ValueError('Fuente alterada')
    rng, reservoir, seen = random.Random(57), {}, Counter()
    with path.open() as stream:
        for line in stream:
            page = json.loads(line)
            domain = page.get('domain') or ''
            if calibration_domain(domain):
                continue
            box = reservoir.setdefault(domain, [])
            for pair in spanish_pairs(page):
                seen[domain] += 1
                if len(box) < 100:
                    box.append(pair)
                else:
                    j = rng.randrange(seen[domain])
                    if j < 100:
                        box[j] = pair
    unique, rows = set(), []
    stats = {'sampled': 0, 'no_unit': 0, 'tokens_before': 0, 'tokens_after': 0}
    for domain, pairs in sorted(reservoir.items()):
        for question, answer in pairs:
            stats['sampled'] += 1
            q = tuple(bot.context_terms(question))
            bot.load_context(answer)
            chosen = bot._rank(list(q), question)
            if not chosen:
                stats['no_unit'] += 1
                continue
            text = bot.context_units[chosen['unit']]['text']
            a = tuple(bot.context_terms(text))
            stats['tokens_before'] += len(bot.context_terms(answer))
            stats['tokens_after'] += len(a)
            if q and a and (q, a) not in unique:
                rows.append((domain, q, a))
                unique.add((q, a))
    stats['examples'] = len(rows)
    return rows, stats


def main():
    base, corpus, output = map(Path, sys.argv[1:4])
    git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
    before = git('rev-parse', 'HEAD:leobot')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor sin congelar')
    start = time.process_time()
    bot = Bot.load(base)
    rows, counts = selected_examples(bot, corpus)
    report = {'engine': before, 'source_sha256': MFAQ_SHA,
              'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
              'preparation': {**counts, 'cpu_s': time.process_time()-start}, 'models': {}}
    print('preparation', json.dumps(report['preparation']), flush=True)
    root = Path('results_v3/kiosco')
    fitting = [root/'desarrollo'/letter for letter in 'ABCD']
    separate = [root/'desarrollo'/letter for letter in 'EF'] + sorted((root/'congelado_g59').glob('X*')) \
        + sorted((root/'congelado_g60').glob('Y*'))

    def assess(name, model, costs):
        begin = time.process_time()
        fit = align.summarize(align.evaluate(bot, {name: model}, fitting))
        other = align.summarize(align.evaluate(bot, {name: model}, separate))
        result = {'fit': fit, 'separate': other, 'cost': costs, 'validation_cpu_s': time.process_time()-begin}
        report['models'][name] = result
        print(name, json.dumps(result), flush=True)

    for width in (1, 2):
        model, cost = align.train(rows, width)
        assess(f'align_{width}', model, cost)
    align.alignment_scores, align.WEIGHTS = rank.linear_scores, rank.WEIGHTS
    begin = time.process_time()
    encoded = rank.representation(rows, 1)
    report['rank_representation_cpu_s'] = time.process_time()-begin
    for seed in (0, 1, 2):
        model, cost = rank.train(encoded, 1, seed)
        assess(f'rank_{seed}', model, cost)
    report['selected'] = {}
    for name in ('align_1', 'align_2'):
        measured = report['models'][name]
        by_weight = measured['fit']['models'][name]['correct']
        weight = max(by_weight, key=lambda w: (by_weight[w], -float(w)))
        n, baseline = measured['separate']['n'], measured['separate']['baseline']
        hits = measured['separate']['models'][name]['correct'][weight]
        report['selected'][name] = {'weight': weight, 'hits': hits, 'n': n,
                                    'gate': hits/n >= .6 and (hits-baseline)/n >= .05}
    models = [(f'rank_{s}', report['models'][f'rank_{s}']) for s in (0, 1, 2)]
    weight = max(rank.WEIGHTS, key=lambda w: (sum(m['fit']['models'][name]['correct'][str(w)] for name, m in models), -w))
    hits = [m['separate']['models'][name]['correct'][str(weight)] for name, m in models]
    report['selected']['rank'] = {'weight': weight, 'hits': hits, 'n': n,
                                  'gate': sum(hits)/3/n >= .6 and (sum(hits)/3-baseline)/n >= .05
                                  and min(hits) >= baseline}
    report['cpu_s'] = time.process_time()-start
    report['rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    report['engine_after'] = git('rev-parse', 'HEAD:leobot')
    report['engine_unchanged'] = before == report['engine_after'] and not git('status', '--porcelain', '--', 'leobot')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'selected': report['selected'], 'cpu_s': report['cpu_s'], 'rss_mib': report['rss_mib']}), flush=True)


if __name__ == '__main__':
    main()

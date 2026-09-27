"""Prototipo descartable G-65; no es importado por el motor.

Uso: timeout 1200s python3 -m experiments.g65_correspondencias BASE MFAQ SALIDA
No enseña con bancos del kiosco: estos solo comparan la selección de unidades.
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
from experiments.g57_educar_kiosco import MFAQ_SHA, calibration_domain, spanish_pairs
from experiments.g57_kiosco import businesses, contains

WEIGHTS = (0, .25, .5, 1, 2)
LIMIT = 2_000_000


def grams(words, width):
    return {tuple(words[i:i+n]) for n in range(1, width+1)
            for i in range(len(words)-n+1)}


def examples(bot, path, *, raw=False):
    if hashlib.sha256(path.read_bytes()).hexdigest() != MFAQ_SHA:
        raise ValueError('MFAQ no coincide con la fuente registrada')
    reservoir, seen = {}, Counter()
    rng = random.Random(57)
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
    for domain, pairs in sorted(reservoir.items()):
        for question, answer in pairs:
            q, a = tuple(bot.context_terms(question)), tuple(bot.context_terms(answer))
            if q and a and (q, a) not in unique:
                rows.append((domain, question, answer) if raw else (domain, q, a))
                unique.add((q, a))
    return rows


def train(rows, width):
    started = time.process_time()
    qdom, adom = Counter(), Counter()
    domains = defaultdict(lambda: [set(), set()])
    for domain, q, a in rows:
        domains[domain][0].update(grams(q, width))
        domains[domain][1].update(grams(a, width))
    for q, a in domains.values():
        qdom.update(q)
        adom.update(a)
    del domains
    qv = {q: i for i, q in enumerate(sorted(q for q, n in qdom.items() if n >= 5))}
    av = {a: i for i, a in enumerate(sorted(a for a, n in adom.items() if n >= 5))}
    encoded = [(tuple(sorted(qv[g] for g in grams(q, width) if g in qv)),
                tuple(sorted(av[g] for g in grams(a, width) if g in av))) for _, q, a in rows]
    pairs = [Counter() for _ in qv]
    qcount = Counter()
    for qs, ans in encoded:
        qcount.update(qs)
        for q in qs:
            pairs[q].update(ans)
    candidates = sum(map(len, pairs))
    # Explicit resource bound. Keep strongest repeated pairs deterministically.
    threshold = 1
    while sum(sum(n >= threshold for n in row.values()) for row in pairs) > LIMIT:
        threshold += 1
    prob = [{a: 1.0 for a, n in sorted(row.items()) if n >= threshold} for row in pairs]
    del pairs
    sizes = Counter(a for row in prob for a in row)
    for row in prob:
        for a in row:
            row[a] /= sizes[a]
    background = {q: n / sum(qcount.values()) for q, n in qcount.items()}
    setup_cpu = time.process_time() - started
    rounds = []
    for _ in range(5):
        begin = time.process_time()
        counts = [defaultdict(float) for _ in prob]
        totals = [0.] * len(av)
        for qs, ans in encoded:
            for q in qs:
                row = prob[q]
                found = [(a, row[a]) for a in ans if a in row]
                # A learned background channel lets unaligned words remain unexplained.
                den = sum(p for _, p in found) + background[q]
                for a, p in found:
                    value = p / den
                    counts[q][a] += value
                    totals[a] += value
        prob = [{a: n / totals[a] for a, n in sorted(row.items())} for row in counts]
        rounds.append(time.process_time() - begin)
    elapsed = time.process_time() - started
    return {'qv': qv, 'av': av, 'prob': prob, 'background': background, 'width': width}, {
        'examples': len(rows), 'q_features': len(qv), 'a_features': len(av),
        'candidates': candidates, 'kept': sum(map(len, prob)), 'minimum_pair_count': threshold,
        'setup_cpu_s': setup_cpu, 'rounds_cpu_s': rounds, 'total_cpu_s': elapsed}


def baseline_scores(bot, terms, question):
    """Same scores as ContextMixin._rank, all candidates, for mixture only."""
    units, postings = bot.context_units, bot._index()
    total, title, bridge = len(units), set(bot.context_title), bot._bridge()
    base, gains = 0., {}
    for q in dict.fromkeys(terms):
        delta = min(max(bot._delta(q), 0.), 1 - 1e-4)
        p0 = (len(postings.get(q, ())) + .5) / (total + 1)
        absent = 0. if q in title else math.log(1-delta)
        base += absent
        best = {i: math.log(delta / p0 + 1-delta) - absent for i in postings.get(q, ())}
        for a, d in bridge.get(q, ()):
            p0 = (len(postings.get(a, ())) + .5) / (total+1)
            gain = math.log(d / p0 + 1-d)
            for i in postings.get(a, ()):
                best[i] = max(best.get(i, -math.inf), gain)
        for i, gain in best.items():
            gains[i] = gains.get(i, 0.) + gain
    asked = bot._asked_class(question)
    if asked:
        cls, share = asked
        share = min(share, 1-1e-4)
        having = [i for i, u in enumerate(units) if cls in u.get('classes', ())
                  and u['kind'] not in ('question', 'heading')]
        p0, absent = (len(having)+.5)/(total+1), math.log(1-share)
        base += absent
        for i in having:
            gains[i] = gains.get(i, 0.) + math.log(share / p0+1-share)-absent
    return [base+gains.get(i, 0.) for i in range(total)]


def prepared_units(bot, model):
    av, width = model['av'], model['width']
    prepared = []
    for u in bot.context_units:
        text = u['text'] + (' '+u['heading'] if u.get('inherited') else '')
        prepared.append([av[g] for g in sorted(grams(bot.context_terms(text), width)) if g in av])
    return prepared


def alignment_scores(model, units, terms):
    qs = [model['qv'][g] for g in sorted(grams(terms, model['width'])) if g in model['qv']]
    out = []
    for ans in units:
        total = 0.
        for q in qs:
            row, bg = model['prob'][q], model['background'][q]
            translated = sum(row.get(a, 0.) for a in ans) / max(1, len(ans))
            total += math.log(.5 + .5 * translated / bg)
        out.append(total)
    return out


def evaluate(bot, models, folders):
    result = []
    for name, text, instructions, conversations in businesses(folders):
        bot.load_context(text, instructions)
        if not bot.context_units:
            continue
        prepared = {key: prepared_units(bot, model) for key, model in models.items()}
        for conversation in conversations:
            for turn in conversation:
                if turn.get('accion') != 'responder' or turn.get('tipo') not in ('directa', 'si_no'):
                    continue
                keys = turn.get('claves') or []
                if not keys:
                    continue
                _, question = bot._question_part(turn['cliente'])
                terms = bot.context_terms(question)
                scores = baseline_scores(bot, terms, question)
                rank = bot._rank(terms, question)
                baseline = rank['unit']
                ours = max(range(len(scores)), key=lambda i: (scores[i], -i))
                if ours != baseline:
                    raise AssertionError('El control no reproduce la selección de la base')
                good = [all(contains(u['text'], key) for key in keys) for u in bot.context_units]
                row = {'business': name, 'ceiling': any(good), 'baseline': good[baseline], 'models': {}}
                for key, model in models.items():
                    start = time.perf_counter()
                    added = alignment_scores(model, prepared[key], terms)
                    choices = {}
                    for weight in WEIGHTS:
                        index = max((i for i, u in enumerate(bot.context_units) if u['kind'] != 'question'),
                                    key=lambda i: (scores[i]+weight*added[i], -i))
                        choices[str(weight)] = good[index]
                    row['models'][key] = {'choices': choices, 'ms': 1000*(time.perf_counter()-start)}
                result.append(row)
    return result


def summarize(rows):
    out = {'n': len(rows), 'ceiling': sum(r['ceiling'] for r in rows),
           'baseline': sum(r['baseline'] for r in rows), 'models': {}}
    for model in rows[0]['models'] if rows else ():
        times = sorted(r['models'][model]['ms'] for r in rows)
        out['models'][model] = {'correct': {str(w): sum(r['models'][model]['choices'][str(w)] for r in rows)
                                          for w in WEIGHTS},
                                'p50_ms': times[len(times)//2], 'p95_ms': times[int(.95*len(times))]}
    return out


def main():
    base, corpus, output = map(Path, sys.argv[1:4])
    git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
    before = git('rev-parse', 'HEAD:leobot')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor sin congelar')
    started = time.process_time()
    bot = Bot.load(base)
    rows = examples(bot, corpus)
    acquisition = time.process_time()-started
    report = {'engine': before, 'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
              'acquisition_cpu_s': acquisition, 'training': {}}
    models = {}
    for width, name in ((1, 'words'), (2, 'phrases')):
        models[name], report['training'][name] = train(rows, width)
        print(name, json.dumps(report['training'][name]), flush=True)
    validation = time.process_time()
    root = Path('results_v3/kiosco')
    fitting = evaluate(bot, models, [root/'desarrollo'/letter for letter in 'ABCD'])
    separate = evaluate(bot, models, [root/'desarrollo'/letter for letter in 'EF'] +
                        sorted((root/'congelado_g59').glob('X*')) + sorted((root/'congelado_g60').glob('Y*')))
    report['fit'], report['separate'] = summarize(fitting), summarize(separate)
    chosen = {name: max(WEIGHTS, key=lambda w: (report['fit']['models'][name]['correct'][str(w)], -w))
              for name in models}
    report['chosen_weights'] = chosen
    n, base_n = report['separate']['n'], report['separate']['baseline']
    chosen_hits = {m: report['separate']['models'][m]['correct'][str(w)] for m, w in chosen.items()}
    report['chosen_hits'] = chosen_hits
    report['development_gate'] = {m: hits/n >= .6 and (hits-base_n)/n >= .05 for m, hits in chosen_hits.items()}
    report['phrase_retention'] = (chosen_hits['phrases']-chosen_hits['words'])/n >= .02
    report['validation_cpu_s'] = time.process_time()-validation
    report['total_cpu_s'] = time.process_time()-started
    report['rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    report['engine_after'] = git('rev-parse', 'HEAD:leobot')
    report['engine_unchanged'] = before == report['engine_after'] and not git('status', '--porcelain', '--', 'leobot')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

"""G76: paired multinomial mixtures, no neural models or stored QA responses."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import resource
import subprocess
import time

from leobot import Bot
from experiments.g65_correspondencias import examples
from experiments.g68_confianza import TRAIN, DEV, collect, collect_context, metrics
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import (
    RelationalRanker, fit_confidence, public_measure, WEIGHTS, check_budget, training_contexts,
)

FIELDS = ('topic_score', 'topic_margin', 'topic_known')


def softmax(values):
    high = max(values)
    weights = [math.exp(v-high) for v in values]
    total = sum(weights)
    return [v/total for v in weights], high+math.log(total)


def posterior(model, ids, side):
    values = [math.log(p) for p in model['prior']]
    for i in ids:
        for k, value in enumerate(model[side][i]):
            values[k] += value
    return softmax(values)[0]


def match(model, query, answer):
    q = posterior(model, query, 'qlog')
    a = posterior(model, answer, 'alog')
    return math.log(sum(x*y/p for x, y, p in zip(q, a, model['prior'])))


def parameters(qcounts, acounts, totals):
    prior = [n/sum(totals) for n in totals]
    model = {'prior': prior}
    for side, counts in (('qlog', qcounts), ('alog', acounts)):
        den = [sum(col[k] for col in counts) for k in range(len(prior))]
        model[side] = [[math.log(value/den[k]) for k, value in enumerate(col)] for col in counts]
    return model


def train(rows, qsize, asize, *, seed, groups=32, rounds=12, deadline=None):
    begin = time.process_time()
    rng = random.Random(seed)
    qcounts, acounts = [[.1]*groups for _ in range(qsize)], [[.1]*groups for _ in range(asize)]
    totals = [1.]*groups
    for qs, ans in rows:
        k = rng.randrange(groups)
        totals[k] += 1
        for i in qs:
            qcounts[i][k] += 1
        for i in ans:
            acounts[i][k] += 1
    model = parameters(qcounts, acounts, totals)
    trace = []
    for iteration in range(rounds):
        if deadline is not None and time.process_time() > deadline:
            raise TimeoutError('G76 enseñanza agotó presupuesto')
        start = time.process_time()
        qcounts, acounts = [[.1]*groups for _ in range(qsize)], [[.1]*groups for _ in range(asize)]
        totals = [1.]*groups
        logs = [math.log(p) for p in model['prior']]
        likelihood = 0.
        for qs, ans in rows:
            values = logs.copy()
            for side, ids in (('qlog', qs), ('alog', ans)):
                for i in ids:
                    for k, value in enumerate(model[side][i]):
                        values[k] += value
            responsibility, ll = softmax(values)
            likelihood += ll
            for k, r in enumerate(responsibility):
                totals[k] += r
            for counts, ids in ((qcounts, qs), (acounts, ans)):
                for i in ids:
                    for k, r in enumerate(responsibility):
                        counts[i][k] += r
        model = parameters(qcounts, acounts, totals)
        trace.append({'round': iteration+1, 'log_likelihood': likelihood,
                      'cpu_s': time.process_time()-start})
        if len(rows) > 100 and (iteration+1) % 4 == 0:
            print(json.dumps({'stage': 'education', 'seed': seed, 'round': iteration+1,
                              'cpu_s': time.process_time()-begin}), flush=True)
    return model, {'seed': seed, 'groups': groups, 'pairs': len(rows), 'rounds': trace,
                   'cpu_s': time.process_time()-begin}


def teaching_pairs(bot, *, with_domains=False):
    sampled = examples(bot, ROOT / '.leobot-data/mfaq_es_train.jsonl')
    eligible = [(domain, q, a) for domain, q, a in sampled if len(q) <= 24 and len(a) <= 64]
    rows = sorted(eligible, key=lambda row: sha256(json.dumps(row, ensure_ascii=False).encode()).digest())[:4000]
    support = defaultdict(lambda: [set(), set()])
    for domain, q, a in rows:
        support[domain][0].update(q)
        support[domain][1].update(a)
    qdom, adom = Counter(), Counter()
    for q, a in support.values():
        qdom.update(q)
        adom.update(a)
    qv = {w: i for i, w in enumerate(sorted(w for w, n in qdom.items() if n >= 5))}
    av = {w: i for i, w in enumerate(sorted(w for w, n in adom.items() if n >= 5))}
    encoded = [(sorted({qv[w] for w in q if w in qv}), sorted({av[w] for w in a if w in av}))
               for _, q, a in rows]
    per_domain = defaultdict(list)
    for i, (domain, _, _) in enumerate(rows):
        per_domain[domain].append(i)
    permuted = list(encoded)
    rng = random.Random(76)
    for domain, indices in sorted(per_domain.items()):
        answers = [encoded[i][1] for i in indices]
        rng.shuffle(answers)
        for i, answer in zip(indices, answers):
            permuted[i] = encoded[i][0], answer
    report = {'sampled': len(sampled), 'eligible': len(eligible), 'pairs': len(rows),
              'domains': len(per_domain), 'q_vocabulary': len(qv), 'a_vocabulary': len(av),
              'empty_q': sum(not q for q, _ in encoded), 'empty_a': sum(not a for _, a in encoded),
              'shuffled_changed': sum(a != b for (_, a), (_, b) in zip(encoded, permuted))}
    result = (qv, av, encoded, permuted, report)
    return (*result, [domain for domain, _, _ in rows]) if with_domains else result


class TopicRanker(RelationalRanker):
    feature_fields = FIELDS

    def __init__(self, bot, bundle, weight=1.):
        self.bundle = bundle
        super().__init__(bot, {}, {}, weight=weight)

    def load(self, *args, **kwargs):
        result = self.original_load(*args, **kwargs)
        self.prepare_units()
        return result

    def project(self, model, ids, side):
        return posterior(model, ids, side)

    def prepare_units(self):
        start = time.process_time()
        self.prepared, self.units, self.query_cache, self.analyses = [], [], {}, {}
        self.unit_topics = []
        for unit in self.bot.context_units:
            terms = set(self.bot.context_terms(unit['text'])) | set(unit.get('inherited', ()))
            ids = sorted({self.bundle['av'][w] for w in terms if w in self.bundle['av']})
            self.prepared.append((terms, {}))
            self.unit_topics.append([self.project(m, ids, 'alog') for m in self.bundle['models']]
                                   if ids and self.weight else None)
        self.preparation_cpu += time.process_time()-start

    def evidence(self, question, terms):
        ids = sorted({self.bundle['qv'][w] for w in terms if w in self.bundle['qv']})
        if not ids:
            return {}
        coverage = sum(w in self.bundle['qv'] for w in set(terms))/max(1, len(set(terms)))
        query = [self.project(model, ids, 'qlog') for model in self.bundle['models']]
        scores = {}
        for i, answers in enumerate(self.unit_topics):
            if answers is not None:
                values = [math.log(max(1e-300, sum(q*a/p for q, a, p in zip(qs, ans, model['prior']))))
                          for qs, ans, model in zip(query, answers, self.bundle['models'])]
                scores[i] = sum(values)/len(values)
        # Margin among topical hypotheses is a confidence input, not a threshold.
        ordered = sorted(scores.values(), reverse=True)
        return {i: (value, value, value-(ordered[1] if value == ordered[0] and len(ordered) > 1
                                       else ordered[0]), coverage) for i, value in scores.items()}


def fingerprint(extra=()):
    files = ('experiments/g76_paired_groups.py', 'experiments/g75_relational_evidence.py',
             'experiments/g65_correspondencias.py', 'experiments/g68_confianza.py',
             'prereg/G-76-grupos-de-preguntas-y-respuestas.md') + tuple(extra)
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G76 motor o prototipo sin congelar')
    return {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in files}


def collect_weights(bot, ranker, *, contexts=None, deadline=None):
    rows = {weight: [] for weight in WEIGHTS}
    bot.calibrated, bot.closest = False, False
    for n, (group, text, instructions, conversations) in enumerate(
            training_contexts() if contexts is None else contexts, 1):
        check_budget(deadline)
        ranker.weight = 1.
        bot.load_context(text, instructions)
        for weight in WEIGHTS:
            ranker.weight = weight
            rows[weight].extend(collect_context(bot, group, conversations))
        if n % 35 == 0:
            print(json.dumps({'stage': 'training_contexts', 'n': n}), flush=True)
    return rows


def main(*, producer=None, ranker_type=TopicRanker, experiment='G76',
         validation_seconds=150, extra_sources=(), reuse_training_contexts=False):
    resource.setrlimit(resource.RLIMIT_CPU, (605+validation_seconds, 610+validation_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes = fingerprint(extra_sources)
    start_cpu, start_wall = time.process_time(), time.monotonic()
    base = ROOT / '.leobot-data/base_kiosco.json'
    if sha256(base.read_bytes()).hexdigest() != BASE_SHA:
        raise RuntimeError('G76 base distinta')
    bot = Bot.load(base)
    model_path = ROOT / f'.leobot-data/{experiment.lower()}_models.json'
    if producer is None:
        qv, av, pairs, permuted, teaching = teaching_pairs(bot)
        acquisition = time.process_time()-start_cpu
        seed0 = int(ENGINE[:8], 16)
        bundles, learning = {}, {}
        for mode, data in (('full', pairs), ('shuffled', permuted)):
            bundles[mode] = {'qv': qv, 'av': av, 'models': []}
            learning[mode] = []
            for offset in range(3):
                model, report = train(data, len(qv), len(av), seed=seed0+offset, deadline=start_cpu+600)
                bundles[mode]['models'].append(model)
                learning[mode].append(report)
                model_path.write_text(json.dumps({'models': bundles, 'learning': learning,
                                                 'teaching': teaching, 'sources_sha256': hashes}, ensure_ascii=False))
                print(json.dumps({'stage': 'learned', 'mode': mode, 'seed': seed0+offset,
                                  'cpu_s': report['cpu_s']}), flush=True)
    else:
        bundles, learning, teaching, acquisition = producer(bot, start_cpu, hashes, model_path)
    teaching_cpu = time.process_time()-start_cpu
    deadline = time.process_time()+validation_seconds
    t = time.process_time()
    baseline_rows = collect(bot, TRAIN)
    baseline_fit = metrics(baseline_rows, [r['baseline_p'] for r in baseline_rows])
    baseline = public_measure(bot, deadline=deadline)
    assert (baseline['useful_core'], baseline['quotes_without_data']) == (269, 74)
    choices, confidence, fitted = {}, {}, {}
    for mode, bundle in bundles.items():
        ranker = ranker_type(bot, bundle)
        best = (baseline_fit['useful_core'], -baseline_fit['quotes_without_data'], 0.)
        choices[mode], confidence[mode], fitted[mode] = 0., None, {}
        shared = collect_weights(bot, ranker, deadline=deadline) if reuse_training_contexts else None
        for weight in WEIGHTS:
            check_budget(deadline)
            ranker.weight = weight
            rows = shared[weight] if shared is not None else collect(bot, TRAIN)
            learned, probabilities = fit_confidence(rows, FIELDS)
            result = metrics(rows, probabilities)
            fitted[mode][str(weight)] = result
            candidate = (result['useful_core'], -result['quotes_without_data'], -weight)
            if learned is not None and result['quotes_without_data'] <= baseline_fit['quotes_without_data'] and candidate > best:
                best, choices[mode], confidence[mode] = candidate, weight, learned
            print(json.dumps({'stage': 'selection', 'mode': mode, 'weight': weight,
                              'useful': result['useful_core'], 'absent_quotes': result['quotes_without_data']}), flush=True)
        ranker.restore()
    selection_cpu = time.process_time()-t
    t = time.process_time()
    results, details, raw, seed_results = {}, {}, {}, []
    for mode, bundle in bundles.items():
        ranker = ranker_type(bot, bundle, weight=choices[mode])
        ranker.confidence = confidence[mode]
        results[mode] = public_measure(bot, ranker, deadline=deadline)
        raw_rows = collect(bot, DEV)
        raw[mode] = {'core': sum(r['core'] for r in raw_rows),
                     'correct_first': sum(r['core'] and r['y'] for r in raw_rows)}
        details[mode] = {'stats': dict(ranker.stats), 'load_preparation_cpu_s': ranker.preparation_cpu}
        ranker.restore()
        print(json.dumps({'stage': 'measured', 'mode': mode, 'results': results[mode],
                          'raw': raw[mode], 'weight': choices[mode]}), flush=True)
    saved = {'models': bundles, 'choices': choices, 'confidence': confidence,
             'learning': learning, 'teaching': teaching, 'sources_sha256': hashes}
    model_path.write_text(json.dumps(saved, ensure_ascii=False))
    saved = json.loads(model_path.read_text())
    replay = ranker_type(bot, saved['models']['full'], weight=saved['choices']['full'])
    replay.confidence = saved['confidence']['full']
    restored = public_measure(bot, replay, deadline=deadline)
    replay.restore()
    zero = ranker_type(bot, bundles['full'], weight=0.)
    unmodified = public_measure(bot, zero, deadline=deadline)
    zero.restore()
    for model in bundles['full']['models']:
        ranker = ranker_type(bot, {**bundles['full'], 'models': [model]}, weight=choices['full'])
        ranker.confidence = confidence['full']
        seed_results.append(public_measure(bot, ranker, deadline=deadline))
        ranker.restore()
    controls = {'reload_exact': restored['response_sha256'] == results['full']['response_sha256'],
                'disabled_exact': unmodified['response_sha256'] == baseline['response_sha256']}
    primary = results['full']
    evaluation_cpu = time.process_time()-t
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    gates = {'gain': primary['useful_core'] >= baseline['useful_core']+.05*baseline['core'],
             'shuffled_gain': primary['useful_core'] >= results['shuffled']['useful_core']+.02*baseline['core'],
             'absent': primary['quotes_without_data'] <= baseline['quotes_without_data'],
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'controls': all(controls.values()), 'literal': primary['nonliteral_evidence'] == 0,
             'budget': teaching_cpu <= 600 and selection_cpu+evaluation_cpu <= validation_seconds
                       and rss <= 1024**2 and time.monotonic()-start_wall <= 700+2*validation_seconds}
    if 'global' in results:
        gates['background_gain'] = primary['useful_core'] >= results['global']['useful_core']+.02*baseline['core']
    assert fingerprint(extra_sources) == hashes
    report = {'experiment': experiment, 'scope': 'spent development, external prototype, no promotion',
              'engine_sha': ENGINE, 'engine_unchanged': True, 'base_sha256': BASE_SHA,
              'sources_sha256': hashes, 'teaching': teaching, 'learning': learning,
              'baseline': baseline, 'training_baseline': baseline_fit, 'training_choices': fitted,
              'chosen_weights': choices, 'candidates': results, 'details': details,
              'selection_without_abstention': raw, 'individual_seed_fixed_ensemble_calibration': seed_results,
              'controls': controls, 'gates': gates, 'passes': all(gates.values()),
              'cost': {'acquisition_cpu_s': acquisition, 'teaching_total_cpu_s': teaching_cpu,
                       'selection_cpu_s': selection_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': time.process_time()-start_cpu, 'wall_s': time.monotonic()-start_wall,
                       'peak_rss_kib': rss, 'model_bytes': model_path.stat().st_size}}
    (ROOT / f'results_v3/{experiment.lower()}_paired_groups.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'results': results, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    begin_cpu, begin_wall = time.process_time(), time.monotonic()
    try:
        main()
    except TimeoutError as error:
        (ROOT / 'results_v3/g76_interruption.json').write_text(json.dumps({
            'status': 'interrupted_budget', 'error': str(error),
            'cpu_s': time.process_time()-begin_cpu, 'wall_s': time.monotonic()-begin_wall,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }, ensure_ascii=False, indent=2)+'\n')
        raise

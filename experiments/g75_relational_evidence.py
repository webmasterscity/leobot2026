"""G-75: learn relational applicability from human FAQ pairs; prototype only."""
from collections import Counter, defaultdict
from hashlib import sha256
import bisect
import json
import math
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from leobot import Bot
from leobot.context import cell_key
from experiments.g23_role_paths import route
from experiments.g60_calibrar_confianza import naive_bayes, score
from experiments.g65_correspondencias import examples, baseline_scores
from experiments.g57_kiosco import businesses, contains, plain
from experiments.g68_confianza import TRAIN, DEV, collect, metrics, isotonic, calibrated
from experiments.g74_relation_coverage import inventory, new_links, prepare, BASE_SHA, ENGINE, ROOT

RAW = ('semantic_score', 'binding_score', 'interpretations')
WEIGHTS = (.25, .5, 1., 2.)


def key(*parts):
    return json.dumps(parts, ensure_ascii=False, separators=(',', ':'))


def pair_features(question, answer, mapping):
    qterms, aterms = question['terms'], answer['terms']
    ahead = defaultdict(list)
    for j, word in enumerate(aterms):
        for frame in mapping.get(word, {}):
            ahead[frame].append(j)
    pairs = defaultdict(set)
    for i, word in enumerate(qterms):
        for frame in mapping.get(word, {}):
            for j in ahead.get(frame, ()):
                pairs[(i, j)].add(frame)
    stats = {'head_pairs': len(pairs), 'bindings': 0, 'exhausted': len(pairs) > 64,
             'interpretations': 0, 'novel': False}
    if stats['exhausted']:
        return set(), stats
    feats, frames_seen = set(), set()
    qi, ai = defaultdict(list), defaultdict(list)
    for i, word in enumerate(qterms):
        if word:
            qi[word].append(i)
    for j, word in enumerate(aterms):
        if word:
            ai[word].append(j)
    common = sorted(set(qi) & set(ai))
    qcache, acache = {}, {}
    for (i, j), frames in sorted(pairs.items()):
        stats['novel'] |= qterms[i] != aterms[j] and qterms[i] not in ai
        layout = set()
        if question['nodes'] and answer['nodes']:
            for word in common:
                for x in qi[word]:
                    if x == i:
                        continue
                    if (i, x) not in qcache:
                        qcache[(i, x)] = route(question['nodes'], str(i+1), str(x+1))
                    qp = qcache[(i, x)]
                    if qp is None:
                        continue
                    for y in ai[word]:
                        if y == j:
                            continue
                        if (j, y) not in acache:
                            acache[(j, y)] = route(answer['nodes'], str(j+1), str(y+1))
                        ap = acache[(j, y)]
                        if ap is not None:
                            stats['bindings'] += 1
                            if stats['bindings'] > 128:
                                stats['exhausted'] = True
                                return set(), stats
                            layout.add((qp, ap))
        for frame in sorted(frames):
            frames_seen.add(frame)
            feats.add(key('R', frame))
            for qp, ap in sorted(layout):
                feats.add(key('B', frame, qp, ap))
            if layout:
                feats.add(key('J', frame, sorted(layout)))
    stats['interpretations'] = len(frames_seen)
    return feats, stats


def learn_weights(triples, *, shuffled=False):
    positive, background = Counter(), Counter()
    domains = defaultdict(set)
    rng = random.Random(75)
    for domain, own, other in triples:
        if shuffled and rng.randrange(2):
            own, other = other, own
        positive.update(own)
        background.update(other)
        for feature in own | other:
            domains[feature].add(domain)
        if len(domains) > 200_000:
            raise RuntimeError('Más de 200 000 rasgos')
    return {f: math.log((positive[f]+1)/(background[f]+1))
            for f in sorted(domains) if len(domains[f]) >= 5}


def feature_score(weights, features, *, lexical=False):
    values = [weights[f] for f in sorted(features) if f in weights
              and (not lexical or f.startswith('["R",'))]
    return sum(values) / math.sqrt(len(values)) if values else 0.


class Views:
    def __init__(self, bot, mapping):
        self.bot, self.mapping, self.cache = bot, mapping, {}
        self.stats = Counter()

    def get(self, text):
        if text in self.cache:
            return self.cache[text]
        words = self.bot.split_words(text)
        terms = [self.bot._term(w) if w[:1].isalnum() else '' for w in words]
        nodes = {}
        if len(words) <= 48 and any(w in self.mapping for w in terms):
            parsed = self.bot.parse_words(words)
            self.stats['parse_calls'] += 1
            if parsed and parsed.get('status') == 'parsed_syntax' and parsed.get('labels'):
                nodes = {str(i+1): {'head': str(head), 'deprel': label}
                         for i, (head, label) in enumerate(zip(parsed['heads'], parsed['labels']))}
            else:
                self.stats['unparsed'] += 1
        elif len(words) > 48:
            self.stats['long_units_without_bindings'] += 1
        result = {'terms': terms, 'nodes': nodes}
        if len(self.cache) >= 8192:
            self.cache.clear()
        self.cache[text] = result
        return result


def education(bot, mapping):
    raw = examples(bot, ROOT / '.leobot-data/mfaq_es_train.jsonl', raw=True)
    eligible, excluded = defaultdict(list), Counter()
    for domain, q, a in raw:
        if len(bot.split_words(q)) > 24 or len(bot.split_words(a)) > 48:
            excluded['too_long'] += 1
            continue
        eligible[domain].append((q, a))
    pool = []
    for domain, rows in sorted(eligible.items()):
        rows = sorted(set(rows))
        for i, (q, a) in enumerate(rows):
            other = next((rows[(i+j) % len(rows)][1] for j in range(1, len(rows))
                          if rows[(i+j) % len(rows)][1] != a), None)
            if other is None:
                excluded['no_distinct_background'] += 1
                continue
            digest = sha256(json.dumps((domain, q, a), ensure_ascii=False).encode()).digest()
            pool.append((digest, domain, q, a, other))
    chosen = sorted(pool)[:2000]
    views, counts, triples = Views(bot, mapping), Counter(), []
    for idx, (_, domain, q, a, other) in enumerate(chosen):
        qview = views.get(q)
        own, os = pair_features(qview, views.get(a), mapping)
        rival, rs = pair_features(qview, views.get(other), mapping)
        triples.append((domain, own, rival))
        counts['own_exhausted'] += os['exhausted']
        counts['background_exhausted'] += rs['exhausted']
        counts['own_with_features'] += bool(own)
        counts['background_with_features'] += bool(rival)
        counts['own_bindings'] += os['bindings']
        if (idx+1) % 500 == 0:
            print(json.dumps({'stage': 'education', 'pairs': idx+1}), flush=True)
    weights = learn_weights(triples)
    shuffled = learn_weights(triples, shuffled=True)
    return weights, shuffled, {'sampled_g65_pairs': len(raw), 'eligible': len(pool),
                               'chosen': len(chosen), 'domains': len({t[1] for t in chosen}),
                               'exclusions': dict(excluded), 'features': len(weights),
                               'by_kind': dict(Counter(json.loads(f)[0] for f in weights)),
                               'observations': dict(counts), 'parsing': dict(views.stats)}


def intervals(rows, fields=RAW):
    result = {}
    for name in fields:
        values = sorted(r['f'][name] for r in rows)
        result[name] = sorted({values[int((len(values)-1)*q)] for q in (.25, .5, .75)})
    return result


def discretize(features, edges):
    return {name: str(bisect.bisect_right(edges[name], value)) if name in edges else value
            for name, value in features.items()}


def fit_confidence(rows, fields=RAW):
    active = [r for r in rows if fields[0] in r['f']]
    if len(active) < 60 or any(sum(r['half'] == h for r in active) < 30 for h in (0, 1)):
        return None, [r['baseline_p'] for r in rows]
    edges = intervals(active, fields)
    binned = [{**r, 'f': discretize(r['f'], edges)} for r in active]
    points, raw = [], {}
    for half in (0, 1):
        learned = naive_bayes([r for r in binned if r['half'] != half])
        for r in binned:
            if r['half'] == half:
                value = score(learned, r['f'])
                points.append((value, r['y']))
                raw[r['id']] = value
    table = isotonic(points)
    result = {'edges': edges, 'model': naive_bayes(binned), 'calibration': table}
    return result, [calibrated(table, raw[r['id']]) if r['id'] in raw else r['baseline_p'] for r in rows]


class RelationalRanker:
    feature_fields = RAW

    def __init__(self, bot, mapping, weights, mode='full', weight=1.):
        self.bot, self.mapping, self.weights = bot, mapping, weights
        self.mode, self.weight, self.confidence = mode, weight, None
        self.original_rank, self.original_load = bot._rank, bot.load_context
        self.views = Views(bot, mapping)
        self.units, self.prepared, self.query_cache, self.analyses = [], [], {}, {}
        self.stats = Counter()
        self.preparation_cpu = 0.
        bot._rank, bot.load_context = self.rank, self.load

    def restore(self):
        self.bot._rank, self.bot.load_context = self.original_rank, self.original_load

    def load(self, *args, **kwargs):
        result = self.original_load(*args, **kwargs)
        t = time.process_time()
        self.units, self.prepared, self.query_cache, self.analyses = [], [], {}, {}
        for unit in self.bot.context_units:
            text = unit['text'] + (' ' + unit['heading'] if unit.get('inherited') else '')
            view = self.views.get(text) if self.weight else {'terms': self.bot.context_terms(text), 'nodes': {}}
            self.units.append(view)
            self.prepared.append(prepare(view['terms'], self.mapping))
        self.preparation_cpu += time.process_time() - t
        return result

    def evidence(self, question, terms):
        if question in self.query_cache:
            return self.query_cache[question]
        if question not in self.analyses:
            self.analyses[question] = self.analyze(question, terms)
        rows = {}
        for i, (features, stats) in self.analyses[question].items():
            lexical = feature_score(self.weights, features, lexical=True)
            full = feature_score(self.weights, features)
            rows[i] = (lexical if self.mode == 'lexical' else full,
                       lexical, 0. if self.mode == 'lexical' else full - lexical,
                       stats['interpretations'])
        self.query_cache[question] = rows
        return rows

    def analyze(self, question, terms):
        rows = {}
        if len(self.bot.split_words(question)) <= 24:
            candidates = [i for i, p in enumerate(self.prepared) if new_links(terms, p, self.mapping)[1]]
            if candidates:
                # A new question is parsed here; unit parses were prepared at load.
                self.views.cache.pop(question, None)
                qview = self.views.get(question)
                for i in candidates:
                    features, stats = pair_features(qview, self.units[i], self.mapping)
                    self.stats['pair_exhaustions'] += stats['exhausted']
                    if stats['exhausted'] or not stats['novel']:
                        continue
                    rows[i] = features, stats
        return rows

    def rank(self, terms, question=''):
        original = self.original_rank(terms, question)
        if not original or not self.weight:
            return original
        evidence = self.evidence(question, terms)
        if not evidence:
            self.stats['no_signal'] += 1
            return original
        scores = baseline_scores(self.bot, terms, question)
        options = set(evidence) | {original['unit']}
        options = {i for i in options if self.bot.context_units[i]['kind'] != 'question'} | {original['unit']}
        values = {i: scores[i] + self.weight * evidence.get(i, (0.,))[0] for i in options}
        best = max(options, key=lambda i: (values[i], -i))
        if best not in evidence:
            return original
        ranked = dict(original)
        ranked['unit'], ranked['score'] = best, values[best]
        runner = max((scores[i] + self.weight * evidence.get(i, (0.,))[0]
                      for i in range(len(scores)) if i != best), default=values[best])
        ranked['margin'] = max(0., values[best] - runner)
        unit_terms = self.prepared[best][0]
        title, bridge = set(self.bot.context_title), self.bot._bridge()
        asked = {q: 0. if q in title else min(max(self.bot._delta(q), 0.), 1-1e-4) for q in set(terms)}
        explained = {q: 'direct' if q in unit_terms else 'bridge' for q in asked
                     if q in unit_terms or any(a in unit_terms for a, _ in bridge.get(q, ()))}
        ranked['explained'] = explained
        ranked['unaddressed'] = max((v for q, v in asked.items() if q not in explained), default=0.)
        mass = sum(asked.values())
        ranked['covered'] = sum(v for q, v in asked.items() if q in explained)/mass if mass else 0.
        ranked['cell'] = cell_key(ranked['unaddressed'], ranked['margin'])
        ranked['features'] = self.bot._features(ranked, question)
        _, lex, bindings, ambiguity = evidence[best]
        ranked['features'].update(zip(self.feature_fields, (lex, bindings, ambiguity)))
        if self.confidence is not None:
            f = discretize(ranked['features'], self.confidence['edges'])
            ranked['useful'] = calibrated(self.confidence['calibration'], score(self.confidence['model'], f))
        self.stats['active'] += 1
        self.stats['changed_unit'] += best != original['unit']
        return ranked


def training_contexts():
    for bank in TRAIN:
        root = Path('results_v3/kiosco') / bank
        for name, text, instructions, conversations in businesses(sorted(p for p in root.iterdir() if p.is_dir())):
            yield bank+'/'+name, text, instructions, conversations


def check_budget(deadline):
    if deadline is not None and time.process_time() > deadline:
        raise TimeoutError('Presupuesto de selección y evaluación G75 agotado')


def collect_variants(bot, mapping, weights, shuffled, contexts=None, deadline=None):
    """Same rows as collect, changing traversal order to parse each context once."""
    rows = {(mode, weight): [] for mode in ('full', 'lexical', 'shuffled') for weight in WEIGHTS}
    ranker = RelationalRanker(bot, mapping, weights)
    bot.calibrated, bot.closest = False, False
    begin = time.process_time()
    try:
        for n, (group, text, instructions, conversations) in enumerate(
                training_contexts() if contexts is None else contexts, 1):
            bot.load_context(text, instructions)
            digest = int(sha256(group.encode()).hexdigest(), 16)
            for (mode, weight), target in rows.items():
                check_budget(deadline)
                ranker.mode = 'lexical' if mode == 'lexical' else 'full'
                ranker.weights = shuffled if mode == 'shuffled' else weights
                ranker.weight, ranker.query_cache = weight, {}
                for c, conv in enumerate(conversations):
                    for i, turn in enumerate(conv):
                        action = turn.get('accion', 'responder')
                        if action == 'charla':
                            continue
                        reply = bot.answer(turn['cliente'])
                        if reply['status'] != 'answered':
                            continue
                        keys = [k for k in turn.get('claves', []) or [] if plain(k)]
                        if action not in ('abstenerse', 'derivar') and not keys:
                            continue
                        _, question = bot._question_part(turn['cliente'])
                        ranked = bot._rank(bot.context_terms(question), question)
                        absent = action in ('abstenerse', 'derivar')
                        useful = int(not absent and all(contains(reply['text'], k) for k in keys))
                        target.append({'id': f'{group}/{c}/{i}', 'group': group, 'fold': digest % 5,
                                       'half': digest % 2, 'y': useful, 'f': ranked['features'],
                                       'core': action == 'responder' and turn.get('tipo') in ('directa', 'si_no'),
                                       'absent': absent, 'baseline_p': ranked['useful']})
            if n % 5 == 0:
                print(json.dumps({'stage': 'training_contexts', 'n': n,
                                  'cpu_s': time.process_time()-begin}), flush=True)
    finally:
        ranker.restore()
    return rows, {'cpu_s': time.process_time()-begin, 'parsing': dict(ranker.views.stats),
                  'preparation_cpu_s': ranker.preparation_cpu}


def fingerprint():
    names = ['experiments/g75_relational_evidence.py', 'experiments/g65_correspondencias.py',
             'experiments/g74_relation_coverage.py', 'prereg/G-75-relaciones-con-participantes.md']
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *names):
        raise RuntimeError('Motor o experimento sin congelar')
    return {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in names}


def public_measure(bot, ranker=None, deadline=None):
    from experiments.g68_g70_respuestas_reales import measure
    bot.calibrated, bot.closest = True, True
    original_answer = bot.answer
    digest, literal_failures = sha256(), 0
    def recorded(question, history=None):
        nonlocal literal_failures
        check_budget(deadline)
        if ranker is not None:
            ranker.query_cache.clear()
            ranker.analyses.clear()
        reply = original_answer(question, history)
        digest.update(json.dumps(reply, ensure_ascii=False, sort_keys=True).encode())
        digest.update(b'\n')
        if reply.get('evidence'):
            evidence = reply['evidence']
            literal_failures += evidence['unit'] != bot.context_units[evidence['index']]['text']
        return reply
    bot.answer = recorded
    try:
        result = measure(bot)
    finally:
        bot.answer = original_answer
    result.update(response_sha256=digest.hexdigest(), nonliteral_evidence=literal_failures)
    return result


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (900, 910))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes = fingerprint()
    cpu0, wall0 = time.process_time(), time.monotonic()
    base = ROOT / '.leobot-data/base_kiosco.json'
    if sha256(base.read_bytes()).hexdigest() != BASE_SHA:
        raise RuntimeError('Base distinta')
    bot = Bot.load(base)
    mapping, source = inventory(bot)
    weights, shuffled, education_report = education(bot, mapping)
    teaching_cpu = time.process_time() - cpu0
    checkpoint = ROOT / '.leobot-data/g75_education_checkpoint.json'
    checkpoint.write_text(json.dumps({'weights': weights, 'shuffled': shuffled,
                                     'education': education_report, 'sources_sha256': hashes,
                                     'teaching_cpu_s': teaching_cpu}, ensure_ascii=False))
    print(json.dumps({'stage': 'learned', 'cpu_s': teaching_cpu, 'education': education_report}), flush=True)
    t = time.process_time()
    deadline = t + 300
    baseline_train = collect(bot, TRAIN)
    baseline_fit = metrics(baseline_train, [r['baseline_p'] for r in baseline_train])
    baseline = public_measure(bot, deadline=deadline)
    if (baseline['core'], baseline['useful_core'], baseline['absent_n'], baseline['quotes_without_data']) != (816, 269, 488, 74):
        raise RuntimeError('La referencia no se reproduce')
    choices, fits, retained = {}, {}, {}
    training_rows, preparation = collect_variants(bot, mapping, weights, shuffled, deadline=deadline)
    # Select each learner entirely in TRAIN, then fix the choices before DEV.
    for mode in ('full', 'lexical', 'shuffled'):
        best = (baseline_fit['useful_core'], -baseline_fit['quotes_without_data'], 0.)
        selected, learned = 0., None
        fits[mode] = {}
        for w in WEIGHTS:
            rows = training_rows[(mode, w)]
            confidence, probabilities = fit_confidence(rows)
            fitted = metrics(rows, probabilities)
            fits[mode][str(w)] = fitted
            valid = confidence is not None and fitted['quotes_without_data'] <= baseline_fit['quotes_without_data']
            candidate = (fitted['useful_core'], -fitted['quotes_without_data'], -w)
            if valid and candidate > best:
                best, selected, learned = candidate, w, confidence
        choices[mode] = selected
        retained[mode] = learned
        print(json.dumps({'stage': 'selected', 'mode': mode, 'weight': selected}), flush=True)
    validation_cpu = time.process_time() - t
    t = time.process_time()
    results, details = {}, {}
    for mode in ('full', 'lexical', 'shuffled'):
        ranker = RelationalRanker(bot, mapping, shuffled if mode == 'shuffled' else weights,
                                 mode='lexical' if mode == 'lexical' else 'full', weight=choices[mode])
        ranker.confidence = retained[mode]
        results[mode] = public_measure(bot, ranker, deadline=deadline)
        details[mode] = {'stats': dict(ranker.stats), 'load_preparation_cpu_s': ranker.preparation_cpu,
                         'parsing': dict(ranker.views.stats)}
        ranker.restore()
        print(json.dumps({'stage': 'measured', 'mode': mode, 'results': results[mode]}), flush=True)
    model_path = ROOT / '.leobot-data/g75_relational_models.json'
    model_path.write_text(json.dumps({'weights': weights, 'shuffled': shuffled,
                                      'choices': choices, 'confidence': retained}, ensure_ascii=False))
    saved = json.loads(model_path.read_text())
    replay = RelationalRanker(bot, mapping, saved['weights'], weight=saved['choices']['full'])
    replay.confidence = saved['confidence']['full']
    restored = public_measure(bot, replay, deadline=deadline)
    replay.restore()
    counting = ('core', 'useful_core', 'quotes', 'absent_n', 'quotes_without_data', 'response_sha256')
    controls = {'reload_counts_equal': all(restored[k] == results['full'][k] for k in counting)}
    zero = RelationalRanker(bot, mapping, {}, weight=0.)
    unmodified = public_measure(bot, deadline=deadline)
    zero.restore()
    controls['disabled_counts_equal'] = all(unmodified[k] == baseline[k] for k in counting)
    evaluation_cpu = time.process_time() - t
    primary = results['full']
    gates = {'gain': primary['useful_core'] >= baseline['useful_core'] + .05 * baseline['core'],
             'binding_gain': primary['useful_core'] >= results['lexical']['useful_core'] + .02 * baseline['core'],
             'shuffled_gain': primary['useful_core'] >= results['shuffled']['useful_core'] + .05 * baseline['core'],
             'absent': primary['quotes_without_data'] <= baseline['quotes_without_data'],
             'latency': primary['p95_ms'] < 5, 'controls': all(controls.values()),
             'literal_evidence': primary['nonliteral_evidence'] == 0}
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    gates['budget'] = teaching_cpu <= 600 and validation_cpu + evaluation_cpu <= 300 and rss <= 1024**2 and time.monotonic()-wall0 <= 1200
    if fingerprint() != hashes:
        raise RuntimeError('Código cambiado durante el experimento')
    report = {'experiment': 'G-75', 'scope': 'spent development; API calls with external prototype, no promotion',
              'engine_sha': ENGINE, 'sources_sha256': hashes, 'engine_unchanged': True,
              'source': source, 'education': education_report, 'baseline': baseline,
              'training_baseline': baseline_fit, 'training_choices': fits, 'chosen_weights': choices,
              'training_preparation': preparation,
              'candidates': results, 'details': details, 'controls': controls,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'selection_cpu_s': validation_cpu,
                       'evaluation_and_controls_cpu_s': evaluation_cpu, 'total_cpu_s': time.process_time()-cpu0,
                       'wall_s': time.monotonic()-wall0, 'peak_rss_kib': rss, 'model_bytes': model_path.stat().st_size}}
    output = ROOT / 'results_v3/g75_relational_evidence.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'results': results, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    start_cpu, start_wall = time.process_time(), time.monotonic()
    try:
        main()
    except TimeoutError as error:
        (ROOT / 'results_v3/g75_budget_interruption.json').write_text(json.dumps({
            'status': 'interrupted_budget', 'error': str(error),
            'cpu_s': time.process_time()-start_cpu, 'wall_s': time.monotonic()-start_wall,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }, ensure_ascii=False, indent=2)+'\n')
        raise

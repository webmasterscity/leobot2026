"""G86: learn marked, ordered fragments with existing contrastive counts."""
from collections import Counter, defaultdict
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from leobot import Bot
from leobot.context import _plain, _bin
from experiments import g65_correspondencias as g65
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import learn_weights, feature_score, public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g85_human_selection import DirectBinding, G84_SHA


def view(bot, text, limit):
    words = bot.split_words(text)
    if len(words) > limit:
        return None
    tags = bot.tag_words(words) if words else []
    if tags is None:
        return None
    asking = {_plain(word) for word in bot.syntax_model.get('interrogatives', ())}
    return (tuple(bot._term(w) if w[:1].isalnum() else '' for w in words), tuple(tags),
            tuple(_plain(w) for w in words if _plain(w) in asking))


def fragments(question, answer, bridge, *, unordered=False):
    out = [set(), set(), set()]
    if question is None or answer is None:
        return out
    qt, qtags, form = question
    at, atags, _ = answer
    qs, ans = set(qt)-{''}, set(at)-{''}
    destinations = {q: {a for a, _ in bridge.get(q, ())} & ans for q in qs}
    indirect = set().union(*destinations.values()) if destinations else set()
    qmarked = [(tag, 1 if word and word in ans else 2 if destinations.get(word) else 0)
               for word, tag in zip(qt, qtags)]
    amarked = [(tag, 1 if word and word in qs else 2 if word and word in indirect else 0)
               for word, tag in zip(at, atags)]
    for side, tokens in (('Q', qmarked), ('A', amarked)):
        if unordered:
            tokens = sorted(tokens)
        sequence = ['^']+[f'{tag}:{mark}' for tag, mark in tokens]+['$']
        prefix = side+'\x1f'+('\x1e'.join(form) if side == 'A' else '')+'\x1f'
        for size in (1, 2, 3):
            for i in range(len(sequence)-size+1):
                out[size-1].add(prefix+str(size)+'\x1f'+'\x1e'.join(sequence[i:i+size]))
    return out


def education(bot, deadline):
    stages, start = {}, time.process_time()
    raw = g65.examples(bot, ROOT/'.leobot-data/mfaq_es_train.jsonl', raw=True)
    eligible, excluded = defaultdict(list), Counter()
    for domain, q, a in raw:
        if len(bot.split_words(q)) > 24 or len(bot.split_words(a)) > 48:
            excluded['too_long'] += 1
        else:
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
            digest = hashlib.sha256(json.dumps((domain, q, a), ensure_ascii=False).encode()).digest()
            pool.append((digest, domain, q, a, other))
    chosen = sorted(pool)[:6000]
    stages['example_selection_cpu_s'] = time.process_time()-start
    source = {'sampled': len(raw), 'eligible': len(pool), 'chosen': len(chosen),
              'domains': len({r[1] for r in chosen}), 'exclusions': dict(excluded),
              'selected_sha256': hashlib.sha256(b''.join(r[0] for r in chosen)).hexdigest(),
              'source_sha256': g65.MFAQ_SHA}
    del raw, eligible, pool
    start, cache, prepared = time.process_time(), {}, []
    def prepared_view(text, limit):
        key = (text, limit)
        if key not in cache:
            cache[key] = view(bot, text, limit)
        return cache[key]
    for i, (_, domain, q, a, other) in enumerate(chosen):
        if time.process_time() > deadline:
            raise TimeoutError('G86 agotó preparación humana')
        prepared.append((domain, prepared_view(q, 24), prepared_view(a, 48), prepared_view(other, 48)))
        if (i+1) % 1000 == 0:
            print(json.dumps({'stage': 'human_views', 'pairs': i+1, 'cpu_s': time.process_time()-start}), flush=True)
    stages['human_preparation_cpu_s'] = time.process_time()-start
    del chosen, cache
    bridge, tables = bot._bridge(), {}
    for mode in ('ordered', 'unordered', 'shuffled'):
        start = time.process_time()
        def triples():
            for domain, q, a, other in prepared:
                if time.process_time() > deadline:
                    raise TimeoutError('G86 agotó conteos')
                own = set().union(*fragments(q, a, bridge, unordered=mode == 'unordered'))
                rival = set().union(*fragments(q, other, bridge, unordered=mode == 'unordered'))
                yield domain, own, rival
        weights = learn_weights(triples(), shuffled=mode == 'shuffled')
        tables[mode] = {'mode': mode, 'weights': weights}
        stages[mode+'_counts_cpu_s'] = time.process_time()-start
        print(json.dumps({'stage': 'fragment_table', 'mode': mode, 'features': len(weights),
                          'cpu_s': stages[mode+'_counts_cpu_s']}), flush=True)
    return tables, {'source': source, 'features': {m: len(t['weights']) for m, t in tables.items()}, 'stages': stages}


class FragmentBinding:
    def __init__(self, bot, margins):
        self.bot, self.margins = bot, margins
        self.original_candidates, self.original_load = bot._candidates, bot.load_context
        self.units, self.prepared = None, None
        self.cost = {'context_cpu_s': 0., 'contexts': 0, 'long_units': 0,
                     'long_questions': 0, 'comparisons': 0}
        bot._candidates, bot.load_context = self.candidates, self.load_context

    def load_context(self, *args, **kwargs):
        result = self.original_load(*args, **kwargs)
        self.prepare()
        return result

    def prepare(self):
        if not self.bot.context_model.get('fragments'):
            return False
        if self.units is not self.bot.context_units:
            start = time.process_time()
            self.prepared = [view(self.bot, unit['text'], 48) for unit in self.bot.context_units]
            self.units = self.bot.context_units
            self.cost['context_cpu_s'] += time.process_time()-start
            self.cost['contexts'] += 1
            self.cost['long_units'] += sum(v is None for v in self.prepared)
        return True

    def candidates(self, order, how, base, asked, terms, question, k):
        candidates = self.original_candidates(order, how, base, asked, terms, question, k)
        if not self.prepare():
            return candidates
        packet = self.bot.context_model['fragments']
        q = view(self.bot, question, 24)
        self.cost['long_questions'] += q is None
        bridge, scores = self.bot._bridge(), []
        for (_, i), _ in zip(order, candidates):
            fs = fragments(q, self.prepared[i], bridge, unordered=packet['mode'] == 'unordered')
            scores.append([feature_score(packet['weights'], group) for group in fs])
        self.cost['comparisons'] += len(scores)
        for i, f in enumerate(candidates):
            for size in range(3):
                value = scores[i][size]
                other = max((row[size] for j, row in enumerate(scores) if j != i), default=0.)
                f[f'fragment{size+1}_score'] = str(_bin(value, self.margins))
                f[f'fragment{size+1}_margin'] = str(_bin(value-other, self.margins))
        return candidates

    def restore(self):
        self.bot._candidates, self.bot.load_context = self.original_candidates, self.original_load
        self.units = self.prepared = None


def fingerprint():
    files = ('experiments/g86_ordered_fragments.py', 'experiments/test_g86_ordered_fragments.py',
             'experiments/g85_human_selection.py', 'experiments/g84_indirect_alignment.py',
             'experiments/g84b_compact_replay.py', 'experiments/g65_correspondencias.py',
             'experiments/g79_joint_selection.py', 'experiments/g68_confianza.py',
             'experiments/g75_relational_evidence.py', 'prereg/G-86-orden-de-fragmentos-relacionados.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G86 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start, prep = time.process_time(), None
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        direct = DirectBinding(bot)
        binding = FragmentBinding(bot, direct.margins)
        result, error = public_measure(bot), None
        prep = {'alignment': dict(direct.cost), 'fragments': dict(binding.cost)}
        binding.restore()
        direct.restore()
        reference.restore()
    except Exception as exc:
        result, error = None, repr(exc)
    return {'result': result, 'error': error, 'cpu_s': time.process_time()-start,
            'preparation_included': prep, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (845, 850))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g84_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G84_SHA
    fixed = json.loads(previous.read_text())['models']['direct']
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    bot.context_model = fixed
    components = Components()
    components.correct_calibration()
    reference = components.bind(bot)
    ns = components.learner
    tables, taught = education(bot, cpu0+600)
    (ROOT/'.leobot-data/g86_fragments.json').write_text(json.dumps({'tables': tables, 'education': taught}, ensure_ascii=False))
    direct = DirectBinding(bot)
    binding = FragmentBinding(bot, direct.margins)
    native = {key: value for key, value in fixed.items() if key != 'selection'}
    original_fit, fits, models, selector_data = ns['fit'], [], {}, {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G86 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        (ROOT/'.leobot-data/g86_fit_checkpoint.json').write_text(json.dumps({'fits': fits, 'latest_model': fitted}))
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = ROOT/'.leobot-data/g86_models.json'
    for name in ('removed', 'ordered', 'unordered', 'shuffled'):
        context = {**native, 'fragments': None if name == 'removed' else tables[name]}
        bot.context_model = context
        start = time.process_time()
        turns = ns['training_turns'](bot)
        assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
        prep_cost = time.process_time()-start
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        learned = ns['selection'](turns, names, 6)
        models[name] = {**context, 'selection': ns['table_of'](learned)}
        selector_data[name] = {'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns),
                               'features': names, 'preparation_cpu_s': prep_cost}
        model_path.write_text(json.dumps({'models': models, 'education': taught, 'selection': selector_data,
                                         'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G86 agotó enseñanza')
    teaching_prep = {'alignment': dict(direct.cost), 'fragments': dict(binding.cost)}
    results, raw, evaluation_cpu = {}, {}, 0.
    def measured(name, context, raw_selection=False):
        nonlocal evaluation_cpu
        start = time.process_time()
        bot.context_model = context
        result = public_measure(bot, deadline=start+240-evaluation_cpu)
        results[name] = result
        if raw_selection:
            rows = g68.collect(bot, g68.DEV)
            raw[name] = {'core': sum(r['core'] for r in rows),
                         'correct_first': sum(r['core'] and r['y'] for r in rows)}
        evaluation_cpu += time.process_time()-start
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result, 'raw': raw.get(name)}), flush=True)
        return result
    baseline = measured('baseline', original)
    previous_report = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())['candidates']
    assert baseline['response_sha256'] == previous_report['baseline']['response_sha256']
    for name, context in models.items():
        measured(name, context, True)
        if name == 'removed':
            assert results[name]['response_sha256'] == previous_report['direct']['response_sha256']
    start = time.process_time()
    bot.context_model = models['ordered']
    bot.load_context('', '')
    readable, candidate = ROOT/'.leobot-data/g86_candidate_readable.json', ROOT/'.leobot-data/g86_candidate.json'
    bot.save(readable)
    evaluation_cpu += time.process_time()-start
    all_prep = {'alignment': dict(direct.cost), 'fragments': dict(binding.cost)}
    binding.restore()
    direct.restore()
    reference.restore()
    disabled = measured('disabled', original)
    del binding, direct, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    compact_run = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(readable), str(candidate)],
                                 cwd=ROOT, capture_output=True, text=True, check=True, timeout=45)
    compact = json.loads(compact_run.stdout)
    process = subprocess.run([sys.executable, '-m', 'experiments.g86_ordered_fragments', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, check=True, timeout=60)
    child = json.loads(process.stdout)
    child_cpu = compact['cpu_s']+child['cpu_s']
    evaluation_cpu += time.process_time()-start+child_cpu
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'removed_exact': results['removed']['response_sha256'] == previous_report['direct']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['ordered']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(compact['peak_rss_kib'], child['peak_rss_kib']))
    primary = results['ordered']
    total_cpu = time.process_time()-cpu0+child_cpu
    gates = {'useful_gain': primary['useful_core'] >= 344, 'absent': primary['quotes_without_data'] <= 73,
             'selection_gain': raw['ordered']['correct_first'] >= 499,
             'structural_gain': all(primary['useful_core'] >= results[m]['useful_core']+17
                                    for m in ('removed', 'unordered', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 240 and total_cpu <= 840
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1100}
    assert fingerprint() == hashes
    report = {'experiment': 'G86', 'scope': 'spent development; external prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes,
              'g84_models_sha256': G84_SHA, 'base_sha256': BASE_SHA,
              'education': taught, 'selection_education': selector_data, 'fits': fits,
              'candidates': results, 'selection_without_abstention': raw,
              'controls': controls, 'compaction': compact, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'teaching_preparation_included': teaching_prep,
                       'all_preparation_included': all_prep, 'evaluation_cpu_s': evaluation_cpu,
                       'total_cpu_s': total_cpu, 'wall_s': time.monotonic()-wall0,
                       'peak_rss_kib': rss, 'parent_rss_during_children_kib': parent_rss,
                       'models_bytes': model_path.stat().st_size, 'base_bytes': candidate.stat().st_size}}
    (ROOT/'results_v3/g86_ordered_fragments.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': report['cost']}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g86_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None),
            }, indent=2)+'\n')
            raise

"""G93: learn answer-class distributions from human QA and a public lexicon."""
from collections import Counter, defaultdict
import gc
import hashlib
import io
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import tarfile
import time

from leobot import Bot
from leobot.context import COVER_BINS, _bin, _plain
from leobot.reading import KIND_SUPPORT
from experiments import g68_confianza as g68
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE, REFERENCE_HASHES
from experiments.g85_human_selection import DirectBinding, G84_SHA, select_human


def lexical_source(bot):
    manifest = json.loads((ROOT/'results_v3/g93_source_manifest.json').read_text())
    files = {}
    for entry in manifest['files']:
        raw = (ROOT/'.leobot-data/g93'/entry['name']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        files[entry['name']] = raw
    expected = next(e for e in manifest['files'] if 'noun_member' in e)['noun_member']
    with tarfile.open(fileobj=io.BytesIO(files['WordNet-3.0.tar.gz']), mode='r:gz') as archive:
        raw = archive.extractfile(expected['name']).read()
        license_text = archive.extractfile('WordNet-3.0/LICENSE').read().decode()
    assert hashlib.sha256(raw).hexdigest() == expected['sha256']
    classes = {}
    for line in raw.decode().splitlines():
        if not line or not line[0].isdigit():
            continue
        offset, category, pos = line.split()[:3]
        assert pos == 'n'
        classes[offset+'-'+pos] = category
    lexicon, counts = defaultdict(set), Counter()
    for line in files['wn-data-spa.tab'].decode().splitlines():
        if line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) < 3 or fields[1] != 'spa:lemma' or not fields[0].endswith('-n'):
            continue
        sense, _, lemma = fields[:3]
        counts['noun_entries'] += 1
        if sense not in classes:
            counts['unmatched_sense'] += 1
            continue
        if len(lemma.replace('_', ' ').split()) != 1:
            counts['multiword_excluded'] += 1
            continue
        words = bot.split_words(lemma)
        if len(words) != 1 or not words[0][:1].isalnum():
            counts['split_excluded'] += 1
            continue
        lexicon[_plain(bot.lemma_key(words[0]))].add(classes[sense])
        counts['joined_entries'] += 1
    output = {word: sorted(tags) for word, tags in sorted(lexicon.items())}
    counts.update(words=len(output), classes=len({tag for tags in output.values() for tag in tags}),
                  ambiguous_words=sum(len(tags) > 1 for tags in output.values()))
    licenses = {'wordnet': license_text,
                'spanish': 'MCR 3.0; Gonzalez-Agirre, Laparra y Rigau (2012); CC BY 3.0; '+manifest['files'][0]['url']}
    return output, dict(counts), licenses


def normalized(counts):
    total = sum(counts.values())
    return {tag: count/total for tag, count in sorted(counts.items())} if total else {}


def distribution(bot, text, lexicon):
    words = sorted({_plain(bot.lemma_key(w)) for w in bot.split_words(text) if w[:1].isalnum()})
    counts, known = Counter(), 0
    for word in words:
        tags = lexicon.get(word, ())
        if tags:
            known += 1
            for tag in tags:
                counts[tag] += 1/len(tags)
    return normalized(counts), known/max(1, len(words))


def observe(table, keys, vector):
    if not vector:
        return
    for key in keys:
        row = table.setdefault(key, {'n': 0, 'classes': {}})
        row['n'] += 1
        for tag, weight in sorted(vector.items()):
            row['classes'][tag] = row['classes'].get(tag, 0.)+weight


def kind_keys(bot, question):
    return bot._kind_keys([w.lower() for w in bot.split_words(question) if w[:1].isalnum()])


def requested(bot, question, table):
    for key in reversed(kind_keys(bot, question)):
        row = table.get(key)
        if row and row['n'] >= KIND_SUPPORT:
            return normalized(row['classes'])
    return {}


def teach_types(bot, lexicon, deadline):
    examples, source = select_human()
    tables = {'semantic': {}, 'grammar': {}}
    coverage = Counter()
    for qa in examples:
        if time.process_time() > deadline:
            raise TimeoutError('G93 agotó educación de clases')
        keys = kind_keys(bot, qa['question'])
        if not keys:
            coverage['without_question_key'] += 1
            continue
        semantic, _ = distribution(bot, qa['answer'], lexicon)
        words = [w for w in bot.split_words(qa['answer']) if w[:1].isalnum()]
        grammar = normalized(Counter(bot.tag_words(words) or [])) if words else {}
        for name, vector in (('semantic', semantic), ('grammar', grammar)):
            coverage[name+'_answers'] += bool(vector)
            observe(tables[name], keys, vector)
    keys = sorted(tables['semantic'])
    values = [tables['semantic'][key] for key in keys]
    random.Random(1).shuffle(values)
    tables['shuffled'] = dict(zip(keys, values))
    coverage['shuffled_rows_changed'] = sum(tables['semantic'][key] != tables['shuffled'][key] for key in keys)
    return tables, {'source': source, 'coverage': dict(coverage),
                    'supported_keys': {name: sum(r['n'] >= KIND_SUPPORT for r in table.values())
                                       for name, table in tables.items()}}


class TypeBinding:
    def __init__(self, bot, margins):
        self.bot, self.margins = bot, margins
        self.original_candidates, self.original_load = bot._candidates, bot.load_context
        self.packet = self.units = self.vectors = self.known = None
        self.cost = {'context_cpu_s': 0., 'contexts': 0}
        bot._candidates, bot.load_context = self.candidates, self.load_context

    def prepare(self):
        packet = self.bot.context_model.get('semantic_types')
        if not packet:
            self.packet = self.units = self.vectors = self.known = None
            return False
        if self.packet is not packet:
            self.packet, self.units = packet, None
        if self.units is not self.bot.context_units:
            start = time.process_time()
            self.vectors, self.known = [], []
            for unit in self.bot.context_units:
                if packet['mode'] == 'grammar':
                    vector = normalized(unit['classes'])
                    known = float(bool(vector))
                else:
                    vector, known = distribution(self.bot, unit['text'], packet['lexicon'])
                self.vectors.append(vector)
                self.known.append(known)
            self.units = self.bot.context_units
            self.cost['context_cpu_s'] += time.process_time()-start
            self.cost['contexts'] += 1
        return True

    def load_context(self, *args, **kwargs):
        result = self.original_load(*args, **kwargs)
        self.prepare()
        return result

    def candidates(self, order, how, base, asked, terms, question, k):
        candidates = self.original_candidates(order, how, base, asked, terms, question, k)
        if not self.prepare():
            return candidates
        query = requested(self.bot, question, self.packet['questions'])
        scores = [sum(weight*vector.get(tag, 0.) for tag, weight in query.items()) for vector in self.vectors]
        for (_, i), features in zip(order, candidates):
            runner = max((s for j, s in enumerate(scores) if j != i), default=0.)
            features.update(semantic_available=str(int(bool(query))),
                            semantic_agreement=str(_bin(scores[i], COVER_BINS)),
                            semantic_margin=str(_bin(scores[i]-runner, self.margins)),
                            semantic_known=str(_bin(self.known[i], COVER_BINS)))
        return candidates

    def restore(self):
        self.bot._candidates, self.bot.load_context = self.original_candidates, self.original_load
        self.packet = self.units = self.vectors = self.known = None


def fingerprint():
    files = ('experiments/g93_semantic_types.py', 'experiments/test_g93_semantic_types.py',
             'experiments/g85_human_selection.py', 'experiments/g84_indirect_alignment.py',
             'experiments/g84b_compact_replay.py', 'experiments/g79_joint_selection.py',
             'experiments/g68_confianza.py', 'experiments/g75_relational_evidence.py',
             'results_v3/g93_source_manifest.json', 'prereg/G-93-clases-amplias-aprendidas-de-respuestas.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G93 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    preparation = None
    try:
        bot = Bot.load(path)
        reference = Components().bind(bot)
        alignment = DirectBinding(bot)
        binding = TypeBinding(bot, alignment.margins)
        result, error = public_measure(bot), None
        preparation = {'alignment': alignment.cost, 'types': binding.cost}
        binding.restore()
        alignment.restore()
        reference.restore()
    except Exception as exc:
        result, error = None, repr(exc)
    return {'result': result, 'error': error, 'cpu_s': time.process_time()-start,
            'context_preparation_included': preparation, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (805, 810))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g84_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G84_SHA
    fixed = json.loads(previous.read_text())['models']['direct']
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    components = Components()
    components.correct_calibration()
    reference = components.bind(bot)
    alignment = DirectBinding(bot)
    binding = TypeBinding(bot, alignment.margins)
    ns = components.learner
    start = time.process_time()
    lexicon, source, licenses = lexical_source(bot)
    tables, education = teach_types(bot, lexicon, cpu0+600)
    education['lexicon'] = source
    education['acquisition_cpu_s'] = time.process_time()-start
    print(json.dumps({'stage': 'types_ready', 'education': education}), flush=True)
    native = {k: v for k, v in fixed.items() if k != 'selection'}
    original_fit, fits, models = ns['fit'], [], {}
    def timed_fit(items, names):
        if time.process_time()-cpu0 > 600:
            raise TimeoutError('G93 agotó enseñanza')
        start = time.process_time()
        fitted = original_fit(items, names)
        fits.append({'cpu_s': time.process_time()-start, 'rows': fitted['rows'],
                     'features': len(names), 'iterations': fitted['iterations']})
        print(json.dumps({'stage': 'fit', **fits[-1]}), flush=True)
        return fitted
    ns['fit'] = timed_fit
    model_path = ROOT/'.leobot-data/g93/models.json'
    for name in ('removed', 'semantic', 'grammar', 'shuffled'):
        context = dict(native)
        if name != 'removed':
            context['semantic_types'] = {'mode': 'grammar' if name == 'grammar' else 'semantic',
                                         'lexicon': {} if name == 'grammar' else lexicon,
                                         'questions': tables[name], 'licenses': licenses}
        bot.context_model = context
        start = time.process_time()
        turns = ns['training_turns'](bot)
        assert len(turns) == 3520 and sum(len(t['rows']) for t in turns) == 20629
        names = sorted(next(t['rows'][0][0] for t in turns if t['rows']))
        learned = ns['selection'](turns, names, 6)
        models[name] = {**context, 'selection': ns['table_of'](learned)}
        education[name] = {'turns': len(turns), 'rows': sum(len(t['rows']) for t in turns),
                           'features': names, 'preparation_and_learning_cpu_s': time.process_time()-start}
        model_path.write_text(json.dumps({'models': models, 'education': education, 'sources_sha256': hashes}, ensure_ascii=False))
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 600:
        raise TimeoutError('G93 agotó enseñanza')
    results, raw, evaluation_cpu = {}, {}, 0.
    def measured(name, context, raw_selection=False):
        nonlocal evaluation_cpu
        start = time.process_time()
        bot.context_model = context
        result = public_measure(bot, deadline=start+200-evaluation_cpu)
        results[name] = result
        if raw_selection:
            rows = g68.collect(bot, g68.DEV)
            raw[name] = {'core': sum(t['core'] for t in rows),
                         'correct_first': sum(t['core'] and t['y'] for t in rows)}
        evaluation_cpu += time.process_time()-start
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result, 'raw': raw.get(name)}), flush=True)
        return result
    old_report = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())
    baseline = measured('baseline', original)
    assert baseline['response_sha256'] == old_report['candidates']['baseline']['response_sha256']
    for name, context in models.items():
        measured(name, context, raw_selection=True)
        if name == 'removed':
            assert results[name]['response_sha256'] == old_report['candidates']['direct']['response_sha256']
    start = time.process_time()
    bot.context_model = models['semantic']
    bot.load_context('', '')
    readable, candidate = ROOT/'.leobot-data/g93/candidate_readable.json', ROOT/'.leobot-data/g93/candidate.json'
    bot.save(readable)
    evaluation_cpu += time.process_time()-start
    preparation = {'alignment': dict(alignment.cost), 'types': dict(binding.cost)}
    binding.restore()
    restored = measured('restored_direct', fixed)
    alignment.restore()
    reference.restore()
    disabled = measured('disabled', original)
    del binding, alignment, reference, bot, turns
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    start = time.process_time()
    process = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(readable), str(candidate)],
                             cwd=ROOT, capture_output=True, text=True, timeout=40, check=True)
    compacted = json.loads(process.stdout)
    process = subprocess.run([sys.executable, '-m', 'experiments.g93_semantic_types', '--replay', str(candidate)],
                             cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': '1'}, capture_output=True,
                             text=True, timeout=45, check=True)
    child = json.loads(process.stdout)
    evaluation_cpu += time.process_time()-start+compacted['cpu_s']+child['cpu_s']
    controls = {'disabled_exact': disabled['response_sha256'] == baseline['response_sha256'],
                'direct_exact': restored['response_sha256'] == results['removed']['response_sha256'],
                'reload_exact': child['result'] is not None and child['result']['response_sha256'] == results['semantic']['response_sha256']}
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(child['peak_rss_kib'], compacted['peak_rss_kib']))
    total_cpu = time.process_time()-cpu0+child['cpu_s']+compacted['cpu_s']
    primary = results['semantic']
    gates = {'useful_gain': primary['useful_core'] >= 368, 'absent': primary['quotes_without_data'] <= 73,
             'selection_gain': raw['semantic']['correct_first'] >= 491,
             'class_gain': all(primary['useful_core'] >= results[n]['useful_core']+17 for n in ('grammar', 'shuffled')),
             'literal': primary['nonliteral_evidence'] == 0, 'controls': all(controls.values()),
             'base_size': candidate.stat().st_size <= 100*1024**2,
             'latency': primary['p95_ms'] < 5 and primary['max_ms'] < 5,
             'budget': teaching_cpu <= 600 and evaluation_cpu <= 200 and total_cpu <= 800
                       and rss <= 1024**2 and time.monotonic()-wall0 <= 1000}
    assert fingerprint() == hashes
    acquisition = json.loads((ROOT/'results_v3/g93_source_manifest.json').read_text())
    report = {'experiment': 'G93', 'scope': 'spent business development; external semantic-class prototype; not production',
              'repository_engine_sha': ENGINE, 'effective_selector_reference': REFERENCE,
              'reference_sha256': REFERENCE_HASHES, 'sources_sha256': hashes, 'g84_models_sha256': G84_SHA,
              'base_sha256': BASE_SHA, 'education': education, 'fits': fits, 'candidates': results,
              'selection_without_abstention': raw, 'controls': controls, 'compaction': compacted, 'restart': child,
              'gates': gates, 'passes': all(gates.values()),
              'cost': {'teaching_cpu_s': teaching_cpu, 'evaluation_cpu_s': evaluation_cpu,
                       'preparation_included': preparation, 'total_cpu_s': total_cpu,
                       'wall_s': time.monotonic()-wall0, 'peak_rss_kib': rss,
                       'parent_rss_during_children_kib': parent_rss, 'models_bytes': model_path.stat().st_size,
                       'base_bytes': candidate.stat().st_size, 'source_cpu_s': acquisition['cpu_s'],
                       'source_wall_s': acquisition['wall_s'], 'previous_g84_cpu_s': old_report['cost']['total_cpu_s']}}
    (ROOT/'results_v3/g93_semantic_types.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
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
            (ROOT/'results_v3/g93_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

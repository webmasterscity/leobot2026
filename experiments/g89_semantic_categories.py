"""G89: existing TnT learner on human semantic sequence annotations."""
import ast
from collections import Counter, defaultdict
import gc
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import textwrap
import time

from leobot.context import _plain
from leobot.syntax import SyntaxMixin, _empty_syntax, _add
from experiments.g74_relation_coverage import ROOT, ENGINE


def sequence_observer():
    """Reuse exactly the count prefix, without inventing dependency labels."""
    original = ast.parse(textwrap.dedent(inspect.getsource(SyntaxMixin.observe_parsed_sentence))).body[0]
    start = next(i for i, node in enumerate(original.body) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'model' for t in node.targets))
    end = next(i for i, node in enumerate(original.body) if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'lowered' for t in node.targets))
    function = ast.parse('def observe_tags(self, words, tags):\n    pass\n').body[0]
    function.body = original.body[start:end]
    assert not any(isinstance(n, ast.Name) and n.id in ('heads', 'labels', 'feats', 'lemmas')
                   for item in function.body for n in ast.walk(item))
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    scope = {'_add': _add}
    exec(compile(module, 'leobot.syntax:sequence_count_prefix', 'exec'), scope)
    return scope['observe_tags']


observe_tags = sequence_observer()


def new_tagger(model=None):
    tagger = SyntaxMixin()
    tagger.syntax_model = _empty_syntax() if model is None else model
    return tagger


def read_data(name, manifest_path=ROOT/'results_v3/g89_source_manifest.json'):
    manifest = json.loads(Path(manifest_path).read_text())
    expected = next(f for f in manifest['files'] if f['name'] == name)
    compressed = (ROOT/'.leobot-data/g89'/name).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == expected['compressed_sha256']
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == expected['uncompressed_sha256']
    try:
        text, encoding = raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        text, encoding = raw.decode('latin-1'), 'latin-1'
    rows, words, tags = [], [], []
    for line in text.splitlines()+['']:
        if not line.strip():
            if words:
                rows.append((words, tags))
                words, tags = [], []
            continue
        fields = line.split()
        assert len(fields) >= 2
        word, tag = fields[0], fields[-1]
        assert tag == 'O' or tag.startswith(('B-', 'I-')) and len(tag) > 2
        assert '\x1f' not in word+tag
        words.append(word)
        tags.append(tag)
    return rows, {'name': name, 'encoding': encoding, 'sequences': len(rows),
                  'tokens': sum(len(w) for w, _ in rows),
                  'tags': dict(sorted(Counter(t for _, ts in rows for t in ts).items())),
                  'invalid_i_transitions': sum(invalid_i(ts) for _, ts in rows),
                  'sha256': expected['uncompressed_sha256']}


def invalid_i(tags):
    return sum(tag.startswith('I-') and (i == 0 or tags[i-1] not in ('B-'+tag[2:], 'I-'+tag[2:]))
               for i, tag in enumerate(tags))


def spans(tags):
    """Standard BIO evaluation: orphan I begins a span, labels stay unchanged."""
    found, start, label = set(), None, None
    for i, tag in enumerate(list(tags)+['O']):
        prefix, current = (tag.split('-', 1) if '-' in tag else ('O', None))
        if start is not None and (prefix != 'I' or current != label):
            found.add((start, i, label))
            start, label = None, None
        if prefix != 'O' and start is None:
            start, label = i, current
    return found


def learn(rows):
    tagger = new_tagger()
    for words, tags in rows:
        observe_tags(tagger, words, tags)
    tagger.consolidate_syntax()
    return tagger


def shuffle_sequences(rows):
    groups, labels = defaultdict(list), [None]*len(rows)
    for i, (words, _) in enumerate(rows):
        groups[len(words)].append(i)
    rng = random.Random(1)
    for _, indices in sorted(groups.items()):
        order = indices[:]
        rng.shuffle(order)
        for i, j in zip(indices, order):
            labels[i] = rows[j][1]
    return [(words, label) for (words, _), label in zip(rows, labels)]


def references(rows):
    vocabulary = {_plain(w) for words, _ in rows for w in words}
    entities = {tuple(_plain(w) for w in words[a:b]) for words, tags in rows for a, b, _ in spans(tags)}
    lexicon, totals = defaultdict(Counter), Counter()
    for words, tags in rows:
        for word, tag in zip(words, tags):
            lexicon[word][tag] += 1
            totals[tag] += 1
    baseline = {word: max(sorted(counts), key=counts.get) for word, counts in lexicon.items()}
    majority = max(sorted(totals), key=totals.get)
    return vocabulary, entities, baseline, majority


def prf(correct, predicted, gold):
    p, r = correct/max(1, predicted), correct/max(1, gold)
    return {'correct': correct, 'predicted': predicted, 'gold': gold, 'precision': p,
            'recall': r, 'f1': 2*correct/max(1, predicted+gold)}


def evaluate(predict, rows, vocabulary, entities, deadline):
    totals, per_class, unseen, novel_tokens = Counter(), defaultdict(Counter), Counter(), Counter()
    latencies, digest = [], hashlib.sha256()
    for words, gold_tags in rows:
        if time.process_time() > deadline:
            raise TimeoutError('G89 agotó evaluación')
        start = time.perf_counter()
        predicted_tags = predict(words)
        latencies.append((time.perf_counter()-start)*1000)
        assert len(predicted_tags) == len(gold_tags)
        digest.update(json.dumps(predicted_tags, separators=(',', ':')).encode()+b'\n')
        predicted, gold = spans(predicted_tags), spans(gold_tags)
        correct = predicted & gold
        totals.update(correct=len(correct), predicted=len(predicted), gold=len(gold),
                      tokens=len(words), correct_tokens=sum(a == b for a, b in zip(predicted_tags, gold_tags)),
                      invalid_i=invalid_i(predicted_tags))
        for key, collection in (('correct', correct), ('predicted', predicted), ('gold', gold)):
            for a, b, label in collection:
                per_class[label][key] += 1
                text = tuple(_plain(w) for w in words[a:b])
                if text not in entities:
                    unseen[key] += 1
                if any(w not in vocabulary for w in text):
                    novel_tokens[key] += 1
    summary = lambda counts: prf(counts['correct'], counts['predicted'], counts['gold'])
    times = sorted(latencies)
    return {'spans': summary(totals), 'token_accuracy': totals['correct_tokens']/totals['tokens'],
            'tokens': totals['tokens'], 'per_class': {key: summary(row) for key, row in sorted(per_class.items())},
            'unseen_entity_text': summary(unseen), 'entity_with_unseen_token': summary(novel_tokens),
            'invalid_i_predictions': totals['invalid_i'], 'prediction_sha256': digest.hexdigest(),
            'sequence_p50_ms': times[len(times)//2], 'sequence_p95_ms': times[int(.95*(len(times)-1))],
            'sequence_max_ms': max(times)}


def fingerprint():
    files = ('experiments/g89_semantic_categories.py', 'experiments/test_g89_semantic_categories.py',
             'leobot/syntax.py', 'results_v3/g89_source_manifest.json',
             'prereg/G-89-categorias-semanticas-con-aprendiz-existente.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G89 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    model = json.loads(Path(path).read_text())
    tagger = new_tagger(model)
    training, _ = read_data('esp.train.gz')
    vocabulary, entities, _, _ = references(training)
    dev, _ = read_data('esp.testa.gz')
    result = evaluate(tagger.tag_words, dev, vocabulary, entities, start+120)
    return {'result': result, 'cpu_s': time.process_time()-start,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (185, 190))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    training, source = read_data('esp.train.gz')
    shuffled = shuffle_sequences(training)
    vocabulary, entities, lexical, majority = references(training)
    models, teaching = {}, {}
    for name, rows in (('learned', training), ('shuffled', shuffled)):
        start = time.process_time()
        models[name] = learn(rows)
        teaching[name+'_cpu_s'] = time.process_time()-start
    teaching_cpu = time.process_time()-cpu0
    if teaching_cpu > 60:
        raise TimeoutError('G89 agotó enseñanza')
    path = ROOT/'.leobot-data/g89/model.json'
    path.write_text(json.dumps(models['learned'].syntax_model, ensure_ascii=False, separators=(',', ':')))
    teaching['total_cpu_s'] = teaching_cpu
    teaching['shuffled_token_labels_changed'] = sum(a != b for (_, ts), (_, us) in zip(training, shuffled) for a, b in zip(ts, us))
    (ROOT/'.leobot-data/g89/teaching.json').write_text(json.dumps({'source': source, 'cost': teaching}, indent=2))
    print(json.dumps({'stage': 'teaching', 'source': source, 'cost': teaching, 'model_bytes': path.stat().st_size}), flush=True)
    start_eval = time.process_time()
    dev, dev_info = read_data('esp.testa.gz')
    results = {}
    for name, predict in (('lexical', lambda words: [lexical.get(w, majority) for w in words]),
                          ('learned', models['learned'].tag_words), ('shuffled', models['shuffled'].tag_words)):
        start = time.process_time()
        results[name] = evaluate(predict, dev, vocabulary, entities, start_eval+120)
        results[name]['cpu_s'] = time.process_time()-start
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': results[name]}), flush=True)
    del models, training, shuffled, dev, vocabulary, entities, lexical, predict
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    process = subprocess.run([sys.executable, '-m', 'experiments.g89_semantic_categories', '--replay', str(path)],
                             cwd=ROOT, capture_output=True, text=True, check=True, timeout=90,
                             env={**os.environ, 'PYTHONHASHSEED': '1'})
    child = json.loads(process.stdout)
    evaluation_cpu = time.process_time()-start_eval+child['cpu_s']
    cost = {'teaching': teaching, 'evaluation_cpu_s': evaluation_cpu,
            'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
            'peak_rss_kib': max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib']),
            'parent_rss_during_child_kib': parent_rss, 'model_bytes': path.stat().st_size}
    learned = results['learned']
    gates = {'span_f1': learned['spans']['f1'] >= .65,
             'lexical_gain': learned['spans']['f1'] >= results['lexical']['spans']['f1']+.05,
             'shuffled_gain': learned['spans']['f1'] >= results['shuffled']['spans']['f1']+.10,
             'new_names': learned['unseen_entity_text']['recall'] >= .40 and learned['unseen_entity_text']['gold'] >= 100,
             'reload_exact': child['result']['prediction_sha256'] == learned['prediction_sha256'],
             'budget': teaching_cpu <= 60 and evaluation_cpu <= 120 and cost['total_cpu_s'] <= 180
                       and cost['wall_s'] <= 300 and cost['peak_rss_kib'] <= 512*1024}
    assert fingerprint() == hashes
    report = {'experiment': 'G89', 'scope': 'semantic sequence education; not QA performance or business transfer',
              'repository_engine_sha': ENGINE, 'sources_sha256': hashes,
              'source': source, 'development': dev_info, 'candidates': results,
              'restart': child, 'gates': gates, 'continue_to_qa_study': all(gates.values()), 'cost': cost}
    (ROOT/'results_v3/g89_semantic_categories.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': cost}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g89_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall,
                'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

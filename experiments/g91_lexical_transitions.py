"""G91: count-backed lexical context in the existing sequence decoder."""
from collections import Counter, defaultdict
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from leobot.syntax import SyntaxMixin
from experiments.g74_relation_coverage import ROOT, ENGINE
from experiments import g89_semantic_categories as g89
from experiments.g90_observed_transitions import MODEL_SHA


def count_contexts(rows):
    contexts = {}
    for words, tags in rows:
        previous_word, previous_tag = '<s>', '<s>'
        for word, tag in zip(words+['</s>'], tags+['</s>']):
            row = contexts.setdefault(previous_tag, {}).setdefault(previous_word, {})
            row[tag] = row.get(tag, 0)+1
            previous_word, previous_tag = word, tag
    return contexts


def shuffled_contexts(contexts):
    rng, result = random.Random(1), {}
    for tag, group in sorted(contexts.items()):
        words = sorted(group)
        rows = [group[word] for word in words]
        rng.shuffle(rows)
        result[tag] = dict(zip(words, rows))
    return result


class LexicalTagger(SyntaxMixin):
    def __init__(self, model, contexts, mode='lexical'):
        self.syntax_model, self.mode = model, mode
        self.contexts = {tag: {word: (sum(row.values()), row) for word, row in group.items()}
                         for tag, group in contexts.items()}
        self.erased = {}
        for tag, group in contexts.items():
            row = Counter()
            for counts in group.values():
                row.update(counts)
            self.erased[tag] = (sum(row.values()), dict(row))
        self.active_words, self.position, self.previous_word = None, 0, None
        self.observed_calls = self.unseen_calls = 0

    def _emissions(self, word):
        if self.active_words is not None:
            self.previous_word = self.active_words[self.position-1] if self.position else '<s>'
            self.position += 1
        return super()._emissions(word)

    def _transition(self, t1, t2, t3):
        original = super()._transition(t1, t2, t3)
        if self.mode == 'disabled' or self.active_words is None:
            return original
        word = (self.active_words[-1] if self.active_words else '<s>') if t3 == '</s>' else self.previous_word
        row = self.erased.get(t2) if self.mode == 'erased' else self.contexts.get(t2, {}).get(word)
        if row is None:
            self.unseen_calls += 1
            return original
        self.observed_calls += 1
        n, counts = row
        return math.log((counts.get(t3, 0)+8*math.exp(original))/(n+8))

    def tag_words(self, words):
        self.active_words, self.position = list(words), 0
        try:
            return super().tag_words(words)
        finally:
            self.active_words, self.position, self.previous_word = None, 0, None


def fingerprint():
    files = ('experiments/g91_lexical_transitions.py', 'experiments/test_g91_lexical_transitions.py',
             'experiments/g90_observed_transitions.py', 'experiments/g89_semantic_categories.py',
             'leobot/syntax.py', 'results_v3/g89_source_manifest.json',
             'prereg/G-91-contexto-lexico-en-transiciones.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G91 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    packet = json.loads(Path(path).read_text())
    tagger = LexicalTagger(packet['syntax'], packet['contexts'])
    training, _ = g89.read_data('esp.train.gz')
    vocabulary, entities, _, _ = g89.references(training)
    dev, _ = g89.read_data('esp.testa.gz')
    result = g89.evaluate(tagger.tag_words, dev, vocabulary, entities, start+60)
    return {'result': result, 'cpu_s': time.process_time()-start,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (72, 75))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    model_path = ROOT/'.leobot-data/g89/model.json'
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == MODEL_SHA
    model = json.loads(model_path.read_text())
    training, source = g89.read_data('esp.train.gz')
    vocabulary, entities, _, _ = g89.references(training)
    contexts = count_contexts(training)
    confused = shuffled_contexts(contexts)
    candidate = ROOT/'.leobot-data/g91/model.json'
    candidate.parent.mkdir(exist_ok=True)
    candidate.write_text(json.dumps({'syntax': model, 'contexts': contexts}, ensure_ascii=False, separators=(',', ':')))
    education = {'previous_tags': len(contexts), 'lexical_contexts': sum(map(len, contexts.values())),
                 'outcomes': sum(len(row) for group in contexts.values() for row in group.values()),
                 'shuffled_rows_changed': sum(group[word] != confused[tag][word] for tag, group in contexts.items() for word in group)}
    acquisition = time.process_time()-cpu0
    assert acquisition <= 10
    start_eval = time.process_time()
    dev, dev_info = g89.read_data('esp.testa.gz')
    results, usage = {}, {}
    def measured(name, tagger):
        start = time.process_time()
        result = g89.evaluate(tagger.tag_words, dev, vocabulary, entities, start_eval+60)
        result['cpu_s'] = time.process_time()-start
        results[name] = result
        usage[name] = {'observed': tagger.observed_calls, 'unseen': tagger.unseen_calls}
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result}), flush=True)
        return result
    baseline = measured('baseline', LexicalTagger(model, {}, 'disabled'))
    old = json.loads((ROOT/'results_v3/g89_semantic_categories.json').read_text())['candidates']['learned']
    assert baseline['prediction_sha256'] == old['prediction_sha256']
    learned_tagger = LexicalTagger(model, contexts)
    measured('learned', learned_tagger)
    measured('erased', LexicalTagger(model, contexts, 'erased'))
    measured('shuffled', LexicalTagger(model, confused))
    learned_tagger.mode = 'disabled'
    disabled = measured('disabled', learned_tagger)
    del learned_tagger, model, training, dev, vocabulary, entities
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    process = subprocess.run([sys.executable, '-m', 'experiments.g91_lexical_transitions', '--replay', str(candidate)],
                             cwd=ROOT, capture_output=True, text=True, check=True, timeout=45,
                             env={**os.environ, 'PYTHONHASHSEED': '1'})
    child = json.loads(process.stdout)
    evaluation_cpu = time.process_time()-start_eval+child['cpu_s']
    cost = {'reuse_and_education_cpu_s': acquisition, 'evaluation_cpu_s': evaluation_cpu,
            'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
            'peak_rss_kib': max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib']),
            'parent_rss_during_child_kib': parent_rss, 'model_bytes': candidate.stat().st_size}
    learned = results['learned']
    controls = {'baseline_exact': baseline['prediction_sha256'] == old['prediction_sha256'],
                'disabled_exact': disabled['prediction_sha256'] == baseline['prediction_sha256'],
                'reload_exact': child['result']['prediction_sha256'] == learned['prediction_sha256']}
    gates = {'span_f1': learned['spans']['f1'] >= .67,
             'baseline_gain': learned['spans']['f1'] >= baseline['spans']['f1']+.02,
             'context_gain': all(learned['spans']['f1'] >= results[m]['spans']['f1']+.01 for m in ('erased', 'shuffled')),
             'new_names': learned['unseen_entity_text']['recall'] >= .40 and learned['unseen_entity_text']['gold'] >= 100,
             'controls': all(controls.values()),
             'budget': acquisition <= 10 and evaluation_cpu <= 60 and cost['total_cpu_s'] <= 70
                       and cost['wall_s'] <= 100 and cost['peak_rss_kib'] <= 512*1024}
    assert fingerprint() == hashes
    report = {'experiment': 'G91', 'scope': 'count-backed lexical transitions; spent NER development; no QA claim',
              'repository_engine_sha': ENGINE, 'sources_sha256': hashes, 'g89_model_sha256': MODEL_SHA,
              'source': source, 'development': dev_info, 'education': education, 'transition_uses': usage,
              'candidates': results, 'controls': controls, 'restart': child,
              'gates': gates, 'continue_to_separate_check': all(gates.values()), 'cost': cost}
    (ROOT/'results_v3/g91_lexical_transitions.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'education': education, 'cost': cost}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g91_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall,
                'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

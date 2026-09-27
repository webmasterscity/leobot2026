"""G90: generic support of label transitions learned from G89 counts."""
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

MODEL_SHA = '7020a285adf4c9673c89ad0379f24735ca766d2f0da239e299113391f238d140'


def support(model):
    return {tuple(pair.split('\x1f')) for pair, count in model['bigrams'].items() if count > 0}


class ConstrainedTagger(SyntaxMixin):
    def __init__(self, model, allowed):
        self.syntax_model, self.allowed, self.fallbacks = model, allowed, 0

    def _transition(self, t1, t2, t3):
        if self.allowed is not None and (t2, t3) not in self.allowed:
            return -math.inf
        return super()._transition(t1, t2, t3)

    def tag_words(self, words):
        result = super().tag_words(words)
        if self.allowed is None:
            return result
        path = ['<s>']+result+['</s>']
        if all(pair in self.allowed for pair in zip(path, path[1:])):
            return result
        self.fallbacks += 1
        previous = self.allowed
        try:
            self.allowed = None
            return super().tag_words(words)
        finally:
            self.allowed = previous


def fingerprint():
    files = ('experiments/g90_observed_transitions.py', 'experiments/test_g90_observed_transitions.py',
             'experiments/g89_semantic_categories.py', 'leobot/syntax.py',
             'results_v3/g89_source_manifest.json', 'prereg/G-90-transiciones-admitidas-por-los-datos.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G90 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay(path):
    start = time.process_time()
    packet = json.loads(Path(path).read_text())
    tagger = ConstrainedTagger(packet['syntax'], {tuple(pair) for pair in packet['allowed']})
    training, _ = g89.read_data('esp.train.gz')
    vocabulary, entities, _, _ = g89.references(training)
    dev, _ = g89.read_data('esp.testa.gz')
    result = g89.evaluate(tagger.tag_words, dev, vocabulary, entities, start+50)
    return {'result': result, 'fallbacks': tagger.fallbacks, 'cpu_s': time.process_time()-start,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (62, 65))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    model_path = ROOT/'.leobot-data/g89/model.json'
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == MODEL_SHA
    model = json.loads(model_path.read_text())
    allowed = support(model)
    tags = sorted(t for t in model['tags'] if t != '</s>')
    permuted = tags[:]
    random.Random(1).shuffle(permuted)
    mapping = dict(zip(tags, permuted))
    confused = {(mapping.get(a, a), mapping.get(b, b)) for a, b in sorted(allowed)}
    training, source = g89.read_data('esp.train.gz')
    vocabulary, entities, lexical, majority = g89.references(training)
    candidate = ROOT/'.leobot-data/g90/model.json'
    candidate.parent.mkdir(exist_ok=True)
    candidate.write_text(json.dumps({'syntax': model, 'allowed': sorted(allowed)}, ensure_ascii=False, separators=(',', ':')))
    acquisition = time.process_time()-cpu0
    assert acquisition <= 10
    start_eval = time.process_time()
    dev, dev_info = g89.read_data('esp.testa.gz')
    results, tagger = {}, None
    def measured(name, predict):
        start = time.process_time()
        result = g89.evaluate(predict, dev, vocabulary, entities, start_eval+50)
        result['cpu_s'] = time.process_time()-start
        results[name] = result
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result}), flush=True)
        return result
    baseline = measured('baseline', g89.new_tagger(model).tag_words)
    old = json.loads((ROOT/'results_v3/g89_semantic_categories.json').read_text())['candidates']
    assert baseline['prediction_sha256'] == old['learned']['prediction_sha256']
    measured('lexical', lambda words: [lexical.get(w, majority) for w in words])
    assert results['lexical']['prediction_sha256'] == old['lexical']['prediction_sha256']
    fallbacks = {}
    for name, mask in (('learned', allowed), ('shuffled', confused)):
        tagger = ConstrainedTagger(model, mask)
        measured(name, tagger.tag_words)
        fallbacks[name] = tagger.fallbacks
    tagger.allowed = None
    disabled = measured('disabled', tagger.tag_words)
    del tagger, model, training, dev, vocabulary, entities, lexical
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    process = subprocess.run([sys.executable, '-m', 'experiments.g90_observed_transitions', '--replay', str(candidate)],
                             cwd=ROOT, capture_output=True, text=True, check=True, timeout=45,
                             env={**os.environ, 'PYTHONHASHSEED': '1'})
    child = json.loads(process.stdout)
    evaluation_cpu = time.process_time()-start_eval+child['cpu_s']
    cost = {'reuse_and_support_cpu_s': acquisition, 'evaluation_cpu_s': evaluation_cpu,
            'total_cpu_s': time.process_time()-cpu0+child['cpu_s'], 'wall_s': time.monotonic()-wall0,
            'peak_rss_kib': max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib']),
            'parent_rss_during_child_kib': parent_rss, 'model_bytes': candidate.stat().st_size}
    learned = results['learned']
    controls = {'baseline_exact': baseline['prediction_sha256'] == old['learned']['prediction_sha256'],
                'disabled_exact': disabled['prediction_sha256'] == baseline['prediction_sha256'],
                'reload_exact': child['result']['prediction_sha256'] == learned['prediction_sha256']}
    gates = {'span_f1': learned['spans']['f1'] >= .65,
             'baseline_gain': learned['spans']['f1'] >= baseline['spans']['f1']+.01,
             'shuffled_gain': learned['spans']['f1'] >= results['shuffled']['spans']['f1']+.01,
             'lexical_gain': learned['spans']['f1'] >= results['lexical']['spans']['f1']+.05,
             'new_names': learned['unseen_entity_text']['recall'] >= .40 and learned['unseen_entity_text']['gold'] >= 100,
             'controls': all(controls.values()),
             'budget': acquisition <= 10 and evaluation_cpu <= 50 and cost['total_cpu_s'] <= 60
                       and cost['wall_s'] <= 90 and cost['peak_rss_kib'] <= 512*1024}
    assert fingerprint() == hashes
    report = {'experiment': 'G90', 'scope': 'learned transition support; spent NER development; no QA claim',
              'repository_engine_sha': ENGINE, 'sources_sha256': hashes, 'g89_model_sha256': MODEL_SHA,
              'source': source, 'development': dev_info, 'allowed_edges': len(allowed),
              'shuffled_edges_changed': len(confused-allowed), 'fallbacks': fallbacks,
              'candidates': results, 'controls': controls, 'restart': child,
              'gates': gates, 'continue_to_separate_check': all(gates.values()), 'cost': cost}
    (ROOT/'results_v3/g90_observed_transitions.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'fallbacks': fallbacks, 'cost': cost}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        print(json.dumps(replay(sys.argv[2])))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g90_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall,
                'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

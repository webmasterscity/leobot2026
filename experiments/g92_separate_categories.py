"""G92: unchanged G91 model on the previously unopened public test split."""
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from experiments.g74_relation_coverage import ROOT, ENGINE
from experiments import g89_semantic_categories as g89
from experiments.g91_lexical_transitions import LexicalTagger, shuffled_contexts


MODEL_SHA = '3dcf0406c1a3bd512643c0fb0cbda2e56d419007d7f81ab0cf5960317af1f6e2'
MODEL_PATH = ROOT/'.leobot-data/g91/model.json'
MANIFEST = ROOT/'results_v3/g92_source_manifest.json'


def packet():
    raw = MODEL_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MODEL_SHA
    return json.loads(raw)


def fingerprint():
    files = ('experiments/g92_separate_categories.py', 'experiments/test_g92_separate_categories.py',
             'experiments/g91_lexical_transitions.py', 'experiments/g89_semantic_categories.py',
             'leobot/syntax.py', 'results_v3/g89_source_manifest.json',
             'results_v3/g92_source_manifest.json', 'prereg/G-92-comprobacion-separada-de-categorias.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G92 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def replay():
    start = time.process_time()
    data = packet()
    tagger = LexicalTagger(data['syntax'], data['contexts'])
    training, _ = g89.read_data('esp.train.gz')
    vocabulary, entities, _, _ = g89.references(training)
    separate, _ = g89.read_data('esp.testb.gz', manifest_path=MANIFEST)
    result = g89.evaluate(tagger.tag_words, separate, vocabulary, entities, start+60)
    return {'result': result, 'cpu_s': time.process_time()-start,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (72, 75))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    data = packet()
    model, contexts = data['syntax'], data['contexts']
    training, source = g89.read_data('esp.train.gz')
    vocabulary, entities, _, _ = g89.references(training)
    dev, _ = g89.read_data('esp.testa.gz')
    old_g89 = json.loads((ROOT/'results_v3/g89_semantic_categories.json').read_text())
    old_g91 = json.loads((ROOT/'results_v3/g91_lexical_transitions.json').read_text())
    verification = {}
    for name, tagger, expected in (
            ('baseline', g89.new_tagger(model), old_g89['candidates']['learned']),
            ('learned', LexicalTagger(model, contexts), old_g91['candidates']['learned'])):
        result = g89.evaluate(tagger.tag_words, dev, vocabulary, entities, cpu0+10)
        verification[name] = result['prediction_sha256'] == expected['prediction_sha256']
        assert verification[name], 'Predicciones previas cambiaron; testb permanece cerrado'
    verification_cpu = time.process_time()-cpu0
    assert verification_cpu <= 10
    print(json.dumps({'stage': 'prior_predictions_verified', 'controls': verification,
                      'cpu_s': verification_cpu}), flush=True)
    start_eval = time.process_time()
    separate, separate_info = g89.read_data('esp.testb.gz', manifest_path=MANIFEST)
    results = {}
    for name, tagger in (
            ('baseline', g89.new_tagger(model)),
            ('learned', LexicalTagger(model, contexts)),
            ('erased', LexicalTagger(model, contexts, 'erased')),
            ('shuffled', LexicalTagger(model, shuffled_contexts(contexts)))):
        start = time.process_time()
        result = g89.evaluate(tagger.tag_words, separate, vocabulary, entities, start_eval+60)
        result['cpu_s'] = time.process_time()-start
        results[name] = result
        print(json.dumps({'stage': 'measured', 'mode': name, 'result': result}), flush=True)
    del data, model, contexts, training, dev, separate, vocabulary, entities, tagger
    gc.collect()
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    process = subprocess.run([sys.executable, '-m', 'experiments.g92_separate_categories', '--replay'],
                             cwd=ROOT, capture_output=True, text=True, check=True, timeout=45,
                             env={**os.environ, 'PYTHONHASHSEED': '1'})
    child = json.loads(process.stdout)
    evaluation_cpu = time.process_time()-start_eval+child['cpu_s']
    acquisition = json.loads(MANIFEST.read_text())
    cost = {'source_acquisition_cpu_s': acquisition['cpu_s'],
            'source_acquisition_wall_s': acquisition['wall_s'],
            'reuse_and_verification_cpu_s': verification_cpu, 'evaluation_cpu_s': evaluation_cpu,
            'total_cpu_s': time.process_time()-cpu0+child['cpu_s']+acquisition['cpu_s'],
            'wall_s': time.monotonic()-wall0,
            'peak_rss_kib': max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, parent_rss+child['peak_rss_kib']),
            'parent_rss_during_child_kib': parent_rss, 'model_bytes': MODEL_PATH.stat().st_size,
            'previous_experiments_cpu_s': {'G89': old_g89['cost']['total_cpu_s'], 'G91': old_g91['cost']['total_cpu_s']}}
    learned = results['learned']
    verification['reload_exact'] = child['result']['prediction_sha256'] == learned['prediction_sha256']
    gates = {'span_f1': learned['spans']['f1'] >= .67,
             'baseline_gain': learned['spans']['f1'] >= results['baseline']['spans']['f1']+.02,
             'context_gain': all(learned['spans']['f1'] >= results[m]['spans']['f1']+.01 for m in ('erased', 'shuffled')),
             'new_names': learned['unseen_entity_text']['recall'] >= .40 and learned['unseen_entity_text']['gold'] >= 100,
             'controls': all(verification.values()),
             'budget': acquisition['wall_s'] <= 30 and verification_cpu <= 10 and evaluation_cpu <= 60
                       and cost['total_cpu_s'] <= 70 and cost['wall_s'] <= 100 and cost['peak_rss_kib'] <= 512*1024}
    assert fingerprint() == hashes
    report = {'experiment': 'G92', 'scope': 'unchanged model on previously unused public NER test; no QA claim',
              'repository_engine_sha': ENGINE, 'sources_sha256': hashes, 'model_sha256': MODEL_SHA,
              'source': source, 'separate_test': separate_info, 'candidates': results,
              'controls': verification, 'restart': child, 'gates': gates,
              'continue_to_qa_study': all(gates.values()), 'cost': cost}
    (ROOT/'results_v3/g92_separate_categories.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'gates': gates, 'cost': cost}), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--replay']:
        print(json.dumps(replay()))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g92_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall,
                'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'child_stderr': getattr(error, 'stderr', None)}, indent=2)+'\n')
            raise

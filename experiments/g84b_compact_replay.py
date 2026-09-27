"""Transport check only: preserve G84's learned values and all quality failures."""
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from experiments.g74_relation_coverage import ROOT


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def compact(source, destination):
    start = time.process_time()
    source_sha = digest(source)
    with source.open() as stream:
        data = json.load(stream)
    original_keys = list(data)
    with destination.open('w') as stream:
        json.dump(data, stream, ensure_ascii=False, separators=(',', ':'))
    del data
    gc.collect()
    with destination.open() as stream:
        reloaded = json.load(stream)
    same_keys = original_keys == list(reloaded)
    del reloaded
    return {'source_sha256': source_sha, 'source_unchanged': digest(source) == source_sha,
            'compact_sha256': digest(destination), 'source_bytes': source.stat().st_size,
            'compact_bytes': destination.stat().st_size, 'same_top_level_keys': same_keys,
            'cpu_s': time.process_time()-start, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    start_cpu, start_wall = time.process_time(), time.monotonic()
    source, destination = ROOT/'.leobot-data/g84_candidate.json', ROOT/'.leobot-data/g84_candidate_compact.json'
    files = ('experiments/g84b_compact_replay.py', 'experiments/g84_indirect_alignment.py',
             'prereg/G-84b-reinicio-con-archivo-compacto.md')
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--', *files], cwd=ROOT)
    hashes = {p: digest(ROOT/p) for p in files}
    parent_rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
    first = subprocess.run([sys.executable, '-m', 'experiments.g84b_compact_replay', '--compact', str(source), str(destination)],
                           cwd=ROOT, capture_output=True, text=True, timeout=40, check=True)
    compacted = json.loads(first.stdout)
    second = subprocess.run([sys.executable, '-m', 'experiments.g84_indirect_alignment', '--replay', str(destination)],
                            cwd=ROOT, capture_output=True, text=True, timeout=40, check=True,
                            env={**os.environ, 'PYTHONHASHSEED': '1'})
    replayed = json.loads(second.stdout)
    original = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              parent_rss+max(compacted['peak_rss_kib'], replayed['peak_rss_kib']))
    cost = {'cpu_s': time.process_time()-start_cpu+compacted['cpu_s']+replayed['cpu_s'],
            'wall_s': time.monotonic()-start_wall, 'peak_rss_kib': rss}
    result = replayed['result']
    gates = {'file_fits_existing_limit': compacted['compact_bytes'] <= 100*1024**2,
             'source_unchanged': compacted['source_unchanged'], 'top_level_keys': compacted['same_top_level_keys'],
             'responses_exact': result is not None and result['response_sha256'] == original['candidates']['indirect']['response_sha256'],
             'literal': result is not None and result['nonliteral_evidence'] == 0,
             'budget': cost['cpu_s'] <= 60 and cost['wall_s'] <= 90 and cost['peak_rss_kib'] <= 1024**2}
    assert {p: digest(ROOT/p) for p in files} == hashes
    report = {'experiment': 'G84b', 'scope': 'serialization and replay only; G84 quality gates remain failed',
              'sources_sha256': hashes, 'compaction': compacted, 'replay': replayed,
              'original_quality_gates': original['gates'], 'transport_gates': gates,
              'transport_passes': all(gates.values()), 'promotable': False, 'cost': cost}
    (ROOT/'results_v3/g84b_compact_replay.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--compact':
        print(json.dumps(compact(Path(sys.argv[2]), Path(sys.argv[3]))))
    else:
        start_cpu, start_wall = time.process_time(), time.monotonic()
        try:
            main()
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            (ROOT/'results_v3/g84b_interruption.json').write_text(json.dumps({
                'error': repr(error), 'cpu_s': time.process_time()-start_cpu+children.ru_utime+children.ru_stime,
                'wall_s': time.monotonic()-start_wall, 'child_stderr': getattr(error, 'stderr', None),
            }, ensure_ascii=False, indent=2)+'\n')
            raise

"""Bounded, pinned public assets for the explicitly authorized G97 experiment."""
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.leobot-data/g97'
MODEL_REV = '657e078c94084481950a2d555a941481f715536b'
CPP_REV = '4da6337767f973e2b4d0797e5b323d77d8565e4a'


def main():
    start, wall = time.process_time(), time.monotonic()
    OUT.mkdir(exist_ok=True)
    manifest = {'model_revision': MODEL_REV, 'executor_revision': CPP_REV, 'files': []}
    sources = (
        ('model.gguf', f'https://huggingface.co/LiquidAI/LFM2.5-350M-GGUF/resolve/{MODEL_REV}/LFM2.5-350M-Q4_K_M.gguf'),
        ('LFM-LICENSE.txt', f'https://huggingface.co/LiquidAI/LFM2.5-350M-GGUF/resolve/{MODEL_REV}/LICENSE'),
        ('llama.cpp.tar.gz', f'https://codeload.github.com/ggml-org/llama.cpp/tar.gz/{CPP_REV}'))
    total = 0
    try:
        for name, url in sources:
            path = OUT/name
            if path.exists():
                raise RuntimeError(f'Existing unverified acquisition: {path}')
            h, size, begin = hashlib.sha256(), 0, time.monotonic()
            with urllib.request.urlopen(url, timeout=60) as response, path.open('wb') as stream:
                while chunk := response.read(1024*1024):
                    total += len(chunk)
                    if total > 600*1024**2 or time.monotonic()-wall > 1200:
                        raise TimeoutError('G97 acquisition budget')
                    h.update(chunk); stream.write(chunk); size += len(chunk)
            record = {'file': str(path.relative_to(ROOT)), 'url': url, 'bytes': size,
                      'sha256': h.hexdigest(), 'wall_s': time.monotonic()-begin}
            manifest['files'].append(record)
            print(json.dumps(record), flush=True)
        with (OUT/'model.gguf').open('rb') as f:
            assert f.read(4) == b'GGUF'
        with tarfile.open(OUT/'llama.cpp.tar.gz') as archive:
            archive.extractall(OUT, filter='data')
        source = OUT/f'llama.cpp-{CPP_REV}'
        build = OUT/'build'
        configure = ['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
                     '-DCMAKE_BUILD_TYPE=Release', '-DGGML_NATIVE=ON', '-DGGML_CUDA=OFF',
                     '-DLLAMA_CURL=OFF', '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF',
                     '-DLLAMA_BUILD_SERVER=OFF', '-DLLAMA_BUILD_TOOLS=OFF']
        with (OUT/'build.log').open('w') as log:
            subprocess.run(configure, stdout=log, stderr=subprocess.STDOUT, timeout=60, check=True)
            subprocess.run(['cmake', '--build', str(build), '--target', 'llama', '-j', '2'],
                           stdout=log, stderr=subprocess.STDOUT,
                           timeout=max(1, 1200-(time.monotonic()-wall)), check=True)
        manifest['executor_source'] = str(source.relative_to(ROOT))
        manifest['compiled'] = True
    except Exception as exc:
        manifest['error'] = repr(exc)
        raise
    finally:
        child = resource.getrusage(resource.RUSAGE_CHILDREN)
        manifest['cpu_s'] = time.process_time()-start+child.ru_utime+child.ru_stime
        manifest['wall_s'] = time.monotonic()-wall
        manifest['child_peak_rss_kib'] = child.ru_maxrss
        manifest['cpu_budget_met'] = manifest['cpu_s'] <= 1200
        (ROOT/'results_v3/g97_acquisition.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()

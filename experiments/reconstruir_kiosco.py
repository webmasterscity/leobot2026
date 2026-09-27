"""Reconstruye la educación estable y guarda sus fuentes fuera de /tmp.

python3 -m experiments.reconstruir_kiosco /ruta/corpus_ud .leobot-data
Cada etapa tiene un límite. No cambia el motor ni usa material reservado nuevo.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from experiments.agi_board import MLQA_ARCHIVE_SHA, MLQA_URL
from experiments.base_educada import SQUAD_TRAIN_SHA, SQUAD_TRAIN_URL
from experiments.g57_educar_kiosco import MFAQ_SHA, MFAQ_URL


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url, path, expected):
    if not path.exists() or sha(path) != expected:
        temporary = path.with_suffix(path.suffix+'.part')
        try:
            with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as target:
                while chunk := source.read(1024*1024):
                    target.write(chunk)
            if sha(temporary) != expected:
                raise RuntimeError(f'La fuente cambió: {url}')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'url': url, 'sha256': expected, 'file': str(path)}


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Uso: python3 -m experiments.reconstruir_kiosco ANCORA_DIR DESTINO')
    root = Path(__file__).resolve().parents[1]
    corpus, out = (Path(p).resolve() for p in sys.argv[1:])
    out.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for name in ('es_ancora-ud-train.conllu', 'es_coser-ud-train.conllu'):
        path = corpus/name
        inputs[name] = {'file': str(path), 'sha256': sha(path)}
    for name, url, digest in (('mfaq_es_train.jsonl', MFAQ_URL, MFAQ_SHA),
                              ('squad_es_train_v1.1.json', SQUAD_TRAIN_URL, SQUAD_TRAIN_SHA),
                              ('leobot_mlqa_v1.zip', MLQA_URL, MLQA_ARCHIVE_SHA)):
        inputs[name] = fetch(url, out/name, digest)
    banks = ['congelado', 'congelado_g58', 'congelado_g59', 'congelado_g60', 'congelado_g61', 'desarrollo']
    environment = dict(os.environ, PYTHONHASHSEED='0', MLQA_CACHE=str(out/'leobot_mlqa_v1.zip'),
                       SQUAD_TRAIN_CACHE=str(out/'squad_es_train_v1.1.json'),
                       CONFIANZA_CITA='0.4', CONFIANZA_BANCOS=','.join('results_v3/kiosco/'+b for b in banks))
    stages = [
        ('base_educada', [str(corpus), str(out/'base_general.json')], 900),
        ('g57_educar_kiosco', [str(out/'base_general.json'), str(out/'base_mfaq.json'),
                               str(out/'mfaq_es_train.jsonl'), '--sin-contraste'], 180),
        ('g57_calibrar_kiosco', [str(out/'base_mfaq.json'), str(out/'base_calibrada.json'),
                                *('results_v3/kiosco/desarrollo/'+c for c in 'ABCD')], 180),
        ('g60_calibrar_confianza', [str(out/'base_calibrada.json'), str(out/'base_kiosco.json')], 180),
    ]
    report = {'python': sys.version, 'inputs': inputs, 'stages': [], 'engine': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD:leobot'], cwd=root, text=True).strip()}
    for module, args, limit in stages:
        begin = time.monotonic()
        result = subprocess.run([sys.executable, '-m', 'experiments.'+module, *args], cwd=root,
                                env=environment, timeout=limit, capture_output=True, text=True, check=True)
        report['stages'].append({'module': module, 'seconds': time.monotonic()-begin,
                                  'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()})
        print(module, result.stdout.strip(), flush=True)
    report['base'] = {'file': str(out/'base_kiosco.json'), 'sha256': sha(out/'base_kiosco.json')}
    (out/'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('Base guardada:', out/'base_kiosco.json', flush=True)


if __name__ == '__main__':
    main()

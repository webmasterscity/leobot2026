"""Inspect the original Spanish AnCora sources; no operational learning."""
from __future__ import annotations

import json
import resource
import ssl
import sys
import time
import zipfile
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.leobot-data/g73'
SOURCES = {
    'corpus': 'https://clic.ub.edu/corpus/system/files/2022-01/ancora-3.0.1es_1.zip',
    'lexicon': 'https://clic.ub.edu/corpus/system/files/2022-01/ancoralex-es-2.0.3.zip',
}


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in SOURCES.items():
        path = CACHE / (name + '.zip')
        if path.exists():
            raise RuntimeError('No sobrescribir una fuente existente')
        begin, cpu0 = time.monotonic(), time.process_time()
        attempts, raw = [], b''
        for verify in (True, False):
            try:
                context = ssl.create_default_context() if verify else ssl._create_unverified_context()
                with urlopen(url, timeout=20, context=context) as response:
                    length = int(response.headers.get('Content-Length', 0))
                    if length > 64 * 1024**2:
                        raise RuntimeError('Fuente demasiado grande')
                    pieces, size = [], 0
                    while chunk := response.read(1024 * 1024):
                        pieces.append(chunk)
                        size += len(chunk)
                        if size > 64 * 1024**2 or time.monotonic() - begin > 120:
                            raise RuntimeError('Presupuesto de descarga agotado')
                    raw = b''.join(pieces)
                    final_url = response.url
                attempts.append({'tls_verified': verify, 'ok': True})
                break
            except URLError as exc:
                attempts.append({'tls_verified': verify, 'ok': False, 'error': str(exc)})
                if not verify or not isinstance(exc.reason, ssl.SSLCertVerificationError):
                    raise
        if not raw:
            raise RuntimeError('Fuente vacía')
        path.write_bytes(raw)
        with zipfile.ZipFile(path) as archive:
            validate_archive(archive)
        manifest[name] = {'url': url, 'final_url': final_url, 'bytes': len(raw),
                          'sha256': sha256(raw).hexdigest(), 'attempts': attempts,
                          'cpu_s': time.process_time() - cpu0,
                          'wall_s': time.monotonic() - begin}
        print(json.dumps({name: manifest[name]}), flush=True)
        # Retain successful acquisition information if the next download fails.
        (CACHE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def validate_archive(archive):
    entries = archive.infolist()
    if len(entries) > 20_000 or sum(e.file_size for e in entries) > 512 * 1024**2:
        raise RuntimeError('Presupuesto de archivo expandido agotado')
    for entry in entries:
        if entry.filename.endswith('.xml') and entry.file_size > 5 * 1024**2:
            raise RuntimeError('XML demasiado grande')


def checked_archive(name):
    manifest = json.loads((CACHE / 'manifest.json').read_text())[name]
    path = CACHE / (name + '.zip')
    if sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
        raise RuntimeError('La fuente cambió después de descargar')
    archive = zipfile.ZipFile(path)
    validate_archive(archive)
    return archive


def schema():
    report = {}
    for name in SOURCES:
        with checked_archive(name) as archive:
            files = sorted(n for n in archive.namelist() if n.endswith('.xml') and '__MACOSX' not in n)
            groups = defaultdict(list)
            for path in files:
                groups[str(Path(path).parent)].append(path)
            samples = []
            for directory, paths in groups.items():
                if len(samples) >= 12:
                    break
                for path in paths[:2]:
                    tree = ET.fromstring(archive.read(path))
                    attrs, tags, examples = defaultdict(set), Counter(), {}
                    for node in tree.iter():
                        tags[node.tag] += 1
                        attrs[node.tag].update(node.attrib)
                        # Only format/annotation values, never sentences or examples.
                        for key, value in node.attrib.items():
                            if key in ('type', 'arg', 'argument', 'thematicrole', 'thematic_role',
                                       'denotation', 'iarg', 'sem', 'sense', 'predicate', 'class'):
                                examples.setdefault(key, set()).add(value)
                    samples.append({'path': path, 'tags': dict(tags),
                                    'attributes': {k: sorted(v) for k, v in attrs.items()},
                                    'annotation_values': {k: sorted(v)[:20] for k, v in examples.items()}})
            report[name] = {'xml_files': len(files),
                            'directories': {k: len(v) for k, v in groups.items()}, 'samples': samples,
                            'license_files': [n for n in archive.namelist()
                                              if any(s in n.lower() for s in ('license', 'copying', 'readme'))]}
    path = ROOT / 'results_v3/g73_schema.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    {'download': download, 'schema': schema}[sys.argv[1]]()

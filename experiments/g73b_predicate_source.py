"""External acquisition/schema inspection of Predicate Matrix 1.3."""
import json
import resource
import sys
import tarfile
import time
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.leobot-data/g73b'
URL = 'https://adimen.ehu.eus/web/files/PredicateMatrix/PredicateMatrix.v1.3.tar.gz'


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / 'predicate_matrix.tar.gz'
    if path.exists():
        raise RuntimeError('No sobrescribir datos adquiridos')
    cpu0, wall0 = time.process_time(), time.monotonic()
    attempts = []
    raw = b''
    for _ in range(2):
        try:
            with urlopen(URL, timeout=20) as response:
                if int(response.headers.get('Content-Length', 0)) > 64 * 1024**2:
                    raise RuntimeError('Descarga supera 64 MiB')
                parts, size = [], 0
                while chunk := response.read(1024 * 1024):
                    parts.append(chunk)
                    size += len(chunk)
                    if size > 64 * 1024**2 or time.monotonic() - wall0 > 120:
                        raise RuntimeError('Presupuesto de descarga agotado')
                raw = b''.join(parts)
                final_url = response.url
            attempts.append({'ok': True, 'tls_verified': True})
            break
        except URLError as exc:
            attempts.append({'ok': False, 'error': str(exc), 'tls_verified': True})
    report = {'url': URL, 'attempts': attempts, 'available': bool(raw),
              'cpu_s': time.process_time() - cpu0, 'wall_s': time.monotonic() - wall0}
    if raw:
        path.write_bytes(raw)
        report.update(final_url=final_url, bytes=len(raw), sha256=sha256(raw).hexdigest())
    (ROOT / 'results_v3/g73b_download.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


def schema():
    meta = json.loads((ROOT / 'results_v3/g73b_download.json').read_text())
    path = CACHE / 'predicate_matrix.tar.gz'
    if sha256(path.read_bytes()).hexdigest() != meta['sha256']:
        raise RuntimeError('Cambio de fuente')
    total, members = 0, []
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            total += member.size
            if total > 512 * 1024**2 or len(members) >= 20_000:
                raise RuntimeError('Presupuesto de archivo expandido agotado')
            members.append({'name': member.name, 'bytes': member.size})
            if member.isfile():
                stream = archive.extractfile(member)
                # Read text documentation/header only; never extract or execute.
                preview = stream.read(min(member.size, 16000)).decode('utf8', 'replace')
                (CACHE / ('preview_' + str(len(members)) + '.txt')).write_text(preview)
                print(json.dumps({'member': member.name, 'bytes': member.size,
                                  'preview': preview[:10000]}))
    (ROOT / 'results_v3/g73b_members.json').write_text(json.dumps(members, indent=2) + '\n')


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    {'download': download, 'schema': schema}[sys.argv[1]]()

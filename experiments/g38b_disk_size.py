"""G-38b: disk file size, build and first-open time with 100 000 distinct atoms.

python3 -m experiments.g38b_disk_size ENGINE_ROOT OUT_DIR [MIGRATE_FROM_FILE]
Builds in OUT_DIR/kb.sqlite; with MIGRATE_FROM_FILE, copies that file and times
opening it (a one-time format migration when it comes from an older engine).
"""
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

N = 100_000


def main():
    sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
    import leobot
    from leobot.core import Atom
    from leobot.diskkb import SQLiteKnowledgeBase
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(3838)
    atoms = [Atom(rng.choice(('padre', 'vive', 'ama')), (f'e{rng.randrange(40_000)}', f'e{rng.randrange(40_000)}'))
             for _ in range(N)]
    path = out / 'kb.sqlite'
    for suffix in ('', '-wal', '-shm'):
        Path(str(path) + suffix).unlink(missing_ok=True)
    t = time.perf_counter()
    kb = SQLiteKnowledgeBase(path); kb.bulk_add(atoms, 'dataset')
    kb.db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); kb.close()
    report = {'engine': leobot.__file__, 'facts': N, 'build_s': round(time.perf_counter() - t, 2),
              'file_mib': round(os.path.getsize(path) / 2**20, 2)}
    if len(sys.argv) > 3:
        copy = out / 'migrated.sqlite'
        shutil.copy(sys.argv[3], copy)
        t = time.perf_counter(); kb = SQLiteKnowledgeBase(copy); kb.close()
        report['open_older_file_s'] = round(time.perf_counter() - t, 2)
        report['older_file_facts_after_open'] = SQLiteKnowledgeBase(copy).count_facts()
    print(json.dumps(report))


if __name__ == '__main__':
    main()

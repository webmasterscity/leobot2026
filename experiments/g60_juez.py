"""G-60: juez doble ciego (plan 3 del coordinador, propuesta 2).

python3 -m experiments.g60_juez preparar EVAL_DIR CARPETA_BANCO JUECES_DIR N_JUECES
python3 -m experiments.g60_juez desempate JUECES_DIR CARPETA_BANCO N_JUECES
python3 -m experiments.g60_juez reunir EVAL_DIR JUECES_DIR SALIDA.json

`preparar` escribe los mismos ítems, con el mismo reparto, en JUECES_DIR/A (jueces Opus) y JUECES_DIR/B (jueces
Sonnet 5).  `desempate` junta en JUECES_DIR/C los ítems en que A y B discrepan (un tercer juez Opus nuevo, que no ve
los dos veredictos).  `reunir`: vale el veredicto en que coinciden dos de los tres; si los tres difieren, el del medio
por gravedad.  Se informa el desacuerdo entre A y B.  Sistemas por `JUECES_SISTEMAS`/`JUECES_OTROS`, semilla por
`JUECES_SEMILLA` (como en G-58).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from experiments.g58_juez import REPORTED, auto_label, gates, prepare, rows_of

SEVERITY = {'correcta': 0, 'incompleta': 1, 'equivocada': 2, 'inventada': 3, 'util': 0, 'honesta': 1, 'enganosa': 2}


def verdicts_of(folder: Path) -> dict:
    out = {}
    for f in sorted(folder.glob('juez*/veredictos.json')):
        for v in json.loads(f.read_text(encoding='utf8')):
            out[v['id']] = v['veredicto']
    return out


def tiebreak(judges_dir: Path, bank: Path, n: int):
    a, b = verdicts_of(judges_dir / 'A'), verdicts_of(judges_dir / 'B')
    split = sorted(i for i in a if i in b and a[i] != b[i])
    items = {}
    for f in sorted((judges_dir / 'A').glob('juez*/items.json')):
        for it in json.loads(f.read_text(encoding='utf8')):
            items[it['id']] = it
    by_business = {}
    for i in split:
        by_business.setdefault(items[i]['negocio'], []).append(items[i])
    names = sorted(by_business)
    for j, group in enumerate([names[k::n] for k in range(n)]):
        if not group:
            continue
        folder = judges_dir / 'C' / f'juez{j + 1}'
        folder.mkdir(parents=True, exist_ok=True)
        mine = []
        for name in group:
            shutil.copytree(bank / name.replace('_', '/', 1), folder / name, dirs_exist_ok=True)
            mine += by_business[name]
        mine.sort(key=lambda x: (x['negocio'], x['id']))
        (folder / 'items.json').write_text(json.dumps(mine, ensure_ascii=False, indent=1), encoding='utf8')
        print(folder.name, len(group), 'negocios', len(mine), 'ítems')
    print('en desacuerdo', len(split), 'de', len(set(a) & set(b)))


def final(a: str, b: str, c: str | None) -> str:
    if a == b:
        return a
    if c in (a, b):
        return c
    labels = sorted((a, b, c), key=lambda x: SEVERITY.get(x, 0))
    return labels[1]


def collect(eval_dir: Path, judges_dir: Path, out: Path):
    key = json.loads((judges_dir / 'A' / 'clave.json').read_text())
    a, b, c = (verdicts_of(judges_dir / x) for x in ('A', 'B', 'C'))
    both = [i for i in key if i in a and i in b]
    verdicts = {}
    for i in both:
        k = key[i]
        verdicts[(k['negocio'], k['conv'], k['turno'], k['respuesta'])] = final(a[i], b[i], c.get(i))
    disagree = sum(a[i] != b[i] for i in both)
    report = {'juicios': len(verdicts), 'items': len(key), 'desacuerdo_A_B': f'{disagree}/{len(both)}',
              'desacuerdo_pct': round(100 * disagree / len(both), 1) if both else None,
              'sin_tercero': sum(1 for i in both if a[i] != b[i] and i not in c)}
    print(json.dumps(report, ensure_ascii=False))
    for system in REPORTED:
        path = eval_dir / f'{system}.json'
        if not path.exists():
            continue
        labels, missing = [], 0
        for row in rows_of(eval_dir, system):
            label = auto_label(row) or verdicts.get((row['negocio'], row['conv'], row['turno'], row['respuesta']))
            if label is None:
                missing += 1
                continue
            labels.append((row['tipo'], row['accion'], label, row))
        report[system] = {**gates(labels), 'sin_juicio': missing}
        print(system, json.dumps(report[system], ensure_ascii=False))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    if sys.argv[1] == 'preparar':
        for side in ('A', 'B'):
            prepare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]) / side, int(sys.argv[5]))
    elif sys.argv[1] == 'desempate':
        tiebreak(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]))
    else:
        collect(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))

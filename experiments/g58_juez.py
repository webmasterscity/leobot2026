"""G-58: juez ciego del banco congelado de G-58.

python3 -m experiments.g58_juez preparar EVAL_DIR CARPETA_BANCO JUECES_DIR N_JUECES
python3 -m experiments.g58_juez reunir EVAL_DIR JUECES_DIR SALIDA.json

Se juzgan, mezcladas y sin decir el sistema, las respuestas planas y las citas avisadas del tratamiento y las
distintas del tratamiento en sin_seguimiento, tabla_barajada y otro_negocio (misma respuesta al mismo turno: un solo
juicio).  «No lo sé», saludos y excepciones se califican solos.  Puertas del preregistro de G-58.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
from pathlib import Path

FROZEN = os.environ.get('JUECES_SEMILLA', '86684a218e4cc2cc2c13fdb0915fc5a281953b6f')
import os
JUDGED = tuple(os.environ.get('JUECES_SISTEMAS', 'tratamiento,sin_seguimiento,tabla_barajada,otro_negocio').split(','))
REPORTED = JUDGED + tuple(x for x in os.environ.get('JUECES_OTROS', 'sin_cercano,g57r,renombrado_estricto').split(',') if x)


def rows_of(eval_dir: Path, system: str) -> list[dict]:
    return json.loads((eval_dir / f'{system}.json').read_text(encoding='utf8'))['filas']


def auto_label(row):
    if row['estado'] == 'excepcion':
        return 'excepcion'
    if row['estado'] == 'phatic':
        return 'charla'
    if row['estado'] in ('unknown', 'literal_unknown') or str(row['respuesta']).lower().startswith('no lo s'):
        return 'abstencion_correcta' if row['accion'] in ('abstenerse', 'derivar') else 'abstencion_indebida'
    return None


def prepare(eval_dir: Path, bank: Path, judges_dir: Path, n: int):
    unique = {}
    for system in JUDGED:
        for row in rows_of(eval_dir, system):
            if auto_label(row) is None:
                unique.setdefault((row['negocio'], row['conv'], row['turno'], row['respuesta']), row)
    items = list(unique.values())
    random.Random(int(FROZEN[:8], 16)).shuffle(items)
    key = {}
    for k, it in enumerate(items):
        key[f'i{k:04d}'] = {'negocio': it['negocio'], 'conv': it['conv'], 'turno': it['turno'], 'respuesta': it['respuesta']}
    judges_dir.mkdir(parents=True, exist_ok=True)
    (judges_dir / 'clave.json').write_text(json.dumps(key, ensure_ascii=False, indent=1))
    by_business = {}
    for iid, k in key.items():
        by_business.setdefault(k['negocio'], []).append(iid)
    names = sorted(by_business)
    for j, group in enumerate([names[i::n] for i in range(n)]):
        folder = judges_dir / f'juez{j + 1}'
        folder.mkdir(exist_ok=True)
        mine = []
        for name in group:
            shutil.copytree(bank / name, folder / name.replace('/', '_'), dirs_exist_ok=True)
            from experiments.g57_kiosco import conversations_of
            convs = conversations_of(json.loads((bank / name / 'conversaciones.json').read_text(encoding='utf8')))
            for iid in by_business[name]:
                k = key[iid]
                turn = convs[k['conv']][k['turno']]
                mine.append({'id': iid, 'negocio': name.replace('/', '_'),
                             'turnos_previos_del_cliente': [t['cliente'] for t in convs[k['conv']][:k['turno']]],
                             'cliente': turn['cliente'], 'tipo': turn.get('tipo'), 'accion_esperada': turn.get('accion'),
                             'claves': turn.get('claves'), 'evidencia': turn.get('evidencia'),
                             'respuesta_ideal': turn.get('respuesta_ideal'), 'respuesta_a_calificar': k['respuesta']})
        mine.sort(key=lambda x: (x['negocio'], x['id']))
        (folder / 'items.json').write_text(json.dumps(mine, ensure_ascii=False, indent=1), encoding='utf8')
        print(folder.name, len(group), 'negocios', len(mine), 'ítems')


def gates(labels) -> dict:
    core = [l for t, a, l, _ in labels if t in ('directa', 'si_no') and a == 'responder']
    plain = [l for t, a, l, _ in labels if l in ('correcta', 'incompleta', 'equivocada', 'inventada')]
    quotes = [l for t, a, l, _ in labels if l in ('util', 'honesta', 'enganosa')]
    unans = [l for t, a, l, _ in labels if a in ('abstenerse', 'derivar')]
    echoes = sum(1 for t, a, l, row in labels if l == 'charla' and
                 (len(row['cliente'].split()) > 4 or any(c.isdigit() for c in row['cliente'])))
    count = {}
    for _, _, l, _ in labels:
        count[l] = count.get(l, 0) + 1
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    useful = sum(l in ('correcta', 'util') for l in core)
    return {'veredictos': dict(sorted(count.items())),
            'utiles_directa_si_no': f'{useful}/{len(core)}', 'utiles_pct': pct(useful, len(core)),
            'planas': len(plain), 'planas_error_pct': pct(sum(l in ('equivocada', 'inventada') for l in plain), len(plain)),
            'inventadas': count.get('inventada', 0), 'citas': len(quotes),
            'citas_enganosas_pct': pct(sum(l == 'enganosa' for l in quotes), len(quotes)),
            'citas_utiles_pct': pct(sum(l == 'util' for l in quotes), len(quotes)),
            'sin_respuesta_bien': f"{sum(l in ('abstencion_correcta', 'honesta', 'util') for l in unans)}/{len(unans)}",
            'sin_respuesta_bien_pct': pct(sum(l in ('abstencion_correcta', 'honesta', 'util') for l in unans), len(unans)),
            'eco_de_datos': echoes}


def collect(eval_dir: Path, judges_dir: Path, out: Path):
    key = json.loads((judges_dir / 'clave.json').read_text())
    verdicts = {}
    for f in sorted(p for p in judges_dir.glob('juez*/veredictos.json')):
        for v in json.loads(f.read_text(encoding='utf8')):
            k = key[v['id']]
            verdicts[(k['negocio'], k['conv'], k['turno'], k['respuesta'])] = v['veredicto']
    report = {'juicios': len(verdicts), 'items': len(key)}
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
        prepare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), int(sys.argv[5]))
    else:
        collect(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))

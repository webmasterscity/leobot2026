"""G-57: juez ciego del banco congelado.

python3 -m experiments.g57_juez preparar EVAL_DIR CARPETA_BANCO JUECES_DIR N_JUECES
python3 -m experiments.g57_juez reunir EVAL_DIR JUECES_DIR SALIDA.json

`preparar`: junta las respuestas de `contesta_siempre` (G-57 contestando siempre) y `estable_g15` que no son
abstenciones ni saludos, las baraja (semilla de `freeze-G-57`) sin decir qué sistema contestó, y reparte los
negocios entre N jueces (cada juez recibe los textos de sus negocios y sus ítems).  Las abstenciones se califican
solas: abstención correcta si la acción esperada es abstenerse o derivar; abstención indebida si no.
`reunir`: une los veredictos y calcula las puertas del preregistro para cada sistema (el tratamiento, que calla
siempre, se califica solo).
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

FROZEN = '80d543096ddb2be8a5c145fb175e9c769fe39952'
LABELS = ('correcta', 'abstencion_correcta', 'incompleta', 'equivocada', 'inventada', 'abstencion_indebida')
SYSTEMS = ('contesta_siempre', 'estable_g15', 'tratamiento')


def load_rows(eval_dir: Path, system: str) -> list[dict]:
    data = json.loads((eval_dir / f'{system}.json').read_text(encoding='utf8'))
    return data['filas'] if 'filas' in data else data['filas']


def abstained(row) -> bool:
    return row['estado'] in ('unknown', 'literal_unknown', 'unrecognized', 'ambiguous') or \
        str(row['respuesta']).lower().startswith('no lo s')


def auto_label(row):
    if row['accion'] == 'charla' or row['estado'] == 'phatic':
        return 'charla'
    if abstained(row):
        return 'abstencion_correcta' if row['accion'] in ('abstenerse', 'derivar') else 'abstencion_indebida'
    return None


def prepare(eval_dir: Path, bank: Path, judges_dir: Path, n: int):
    items = []
    for system in SYSTEMS[:2]:
        for row in load_rows(eval_dir, system):
            if auto_label(row) is None:
                items.append({'system': system, **row})
    rng = random.Random(int(FROZEN[:8], 16))
    rng.shuffle(items)
    for k, item in enumerate(items):
        item['id'] = f'i{k:04d}'
    key = {it['id']: {'system': it['system'], 'negocio': it['negocio'], 'conv': it['conv'], 'turno': it['turno']}
           for it in items}
    (judges_dir).mkdir(parents=True, exist_ok=True)
    (judges_dir / 'clave_sistemas.json').write_text(json.dumps(key, indent=1))
    names = sorted({it['negocio'] for it in items})
    groups = [names[i::n] for i in range(n)]
    for j, group in enumerate(groups):
        folder = judges_dir / f'juez{j + 1}'
        folder.mkdir(exist_ok=True)
        mine = []
        for name in group:
            src = bank / name
            dst = folder / name.replace('/', '_')
            shutil.copytree(src, dst, dirs_exist_ok=True)
            convs = json.loads((src / 'conversaciones.json').read_text(encoding='utf8'))
            for it in items:
                if it['negocio'] != name:
                    continue
                turn = convs[it['conv']][it['turno']]
                before = [t['cliente'] for t in convs[it['conv']][:it['turno']]]
                mine.append({'id': it['id'], 'negocio': name.replace('/', '_'), 'turnos_previos_del_cliente': before,
                             'cliente': turn['cliente'], 'tipo': turn.get('tipo'), 'accion_esperada': turn.get('accion'),
                             'claves': turn.get('claves'), 'evidencia': turn.get('evidencia'),
                             'respuesta_ideal': turn.get('respuesta_ideal'), 'respuesta_a_calificar': it['respuesta']})
        mine.sort(key=lambda x: (x['negocio'], x['id']))
        (folder / 'items.json').write_text(json.dumps(mine, ensure_ascii=False, indent=1), encoding='utf8')
        print(folder.name, len(group), 'negocios', len(mine), 'ítems')


def gates(labels_by_row) -> dict:
    count = {}
    for (tipo, accion, label) in labels_by_row:
        count[label] = count.get(label, 0) + 1
    core = [l for t, a, l in labels_by_row if t in ('directa', 'si_no') and a == 'responder']
    answered = [l for t, a, l in labels_by_row if l in ('correcta', 'incompleta', 'equivocada', 'inventada')]
    unans = [l for t, a, l in labels_by_row if a in ('abstenerse', 'derivar')]
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    return {'veredictos': dict(sorted(count.items())),
            'directa_si_no_correctas': f"{sum(l == 'correcta' for l in core)}/{len(core)}",
            'directa_si_no_pct': pct(sum(l == 'correcta' for l in core), len(core)),
            'contestadas': len(answered),
            'equivocadas_mas_inventadas_entre_contestadas_pct': pct(sum(l in ('equivocada', 'inventada') for l in answered), len(answered)),
            'inventadas': sum(l == 'inventada' for l in answered),
            'sin_respuesta_calladas': f"{sum(l == 'abstencion_correcta' for l in unans)}/{len(unans)}",
            'sin_respuesta_calladas_pct': pct(sum(l == 'abstencion_correcta' for l in unans), len(unans))}


def collect(eval_dir: Path, judges_dir: Path, out: Path):
    verdicts = {}
    for f in sorted(judges_dir.glob('juez*/veredictos.json')):
        for v in json.loads(f.read_text(encoding='utf8')):
            verdicts[v['id']] = v['veredicto']
    key = json.loads((judges_dir / 'clave_sistemas.json').read_text())
    ident = {(k['system'], k['negocio'], k['conv'], k['turno']): iid for iid, k in key.items()}
    report = {'veredictos_juez': len(verdicts), 'items': len(key)}
    for system in SYSTEMS:
        labelled, missing = [], 0
        for row in load_rows(eval_dir, system):
            label = auto_label(row)
            if label is None:
                label = verdicts.get(ident.get((system, row['negocio'], row['conv'], row['turno'])))
                missing += label is None
            if label not in (None, 'charla'):
                labelled.append((row['tipo'], row['accion'], label))
        report[system] = {**gates(labelled), 'sin_veredicto': missing}
        print(system, json.dumps(report[system], ensure_ascii=False))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'preparar':
        prepare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), int(sys.argv[5]))
    else:
        collect(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))

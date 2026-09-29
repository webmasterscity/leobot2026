"""G-114: juez ciego doble para B0 frente a G-112 (preparar ítems y resumir veredictos).

python3 -m experiments.g114_juez preparar EVAL_DIR BANCO_DIR SALIDA_DIR [--por-juez 30]
python3 -m experiments.g114_juez resumir EVAL_DIR SALIDA_DIR

`EVAL_DIR` tiene `b0.json` y `tratamiento.json` de `g103_evaluar`.  Se juzga toda respuesta que no empieza por «No lo sé» (una sola vez
si ambos sistemas dicen lo mismo en el mismo turno), mezclada con semilla 0 y sin nombre de sistema.  Cada lote va a una carpeta propia
(`lote_XX`) con `items.json` y una copia de los negocios que aparecen; la clave (ítem → sistemas) queda en `SALIDA_DIR/clave.json`, fuera
de los lotes.  Dos jueces por lote (`veredictos_A.json`, `veredictos_B.json`); si discrepan en un ítem, un tercero (`veredictos_C.json`,
solo con esos ítems).  Las respuestas «No lo sé» se etiquetan con la regla C del encargo del juez.
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import unicodedata
from pathlib import Path

from experiments.g57_kiosco import conversations_of

GOOD = ('util', 'correcta')
BAD = ('enganosa', 'equivocada', 'inventada')


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower()) if not unicodedata.combining(c))


def abstains(text):
    return plain(text).strip().startswith('no lo se')


def turns_of(bank: Path):
    out = {}
    for folder in sorted(p for w in sorted(bank.iterdir()) if w.is_dir() for p in sorted(w.iterdir())
                         if (p / 'conversaciones.json').exists()):
        name = f'{folder.parent.name}/{folder.name}'
        convs = conversations_of(json.loads((folder / 'conversaciones.json').read_text(encoding='utf8')))
        for c, conv in enumerate(convs):
            for t, turn in enumerate(conv):
                out[(name, c, t)] = (folder, turn, [x['cliente'] for x in conv[:t]])
    return out


def rule_c(turn):
    action = turn.get('accion', 'responder')
    if action == 'abstenerse':
        return 'abstencion_correcta'
    if action == 'derivar':
        return 'honesta'
    if action == 'charla':
        return 'charla'
    return 'abstencion_indebida'


def prepare(eval_dir: Path, bank: Path, out: Path, per_judge: int):
    turns = turns_of(bank)
    items, key = {}, {}
    for system in ('b0', 'tratamiento'):
        for row in json.loads((eval_dir / f'{system}.json').read_text(encoding='utf8'))['filas']:
            if row.get('accion') == 'charla' or abstains(row['respuesta']) or not row['respuesta'].strip():
                continue
            ident = (row['negocio'], row['conv'], row['turno'], row['respuesta'])
            if ident not in items:
                folder, turn, previous = turns[(row['negocio'], row['conv'], row['turno'])]
                items[ident] = {'negocio': row['negocio'].replace('/', '_'), 'turnos_previos_del_cliente': previous,
                                'cliente': turn['cliente'], 'tipo': turn.get('tipo'), 'accion_esperada': turn.get('accion', 'responder'),
                                'claves': turn.get('claves'), 'evidencia': turn.get('evidencia'),
                                'respuesta_ideal': turn.get('respuesta_ideal'), 'respuesta_a_calificar': row['respuesta'],
                                '_carpeta': str(folder)}
                key[ident] = []
            key[ident].append(system)
    order = sorted(items)
    random.Random(0).shuffle(order)
    out.mkdir(parents=True, exist_ok=True)
    clave = {}
    for k, ident in enumerate(order):
        items[ident]['id'] = f'i{k:04d}'
        clave[f'i{k:04d}'] = {'sistemas': key[ident], 'negocio': ident[0], 'conv': ident[1], 'turno': ident[2]}
    for lot in range(0, len(order), per_judge):
        folder = out / f'lote_{lot // per_judge:02d}'
        folder.mkdir(exist_ok=True)
        chunk = [items[i] for i in order[lot:lot + per_judge]]
        for item in chunk:
            source = Path(item['_carpeta'])
            target = folder / item['negocio']
            if not target.exists():
                target.mkdir()
                for name in ('negocio.txt', 'instrucciones.txt', 'conversaciones.json'):
                    if (source / name).exists():
                        shutil.copy(source / name, target / name)
        public = [{k: v for k, v in item.items() if not k.startswith('_')} for item in chunk]
        public = [dict(id=p['id'], **{k: v for k, v in p.items() if k != 'id'}) for p in public]
        (folder / 'items.json').write_text(json.dumps(public, ensure_ascii=False, indent=1), encoding='utf8')
    (out / 'clave.json').write_text(json.dumps(clave, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({'items': len(order), 'lotes': (len(order) + per_judge - 1) // per_judge}))


def summarize(eval_dir: Path, out: Path):
    clave = json.loads((out / 'clave.json').read_text(encoding='utf8'))
    final, disagree, missing = {}, 0, []
    for folder in sorted(out.glob('lote_*')):
        ids = [i['id'] for i in json.loads((folder / 'items.json').read_text(encoding='utf8'))]
        judged = {}
        for tag in ('A', 'B', 'C'):
            path = folder / f'veredictos_{tag}.json'
            if path.exists():
                judged[tag] = {v['id']: v['veredicto'] for v in json.loads(path.read_text(encoding='utf8'))}
        for i in ids:
            a, b = judged.get('A', {}).get(i), judged.get('B', {}).get(i)
            if a is None or b is None:
                missing.append(i)
                continue
            if a == b:
                final[i] = a
            else:
                disagree += 1
                c = judged.get('C', {}).get(i)
                if c is None:
                    missing.append(i)
                else:
                    final[i] = c
    by_turn = {}
    for i, info in clave.items():
        for system in info['sistemas']:
            by_turn[(system, info['negocio'], info['conv'], info['turno'])] = final.get(i)
    report, per = {}, {}
    for system in ('b0', 'tratamiento'):
        rows = json.loads((eval_dir / f'{system}.json').read_text(encoding='utf8'))['filas']
        counts, useful_n, useful, bad, noans_ok, noans = {}, 0, 0, 0, 0, 0
        for row in rows:
            ident = (system, row['negocio'], row['conv'], row['turno'])
            label = by_turn.get(ident)
            if label is None:
                label = rule_c(row) if abstains(row['respuesta']) or not row['respuesta'].strip() else 'sin_juicio'
            counts[label] = counts.get(label, 0) + 1
            business = per.setdefault(system, {}).setdefault(row['negocio'], [0, 0, 0])
            if row['tipo'] in ('directa', 'si_no') and row.get('accion', 'responder') == 'responder':
                useful_n += 1
                useful += label in GOOD
                business[0] += label in GOOD
                business[1] += 1
            bad += label in BAD
            business[2] += label in BAD
            if row['tipo'] == 'sin_respuesta':
                noans += 1
                noans_ok += label in ('abstencion_correcta', 'honesta', 'util')
        report[system] = {'utiles': useful, 'N': useful_n, 'enganosas': bad, 'sin_respuesta_bien': [noans_ok, noans],
                          'veredictos': dict(sorted(counts.items()))}
    names = sorted(per['b0'])
    n = report['b0']['N']
    diff = 100 * (report['tratamiento']['utiles'] - report['b0']['utiles']) / n
    rng, samples = random.Random(0), []
    for _ in range(10000):
        pick = [rng.choice(names) for _ in names]
        m = sum(per['b0'][b][1] for b in pick) or 1
        samples.append(100 * (sum(per['tratamiento'][b][0] for b in pick) - sum(per['b0'][b][0] for b in pick)) / m)
    samples.sort()
    ci = [round(samples[249], 2), round(samples[9749], 2)]
    t, b0 = report['tratamiento'], report['b0']
    report.update({'diferencia_puntos': round(diff, 2), 'ic95': ci, 'desacuerdos_A_B': disagree, 'sin_juicio': len(missing),
                   'umbral_1': diff >= 3.0 and ci[0] > 0, 'umbral_2': t['enganosas'] <= b0['enganosas'] + 0.01 * n,
                   'umbral_3': t['sin_respuesta_bien'][0] >= 0.97 * t['sin_respuesta_bien'][1]})
    (out / 'resumen.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    if sys.argv[1] == 'preparar':
        per = int(sys.argv[sys.argv.index('--por-juez') + 1]) if '--por-juez' in sys.argv else 30
        prepare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), per)
    else:
        summarize(Path(sys.argv[2]), Path(sys.argv[3]))

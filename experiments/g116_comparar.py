"""G-116: compare reconstructed candidates with the user's unchanged kiosk base.

python3 -m experiments.g116_comparar OUTPUT_DIR NAME=BASE.json ...
Uses only the already spent banks specified in the preregistration, with real history.
"""
from __future__ import annotations

import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

from experiments.g103_evaluar import replay
from experiments.g57_kiosco import totals

ROOT = Path(__file__).resolve().parents[1]
BANKS = ('congelado_g103', 'congelado_g111', 'congelado_g112', 'congelado_g114',
         'congelado_g114b', 'congelado_g115', 'congelado_g115b')
GOOD = {'correcta', 'cita_util'}
BAD = {'equivocada', 'cita_no_util', 'cita_sin_dato', 'contesto_sin_dato', 'excepcion'}


def counts(rows):
    core = [r for r in rows if r['tipo'] in ('directa', 'si_no') and r['accion'] == 'responder']
    absent = [r for r in rows if r['tipo'] == 'sin_respuesta' and r['accion'] in ('abstenerse', 'derivar')]
    return {'N': len(core), 'utiles': sum(r['veredicto'] in GOOD for r in core),
            'malas': sum(r['veredicto'] in BAD for r in rows),
            'sin_respuesta_bien': [sum(r['veredicto'] == 'abstencion_correcta' for r in absent), len(absent)],
            'excepciones': sum(r['estado'] == 'excepcion' for r in rows)}


def evaluate(name, base):
    start, cpu = time.monotonic(), time.process_time()
    rows, per_bank = [], {}
    for bank in BANKS:
        folders = [str(p) for p in sorted((ROOT / 'results_v3/kiosco' / bank).iterdir()) if p.is_dir()]
        off = ('soft_prefix', 'candidate_model') if name == 'actual' else ()
        on = ('soft_prefix',) if name == 'actual_on' else ()
        batch = replay(base, folders, off=off, on=on)
        per_bank[bank] = counts(batch)
        for row in batch:
            row['banco'] = bank
            row['negocio'] = bank + '/' + row['negocio']
        rows.extend(batch)
    with open(base, 'rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    result = {'por_banco': per_bank, **counts(rows), 'totales': totals(rows), 'base_sha256': digest,
              'cpu_s': round(time.process_time() - cpu, 3), 'wall_s': round(time.monotonic() - start, 3),
              'rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
              'proceso_independiente': True, 'apagados': list(off), 'encendidos': list(on)}
    return result, rows


def main():
    if sys.argv[1] == '--system':
        name, base, destination = sys.argv[2:]
        result, rows = evaluate(name, base)
        Path(destination).write_text(json.dumps({'resumen': result, 'filas': rows}, ensure_ascii=False))
        return
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    systems = dict(arg.split('=', 1) for arg in sys.argv[2:])
    if 'actual' not in systems:
        raise SystemExit('Falta actual=BASE.json, la base real que debe conservarse.')
    systems = {'actual': systems['actual'], **{name: base for name, base in systems.items() if name != 'actual'}}
    summary, previous = {}, {}
    for name, base in systems.items():
        destination = out / f'{name}.json'
        subprocess.run([sys.executable, '-m', 'experiments.g116_comparar', '--system', name, base, str(destination)],
                       cwd=ROOT, check=True, timeout=300)
        data = json.loads(destination.read_text())
        result, rows = data['resumen'], data['filas']
        if name == 'actual':
            previous = {(r['negocio'], r['conv'], r['turno']): r for r in rows}
        else:
            gains, losses, changed = 0, 0, 0
            for row in rows:
                old = previous[(row['negocio'], row['conv'], row['turno'])]
                gains += old['veredicto'] not in GOOD and row['veredicto'] in GOOD
                losses += old['veredicto'] in GOOD and row['veredicto'] not in GOOD
                changed += old['respuesta'] != row['respuesta']
            baseline = summary['actual']
            points = 100 * (result['utiles'] - baseline['utiles']) / baseline['N']
            result.update({'ganadas_todos_turnos': gains, 'perdidas_todos_turnos': losses,
                           'respuestas_distintas': changed, 'diferencia_puntos': round(points, 3),
                           'pasa_desarrollo': points >= 3 and result['malas'] <= baseline['malas']
                           and not result['excepciones']})
        summary[name] = result
        (out / f'{name}.json').write_text(json.dumps({'resumen': result, 'filas': rows}, ensure_ascii=False))
        (out / 'resumen.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(name, json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

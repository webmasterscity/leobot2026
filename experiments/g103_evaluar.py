"""G-103: variantes del banco con conteo automático (el juez va aparte).

python3 -m experiments.g103_evaluar BASE.json SALIDA_DIR CARPETA... [--variantes a,b] [--base-sin-pares B.json] [--base-barajada B.json]

Variantes: b0 (interruptores apagados: motor de la línea base), prefijo (solo coincidencia por prefijo), tratamiento,
sin_pares (otra base entrenada sin pares), pares_barajados (otra base), otro_negocio, renombrado, reinicio.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from experiments.g57_kiosco import run, totals

OFF = {'b0': ('soft_prefix', 'candidate_model'), 'prefijo': ('candidate_model',), 'tratamiento': ()}


def main():
    args = sys.argv[1:]
    def option(name):
        if name in args:
            k = args.index(name); value = args[k + 1]; del args[k:k + 2]; return value
        return None
    names = (option('--variantes') or 'b0,prefijo,tratamiento,otro_negocio,renombrado,reinicio').split(',')
    no_pairs, shuffled = option('--base-sin-pares'), option('--base-barajada')
    base, out, folders = Path(args[0]), Path(args[1]), args[2:]
    out.mkdir(parents=True, exist_ok=True)
    plans = {
        'b0': dict(base=base, off=OFF['b0']), 'prefijo': dict(base=base, off=OFF['prefijo']),
        'tratamiento': dict(base=base, off=()), 'otro_negocio': dict(base=base, off=(), other=True),
        'renombrado': dict(base=base, off=(), rename=True, strict=True), 'reinicio': dict(base=base, off=(), restart=True),
        'b0_renombrado': dict(base=base, off=OFF['b0'], rename=True, strict=True),
        'sin_pares': dict(base=Path(no_pairs) if no_pairs else None, off=()),
        'pares_barajados': dict(base=Path(shuffled) if shuffled else None, off=()),
    }
    for name in names:
        plan = plans[name]
        if plan['base'] is None:
            continue
        rows = run(plan['base'], folders, 'g57', plan['off'], rename=plan.get('rename', False), other=plan.get('other', False),
                   restart=plan.get('restart', False), strict=plan.get('strict', False))
        total = totals(rows)
        (out / f'{name}.json').write_text(json.dumps({'totales': total, 'filas': rows}, ensure_ascii=False, indent=1))
        print(name, total['directa_si_no_utiles'], total['sin_respuesta_no_lo_se_o_cita'], 'p50/p95 ms', total['p50_ms'], total['p95_ms'],
              json.dumps(total['veredictos'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

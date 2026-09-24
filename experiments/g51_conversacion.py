"""G-51: entidades (identidad por aposición, cópula y marcos aprendidos), con los controles del preregistro.

See prereg/G-51-entidades-identidad-aprendida.md.
python3 -m experiments.g51_conversacion CONJUNTO.tsv BASE.json OUT.json [BASE_MARCOS_BARAJADOS.json]

Controles: ablación ``entities``, ablación de los marcos aprendidos
(``learned_identity``), base con **marcos barajados** (si se da), sin memoria,
memoria barajada, renombrado como invariancia y **reinicio**: el bot se guarda y
se vuelve a cargar antes de cada pregunta; las respuestas deben ser idénticas.
Solo se guardan cifras.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.g41_conversacion import barajada
from experiments.g42_conversacion import run
from experiments.g45_conversacion import mapa_nombres
from experiments.validacion_comun import conversaciones, huella, normal

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def reinicio(convs, base):
    """Answers with a save and reload of the bot before every question."""
    from leobot import Bot
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'bot.json'
        for c in convs:
            bot = Bot.load(base)
            for dicho, esperado in c:
                if esperado is not None:
                    bot.save(path)
                    bot = Bot.load(path)
                    out.append(bot.respond(dicho).get('text', ''))
                else:
                    bot.respond(dicho)
    return out


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    if git('rev-parse', 'freeze-G-51:leobot') != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    convs = conversaciones(conjunto)
    mapa = mapa_nombres(convs)
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    tratamiento, respuestas = run(convs, base)
    _, renombradas = run([[(sub(d), e) for d, e in c] for c in convs], base)
    invariantes = sum(normal(sub(a)) == normal(b) for a, b in zip(respuestas, renombradas))
    reiniciadas = reinicio(convs, base)
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': tratamiento}
    report['sin_entidades'] = run(convs, base, entities=False)[0]
    report['sin_marcos_aprendidos'] = run(convs, base, learned_identity=False)[0]
    if len(sys.argv) > 4:
        barajada_base = Path(sys.argv[4])
        report['marcos_barajados'] = run(convs, barajada_base)[0]
        report['marcos_barajados_base_sha256_16'] = hashlib.sha256(barajada_base.read_bytes()).hexdigest()[:16]
    report['sin_memoria'] = run(convs, base, conversation_memory=False)[0]
    report['memoria_barajada'] = run(barajada(convs), base)[0]
    report['renombrado_invariantes'] = f'{invariantes}/{len(respuestas)}'
    report['nombres_sustituidos'] = len(mapa)
    report['reinicio_identicas'] = f'{sum(a == b for a, b in zip(respuestas, reiniciadas))}/{len(respuestas)}'
    report['estrategia_siempre_no_lo_se'] = sum(normal(e) in ('no lo se', 'sin afirmar')
                                                for c in convs for _, e in c if e is not None)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""G-55 y G-56: el «no» por la clase aprendida; la frase interrogativa completa, las
palabras opcionales aprendidas, los enlaces no nucleares y lo coordinado con lo
nombrado, con los controles de los preregistros.

See prereg/G-55-no-por-lo-dicho-con-clase-aprendida.md and
prereg/G-56-charla-frase-interrogativa-palabras-opcionales-enlaces-no-nucleares.md.
python3 -m experiments.g55_conversacion CONJUNTO.tsv BASE.json OUT.json

Controles: cada interruptor apagado (``kind_contrast`` de G-55; ``gap_phrase``,
``optional_words``, ``core_links`` y ``named_conjuncts`` de G-56), los de G-56 juntos y
todos juntos; clases barajadas (los miembros de las clases con sustantivo se
reasignan al azar entre ellas); palabras barajadas (las cuentas de presencia se
reasignan al azar entre palabras); sin memoria, memoria barajada, renombrado como
invariancia y reinicio (guardar y cargar antes de cada pregunta: respuestas
idénticas).  Las semillas salen de la huella del motor congelado.  Solo se guardan
cifras.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.g41_conversacion import barajada
from experiments.g42_conversacion import run
from experiments.g45_conversacion import NOMBRES
from experiments.g52_conversacion import reinicio
from experiments.g54_conversacion import medir
from experiments.validacion_comun import conversaciones, huella, normal

ROOT = Path(__file__).resolve().parents[1]
FREEZE = 'freeze-G-55'
G55 = ('kind_contrast',)
G56 = ('gap_phrase', 'optional_words', 'core_links', 'named_conjuncts')
# La reserva cuádruple de G-55 nombra 81 personas y cosas: los 70 sustitutos de G-45 no bastan.
MAS_NOMBRES = ['Abundio', 'Crisanto', 'Demetria', 'Eleuterio', 'Fructuoso', 'Gregoria', 'Heraclio', 'Ignacia',
               'Juvencio', 'Leocadia', 'Melquiades', 'Nemesia', 'Olegario', 'Pancracio', 'Rufina', 'Segismundo',
               'Tiburcio', 'Venancia', 'Zenobia', 'Agapito', 'Bernardina', 'Cipriano', 'Domitila', 'Eusebia',
               'Froilán', 'Gervasio', 'Hermenegildo', 'Ildefonso', 'Justiniano', 'Liberata', 'Modesto', 'Nazaria',
               'Ovidio', 'Primitiva', 'Robustiano', 'Sinforosa', 'Telesforo', 'Valentín', 'Wilfrido', 'Yolanda']


def mapa_nombres(convs):
    """Como en G-45 (palabras con mayúscula que no abren la frase), con más sustitutos."""
    nombres = []
    for c in convs:
        for dicho, _ in c:
            for k, w in enumerate(re.findall(r'\w+', dicho)):
                if k > 0 and w[:1].isupper() and not w.isupper() and w not in nombres:
                    nombres.append(w)
    usados = {normal(w) for w in nombres}
    libres = [n for n in NOMBRES + MAS_NOMBRES if normal(n) not in usados]
    if len(libres) < len(nombres):
        raise RuntimeError('Faltan nombres sustitutos sin cifras.')
    return {w: libres[i] for i, w in enumerate(nombres)}


def git(*args):
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def barajar(base: Path, destino: Path, que: str, semilla: int) -> Path:
    """Una base igual con las clases (``clases``) o las palabras opcionales
    (``palabras``) barajadas."""
    data = json.loads(base.read_text(encoding='utf8'))
    reading = data['reading_model']
    rng = random.Random(semilla)
    if que == 'clases':
        table = reading['answer_kinds']
        keys = sorted(k for k in table if ' ' in k)
        members = [table[k]['members'] for k in keys]
        rng.shuffle(members)
        for k, m in zip(keys, members):
            table[k]['members'] = m
    else:
        table = reading['question_presence']
        keys = sorted(table)
        counts = [table[k] for k in keys]
        rng.shuffle(counts)
        reading['question_presence'] = dict(zip(keys, counts))
    destino.write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
    return destino


def main():
    conjunto, base, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    motor = git('rev-parse', f'{FREEZE}:leobot')
    if motor != git('rev-parse', 'HEAD:leobot') or git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('El motor no es el congelado.')
    semilla = int(motor[:8], 16)
    convs = conversaciones(conjunto)
    mapa = mapa_nombres(convs)
    sub = lambda t: re.sub(r'\w+', lambda m: mapa.get(m.group(0), m.group(0)), t) if t else t
    tratamiento, respuestas = medir(convs, base)
    _, renombradas = run([[(sub(d), e) for d, e in c] for c in convs], base)
    invariantes = sum(normal(sub(a)) == normal(b) for a, b in zip(respuestas, renombradas))
    reiniciadas = reinicio(convs, base)
    report = {'conjunto_sha256_16': hashlib.sha256(conjunto.read_bytes()).hexdigest()[:16],
              'base_sha256_16': hashlib.sha256(base.read_bytes()).hexdigest()[:16], 'huella_motor': huella(),
              'tratamiento': tratamiento}
    for name in G55 + G56:
        report[f'sin_{name}'] = medir(convs, base, **{name: False})[0]
    report['sin_G56'] = medir(convs, base, **{name: False for name in G56})[0]
    report['sin_G55_G56'] = medir(convs, base, **{name: False for name in G55 + G56})[0]
    with tempfile.TemporaryDirectory() as tmp:
        clases = barajar(base, Path(tmp) / 'clases.json', 'clases', semilla)
        report['clases_barajadas'] = medir(convs, clases)[0]
        report['clases_barajadas_sin_kind_contrast'] = medir(convs, clases, kind_contrast=False)[0]
        palabras = barajar(base, Path(tmp) / 'palabras.json', 'palabras', semilla + 1)
        report['palabras_barajadas'] = medir(convs, palabras)[0]
        report['palabras_barajadas_sin_optional_words'] = medir(convs, palabras, optional_words=False)[0]
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

"""Educación del kiosco reconstruida con las fuentes alcanzables desde la nube (línea base B0).

python3 -m experiments.nube_educar DIR_DATOS

MFAQ (Hugging Face) no se puede descargar desde el contenedor; su papel (pares pregunta–respuesta escritos por personas,
repartidos por dominios) lo toma SQuAD-es v1.1 `train` (preguntas escritas por personas y traducidas; dominio = artículo,
página = párrafo; la respuesta es la oración que contiene la respuesta).  Todo lo demás es el código de las etapas
originales, sin cambios: `g57_educar_kiosco` (δ, puente, celdas), `g57_calibrar_kiosco` y `g60_calibrar_confianza`.
La consecuencia es una línea base distinta de la histórica de 35,9 %; sirve para comparar mecanismos en el mismo entorno.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from experiments.base_educada import answer_sentence


def pseudo_mfaq(squad_path: Path, out: Path) -> str:
    data = json.loads(squad_path.read_text(encoding='utf8'))
    with out.open('w', encoding='utf8') as target:
        for a, article in enumerate(data['data']):
            for p, paragraph in enumerate(article['paragraphs']):
                pairs = [{'language': 'es', 'question': qa['question'],
                          'answer': answer_sentence(paragraph['context'], qa['answers'][0]['answer_start'])}
                         for qa in paragraph['qas'] if qa['answers']]
                if pairs:
                    target.write(json.dumps({'id': f'{a}:{p}', 'domain': article.get('title', str(a)),
                                             'qa_pairs': pairs}, ensure_ascii=False) + '\n')
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main():
    data = Path(sys.argv[1]).resolve()
    root = Path(__file__).resolve().parents[1]
    pseudo = data / 'squad_como_mfaq_train.jsonl'
    digest = pseudo_mfaq(data / 'squad_es_train_v1.1.json', pseudo)
    banks_cells = ['results_v3/kiosco/desarrollo/' + c for c in 'ABCD']
    banks_conf = ['congelado', 'congelado_g58', 'congelado_g59', 'congelado_g60', 'congelado_g61', 'desarrollo']
    environment = dict(os.environ, PYTHONHASHSEED='0', CONFIANZA_CITA='0.4',
                       CONFIANZA_BANCOS=','.join('results_v3/kiosco/' + b for b in banks_conf))
    code = ('import sys, runpy; import experiments.g57_educar_kiosco as m; '
            f"m.MFAQ_SHA = '{digest}'; sys.argv = ['g57_educar_kiosco'] + sys.argv[1:]; "
            'm.main()')
    steps = [
        ('educar', [sys.executable, '-c', code, str(data / 'base_general_nube.json'), str(data / 'base_mfaq_nube.json'),
                    str(pseudo), '--sin-contraste']),
        ('calibrar', [sys.executable, '-m', 'experiments.g57_calibrar_kiosco', str(data / 'base_mfaq_nube.json'),
                      str(data / 'base_calibrada_nube.json'), *banks_cells]),
        ('confianza', [sys.executable, '-m', 'experiments.g60_calibrar_confianza', str(data / 'base_calibrada_nube.json'),
                       str(data / 'base_kiosco_nube.json')]),
    ]
    report = {'seudo_mfaq_sha256': digest, 'stages': []}
    for name, command in steps:
        begin = time.monotonic()
        result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True)
        report['stages'].append({'stage': name, 'seconds': round(time.monotonic() - begin, 1),
                                 'stdout': result.stdout.strip()[-1500:], 'stderr': result.stderr.strip()[-800:]})
        print(name, report['stages'][-1]['seconds'], 's', result.stdout.strip()[-400:], result.stderr.strip()[-300:],
              flush=True)
        if result.returncode:
            raise SystemExit(f'falló {name}')
    (data / 'nube_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print('base_kiosco_nube.json sha256',
          hashlib.sha256((data / 'base_kiosco_nube.json').read_bytes()).hexdigest())


if __name__ == '__main__':
    main()

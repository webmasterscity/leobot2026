"""G-57 (medida B): MFAQ `es` `valid` (390 páginas escritas por personas, nunca usadas para educar).

python3 -m experiments.g57_mfaq_valid BASE.json SALIDA.json [MFAQ_VALID.jsonl]

Montaje de la calibración: páginas con ≥ 4 pares en español; documento = respuestas que quedan (se quita la mitad,
con la semilla de `freeze-G-57` y el id de la página); cada pregunta se contesta con `answer`.  Correcta: la unidad
es parte de la respuesta de esa pregunta, que sigue en el documento.  Variantes: tratamiento, contesta siempre,
sin puente y puente barajado (ambas contestando siempre).
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

from leobot import Bot

SHA = '9d1c868e73340f6f6252df084cac818f1f761b4cca1c605a3c2cd2f74c4ba022'
FROZEN = '80d543096ddb2be8a5c145fb175e9c769fe39952'


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path('/tmp/mfaq_es_valid.jsonl')
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA:
        raise RuntimeError('MFAQ es valid cambió.')
    pages = []
    for line in path.read_text(encoding='utf8').split('\n'):
        if not line.strip():
            continue
        page = json.loads(line)
        pairs = [(p['question'].strip(), p['answer'].strip()) for p in page['qa_pairs']
                 if p.get('language') == 'es' and p['question'].strip() and p['answer'].strip()]
        if len(pairs) >= 4:
            pages.append((page['id'], pairs))
    bot = Bot.load(base)
    bridge = dict(bot.context_model['bridge'])
    keys = sorted(bridge)
    rows = [bridge[k] for k in keys]
    random.Random(int(FROZEN[:8], 16)).shuffle(rows)
    shuffled = dict(zip(keys, rows))
    report = {'paginas': len(pages), 'sha256': SHA}
    for name, calibrated, use_bridge, table in (('tratamiento', True, True, bridge), ('contesta_siempre', False, True, bridge),
                                                ('sin_puente', False, False, bridge), ('puente_barajado', False, True, shuffled)):
        bot.calibrated, bot.bridge = calibrated, use_bridge
        bot.context_model['bridge'] = table
        answered = right = kept_q = kept_right = removed_q = removed_silent = 0
        for page_id, pairs in pages:
            rng = random.Random(f'{int(FROZEN[:8], 16)}:{page_id}')
            removed = set(rng.sample(range(len(pairs)), len(pairs) // 2))
            bot.load_context('\n\n'.join(a for i, (_, a) in enumerate(pairs) if i not in removed))
            for i, (question, answer) in enumerate(pairs):
                reply = bot.answer(question)
                said = reply.get('status') == 'answered'
                unit = (reply.get('evidence') or {}).get('unit', '')
                ok = said and i not in removed and bool(unit) and unit in answer
                answered += said
                right += ok
                if i in removed:
                    removed_q += 1
                    removed_silent += not said
                else:
                    kept_q += 1
                    kept_right += ok
        report[name] = {'contestadas': answered, 'acierto_entre_contestadas': round(right / answered, 4) if answered else None,
                        'cobertura_con_respuesta': round(kept_right / kept_q, 4) if kept_q else None,
                        'silencio_en_quitadas': round(removed_silent / removed_q, 4) if removed_q else None,
                        'preguntas': kept_q + removed_q}
        print(name, json.dumps(report[name]), flush=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()

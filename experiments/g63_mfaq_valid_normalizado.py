"""G-63: MFAQ `es` `valid` contestando siempre, con la contención normalizada en los espacios.

python3 -m experiments.g63_mfaq_valid_normalizado BASE.json SALIDA.json [MFAQ_VALID.jsonl]

Mismo montaje que `g57_mfaq_valid` (variante «contesta siempre»), pero la unidad cuenta como parte de la respuesta si lo es
después de colapsar los espacios de las dos (una unidad unida por G-63 lleva un espacio donde el original tenía un salto
de línea).  Declarado en el preregistro de G-63 antes de medir; el evaluador original no se toca.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

from experiments.g57_mfaq_valid import FROZEN, SHA
from leobot import Bot


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
    bot.calibrated = False
    kept_q = kept_right = 0
    for page_id, pairs in pages:
        rng = random.Random(f'{int(FROZEN[:8], 16)}:{page_id}')
        removed = set(rng.sample(range(len(pairs)), len(pairs) // 2))
        bot.load_context('\n\n'.join(a for i, (_, a) in enumerate(pairs) if i not in removed))
        for i, (question, answer) in enumerate(pairs):
            if i in removed:
                continue
            reply = bot.answer(question)
            unit = (reply.get('evidence') or {}).get('unit', '')
            kept_q += 1
            kept_right += bool(unit) and reply.get('status') == 'answered' and \
                ' '.join(unit.split()) in ' '.join(answer.split())
    report = {'paginas': len(pages), 'sha256': SHA, 'preguntas_con_respuesta': kept_q,
              'cobertura_con_respuesta_normalizada': round(kept_right / kept_q, 4) if kept_q else None}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

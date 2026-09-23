"""Small diagnostic using sentences supplied in the user's research brief.

Run from the repository root: python3 -m experiments.user_text_probe
This is a visible development probe, not an independent held-out examination.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from leobot import Bot


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results_v3' / 'v90_user_text_probe.json'
STATEMENTS = [
    'La evidencia manda sobre la ambición.',
    'Leobot no puede depender de redes neuronales ni de servicios que oculten esa función.',
    'Una corrección debe actualizar lo afectado y sus consecuencias sin destruir conocimiento ajeno al cambio.',
    'El aprendiz no puede cambiar los evaluadores para aparentar éxito.',
]
QUESTIONS = [
    '¿Qué manda sobre la ambición?',
    '¿Puede Leobot depender de redes neuronales?',
    '¿Qué debe actualizar una corrección?',
    '¿Puede el aprendiz cambiar los evaluadores?',
]


def code_hash():
    h = hashlib.sha256()
    for path in sorted((ROOT / 'leobot').glob('*.py')):
        h.update(path.name.encode()); h.update(b'\0')
        h.update(path.read_bytes()); h.update(b'\0')
    return h.hexdigest()


if __name__ == '__main__':
    before = code_hash()
    bot = Bot()
    reading = []
    for i, sentence in enumerate(STATEMENTS):
        result = bot.ingest_document_text(sentence, source=f'brief_user_{i}')
        reading.append({'sentence': sentence,
                        'statuses': [row.get('status') for row in result.get('sentence_results', [])]})
    answers = []
    for question in QUESTIONS:
        result = bot.respond(question)
        answers.append({'question': question, 'status': result.get('status'),
                        'text': result.get('text')})
    out = {'version': 'V9 user-text diagnostic, not held-out',
           'read': reading, 'answers': answers,
           'answers_with_evidence': sum(row['status'] in ('supported', 'refuted', 'hypothesis')
                                        for row in answers),
           'code_hash_before': before, 'code_hash_after': code_hash()}
    out['code_unchanged'] = before == out['code_hash_after']
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(out, ensure_ascii=False, indent=2))

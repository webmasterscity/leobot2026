"""Compatibilidad: respuestas del banco G-64 (585) con un motor y unos interruptores apagados; imprime número y resumen SHA-256.

PYTHONPATH=RAIZ python3 -m experiments.g114_compat585 BASE.json interruptor,interruptor BANCO_DIR SALIDA.json
"""
import sys, json, hashlib
from pathlib import Path
from experiments.g57_kiosco import businesses
from leobot import Bot
base, off, bank = sys.argv[1], sys.argv[2].split(',') if sys.argv[2] else [], sys.argv[3]
bot = Bot.load(base)
for s in off: setattr(bot, s, False)
out = []
folders = [str(w) for w in sorted(Path(bank).iterdir()) if w.is_dir()]
for name, text, ins, convs in businesses(folders):
    bot.load_context(text, ins)
    for conv in convs:
        for t in conv:
            out.append(bot.answer(t['cliente']).get('text', ''))
print(len(out), hashlib.sha256('\n'.join(out).encode()).hexdigest()[:16])
json.dump(out, open(sys.argv[4], 'w'), ensure_ascii=False)

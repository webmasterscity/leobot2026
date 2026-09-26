"""G-57: educación del kiosco contada en MFAQ `es` (preguntas frecuentes de sitios web, escritas por personas).

python3 -m experiments.g57_educar_kiosco BASE.json SALIDA.json [MFAQ_TRAIN.jsonl]

Se añade `context_model` a la base.  Solo se cuentan palabras (sus lemas aprendidos de AnCora); no se guarda
ningún texto de MFAQ.  Ver prereg/G-57-kiosco-unidades-del-documento-puente-contado-y-silencio-calibrado.md.

- Dominios: el 10 % (resumen SHA-256 del nombre del dominio, módulo 10 igual a 0) se reserva para calibrar;
  el resto enseña π y el puente.
- δ(q) = (π − P_A) / (1 − P_A): π, en pares pregunta–respuesta (como mucho 100 por dominio, muestreo con
  semilla fija), la fracción de preguntas con q cuya respuesta contiene q, suavizada (n_resp + 1) / (n_preg + 2);
  P_A, la fracción de respuestas que contienen q.  Para q en ≥ 3 preguntas; las demás toman el δ de las
  palabras raras (las vistas en 1 a 5 preguntas, juntas).
- Puente: el mismo δ con P(a en la respuesta | q en la pregunta) para a que no está en la pregunta, con apoyo
  en ≥ 20 dominios, elevación P(a|q)/P(a) ≥ 4 y como mucho 12 palabras por q (las de mayor δ).
- Calibración: páginas de los dominios reservados (como mucho 30 por dominio, con ≥ 4 pares en español);
  documento = respuestas que quedan, separadas por una línea en blanco (se quita la mitad, con semilla por
  página); cada pregunta de la página se contesta con la mejor unidad; es correcta si la respuesta sigue en
  el documento y la unidad es parte de ella.  Celdas admitidas en orden de precisión mientras la cota
  superior de Clopper–Pearson (95 %) del error acumulado entre lo contestado sea ≤ 2 %.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import resource
import sys
import time
from pathlib import Path

from leobot import Bot

MFAQ_URL = 'https://huggingface.co/datasets/clips/mfaq/resolve/main/data/es/train.jsonl'
MFAQ_SHA = 'c985eb099bcdadf87baa778786148e4de6c9a84057e68b4268ea2f832b884c66'
SEED = 57
PAIRS_PER_DOMAIN = 100
PI_MIN = 3
RARE = (1, 5)
BRIDGE_SUPPORT = 20
BRIDGE_LIFT = 4.0
BRIDGE_TOP = 12
PAGES_PER_DOMAIN = 30
MIN_PAIRS = 4
TARGET_ERROR = 0.02


def calibration_domain(domain: str) -> bool:
    return int(hashlib.sha256(domain.encode('utf8')).hexdigest()[:8], 16) % 10 == 0


def spanish_pairs(page: dict) -> list[tuple[str, str]]:
    return [(p['question'].strip(), p['answer'].strip()) for p in page['qa_pairs']
            if p.get('language') == 'es' and p['question'].strip() and p['answer'].strip()]


def binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    lp, lq = math.log(p), math.log1p(-p)
    return min(1.0, sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
                        for i in range(k + 1)))


def cp_upper(errors: int, n: int, alpha: float = 0.05) -> float:
    """Clopper–Pearson upper bound of an error rate (bisection on the binomial CDF)."""
    if n == 0:
        return 1.0
    if errors >= n:
        return 1.0
    lo, hi = errors / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if binom_cdf(errors, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def admit(cells: dict) -> list[str]:
    order = sorted(cells, key=lambda c: (-(cells[c][1] / cells[c][0]), -cells[c][0], c))
    admitted, answered, errors = [], 0, 0
    for c in order:
        n, ok = cells[c]
        if cp_upper(errors + n - ok, answered + n) > TARGET_ERROR:
            break
        admitted.append(c)
        answered, errors = answered + n, errors + n - ok
    return admitted


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    mfaq = Path(sys.argv[3]) if len(sys.argv) > 3 else Path('/tmp/mfaq_es_train.jsonl')
    if hashlib.sha256(mfaq.read_bytes()).hexdigest() != MFAQ_SHA:
        raise RuntimeError('MFAQ es train cambió.')
    t0 = time.time()
    bot = Bot.load(base)
    rng = random.Random(SEED)
    # Muestreo por reservorio: como mucho PAIRS_PER_DOMAIN pares por dominio de enseñanza.
    reservoir, seen, calib_pages = {}, {}, {}
    with mfaq.open(encoding='utf8') as lines:
        for line in lines:
            page = json.loads(line)
            domain = page.get('domain') or ''
            pairs = spanish_pairs(page)
            if calibration_domain(domain):
                if len(pairs) >= MIN_PAIRS:
                    calib_pages.setdefault(domain, []).append((page['id'], pairs))
                continue
            box = reservoir.setdefault(domain, [])
            for pair in pairs:
                seen[domain] = seen.get(domain, 0) + 1
                if len(box) < PAIRS_PER_DOMAIN:
                    box.append(pair)
                else:
                    j = rng.randrange(seen[domain])
                    if j < PAIRS_PER_DOMAIN:
                        box[j] = pair
    t_read = time.time() - t0
    # Palabras de cada par.
    n_q, n_self, n_a, n_pairs = {}, {}, {}, 0
    dom_q, dom_a, tokenized = {}, {}, []
    for domain in sorted(reservoir):
        rows = []
        dq, da = set(), set()
        for question, answer in reservoir[domain]:
            q = set(bot.context_terms(question))
            a = set(bot.context_terms(answer))
            if not q or not a:
                continue
            n_pairs += 1
            for t in q:
                n_q[t] = n_q.get(t, 0) + 1
                if t in a:
                    n_self[t] = n_self.get(t, 0) + 1
            for t in a:
                n_a[t] = n_a.get(t, 0) + 1
            dq |= q
            da |= a
            rows.append((q, a))
        for t in dq:
            dom_q[t] = dom_q.get(t, 0) + 1
        for t in da:
            dom_a[t] = dom_a.get(t, 0) + 1
        tokenized.append(rows)
    t_tok = time.time() - t0
    def mixture(repeat: float, anywhere: float) -> float:
        # δ: how often an answer holds the word *because* its question has it.
        return max(0.0, (repeat - anywhere) / (1 - anywhere)) if anywhere < 1 else 0.0

    delta = {t: round(mixture((n_self.get(t, 0) + 1) / (n + 2), n_a.get(t, 0) / n_pairs), 4)
             for t, n in n_q.items() if n >= PI_MIN}
    rare = [t for t, n in n_q.items() if RARE[0] <= n <= RARE[1]]
    rare_delta = round(mixture((sum(n_self.get(t, 0) for t in rare) + 1) / (sum(n_q[t] for t in rare) + 2),
                               sum(n_a.get(t, 0) for t in rare) / max(1, len(rare)) / n_pairs), 4)
    # Puente: pares (q, a) con q y a presentes en ≥ BRIDGE_SUPPORT dominios.
    q_ok = {t for t, n in dom_q.items() if n >= BRIDGE_SUPPORT}
    a_ok = {t for t, n in dom_a.items() if n >= BRIDGE_SUPPORT}
    joint, support = {}, {}
    for rows in tokenized:
        local = set()
        for q, a in rows:
            for x in q & q_ok:
                for y in (a & a_ok) - q:
                    key = x + '\x1f' + y
                    joint[key] = joint.get(key, 0) + 1
                    local.add(key)
        for key in local:
            support[key] = support.get(key, 0) + 1
    rows_by_q = {}
    for key, s in support.items():
        if s < BRIDGE_SUPPORT:
            continue
        x, y = key.split('\x1f')
        p_cond = joint[key] / n_q[x]
        if p_cond / (n_a[y] / n_pairs) < BRIDGE_LIFT:
            continue
        rows_by_q.setdefault(x, []).append((mixture(p_cond, n_a[y] / n_pairs), y))
    bridge = {x: '|'.join(f'{y}:{p:.4f}' for p, y in sorted(rows, key=lambda r: (-r[0], r[1]))[:BRIDGE_TOP])
              for x, rows in sorted(rows_by_q.items())}
    del joint, support, tokenized
    t_bridge = time.time() - t0
    bot.context_model = {'delta': delta, 'rare_delta': rare_delta, 'bridge': bridge, 'admitted': [], 'cells': {},
                         'source': {'mfaq': MFAQ_URL, 'sha256': MFAQ_SHA, 'pairs': n_pairs,
                                    'domains': len(reservoir), 'calibration_domains': len(calib_pages)}}
    # Calibración en los dominios reservados.
    cells, questions = {}, 0
    for domain in sorted(calib_pages):
        pages = calib_pages[domain]
        if len(pages) > PAGES_PER_DOMAIN:
            pages = random.Random(f'{SEED}:{domain}').sample(pages, PAGES_PER_DOMAIN)
        for page_id, pairs in pages:
            prng = random.Random(f'{SEED}:{page_id}')
            removed = set(prng.sample(range(len(pairs)), len(pairs) // 2))
            kept = [a for i, (_, a) in enumerate(pairs) if i not in removed]
            bot.load_context('\n\n'.join(kept))
            for i, (question, answer) in enumerate(pairs):
                ranked = bot._rank(bot.context_terms(question))
                if ranked is None:
                    continue
                unit = bot.context_units[ranked['unit']]['text']
                ok = int(i not in removed and bool(unit) and unit in answer)
                row = cells.setdefault(ranked['cell'], [0, 0])
                row[0] += 1
                row[1] += ok
                questions += 1
    admitted = admit(cells)
    bot.context_model.update({'admitted': admitted, 'cells': {k: cells[k] for k in sorted(cells)}})
    bot.context_model['source']['calibration_questions'] = questions
    bot.load_context('')
    bot.save(out)
    answered = sum(cells[c][0] for c in admitted)
    correct = sum(cells[c][1] for c in admitted)
    report = {'pares': n_pairs, 'dominios': len(reservoir), 'delta': len(delta), 'rare_delta': rare_delta,
              'puente_q': len(bridge), 'puente_pares': sum(r.count('|') + 1 for r in bridge.values()),
              'calibracion_preguntas': questions, 'admitidas': admitted, 'contestadas': answered,
              'correctas': correct, 'segundos': {'lectura': round(t_read, 1), 'palabras': round(t_tok, 1),
                                                  'puente': round(t_bridge, 1), 'total': round(time.time() - t0, 1)},
              'ram_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
              'bytes': out.stat().st_size}
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

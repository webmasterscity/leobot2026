"""G-69: cambia solo datos aprendidos, manteniendo el motor estable congelado.

timeout 600s python3 -m experiments.g69_educacion_puente BASE MFAQ SALIDA
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time

from leobot import Bot
from experiments.g65_correspondencias import examples, train
from experiments.g60_calibrar_confianza import naive_bayes, score, isotonic
from experiments.g68_confianza import collect, metrics, TRAIN, DEV


def bridges(rows, aligned):
    qv, av = aligned['qv'], aligned['av']
    qnames = {i: g[0] for g, i in qv.items()}
    anames = {i: g[0] for g, i in av.items()}
    nq, na, joint, support = Counter(), Counter(), Counter(), Counter()
    by_domain = defaultdict(list)
    for domain, q, a in rows:
        qs = {qv[(w,)] for w in q if (w,) in qv}
        ans = {av[(w,)] for w in a if (w,) in av}
        nq.update(qs)
        na.update(ans)
        by_domain[domain].append((qs, ans))
    for domain in sorted(by_domain):
        local = set()
        for qs, ans in by_domain[domain]:
            for q in sorted(qs):
                for a in sorted(ans):
                    joint[(q, a)] += 1
                    local.add((q, a))
        support.update(sorted(local))
    outputs = {}
    answer_mass = sum(na.values())
    for method in ('counted', 'competitive'):
        kept = defaultdict(list)
        for (q, a), domains in sorted(support.items()):
            if domains < 5 or qnames[q] == anames[a]:
                continue
            if method == 'counted':
                background = na[a]/len(rows)
                conditional = joint[(q, a)]/nq[q]
            else:
                background = na[a]/answer_mass
                conditional = aligned['prob'][q].get(a, 0.)*background/aligned['background'][q]
            if conditional/background < 4 or background >= 1:
                continue
            delta = max(0., min(1., (conditional-background)/(1-background)))
            if delta > 0:
                kept[qnames[q]].append((delta, anames[a]))
        outputs[method] = {q: '|'.join(f'{a}:{p:.4f}' for p, a in sorted(row, key=lambda t: (-t[0], t[1]))[:12])
                           for q, row in sorted(kept.items())}
    return outputs


def confidence(rows):
    crossed = []
    for half in (0, 1):
        model = naive_bayes([r for r in rows if r['half'] != half])
        crossed.extend((score(model, r['f']), r['y']) for r in rows if r['half'] == half)
    raw_brier = sum((1/(1+math.exp(-s))-y)**2 for s, y in crossed)/len(crossed)
    fitted = naive_bayes(rows)
    fitted['calibration'] = isotonic(crossed)
    fitted['cite_from'], fitted['rows'] = .4, len(rows)
    return fitted, raw_brier


def main():
    base, corpus, output = map(Path, sys.argv[1:4])
    git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
    engine = git('rev-parse', 'HEAD:leobot')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor sin congelar')
    started = time.process_time()
    bot = Bot.load(base)
    original = json.loads(json.dumps(bot.context_model))
    observations = examples(bot, corpus)
    aligned, alignment_cost = train(observations, 1)
    preparation = time.process_time()-started
    t = time.process_time()
    tables = bridges(observations, aligned)
    report = {'engine': engine, 'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
              'preparation_cpu_s': preparation, 'alignment': alignment_cost,
              'consolidation_cpu_s': time.process_time()-t, 'candidates': {}}
    del aligned, observations
    baseline_rows = collect(bot, DEV)
    report['baseline'] = metrics(baseline_rows, [r['baseline_p'] for r in baseline_rows])
    learned_models = {}
    for name, table in tables.items():
        begin = time.process_time()
        bot.context_model = {**original, 'bridge': table}
        training_rows = collect(bot, TRAIN)
        fitted, oof_brier = confidence(training_rows)
        bot.context_model['confidence'] = fitted
        trained = time.process_time()-begin
        t = time.process_time()
        checked = collect(bot, DEV)
        measured = metrics(checked, [r['baseline_p'] for r in checked])
        measured.update(oof_brier=oof_brier, training_cpu_s=trained, validation_cpu_s=time.process_time()-t,
                        bridge_words=len(table), associations=sum(v.count('|')+1 for v in table.values()))
        measured['gate'] = measured['useful_rate'] >= report['baseline']['useful_rate']+.05 and \
            measured['quotes_without_data_rate'] <= report['baseline']['quotes_without_data_rate']
        report['candidates'][name] = measured
        learned_models[name] = {'bridge': table, 'confidence': fitted}
        print(name, json.dumps(measured), flush=True)
    selected = min(learned_models, key=lambda name: (report['candidates'][name]['oof_brier'], name))
    report['selected'] = selected
    report['selected_gate'] = report['candidates'][selected]['gate']
    bot.context_model = {**original, **learned_models[selected]}
    bot.calibrated, bot.closest = True, True
    bot.load_context('''Panadería La Espiga
Horario: lunes a sábado de 7:00 a 19:00. Domingos cerrado.
Dirección: Calle Real 12, frente a la plaza.
Pagos: efectivo y tarjeta. No aceptamos cheques.
Productos: pan de trigo, pan integral, croissants y tortas por encargo.
Las tortas por encargo se piden con dos días de anticipación.
''', '')
    report['user_diagnostic_only'] = [{ 'question': q, 'reply': bot.answer(q, [])} for q in (
        '¿A qué hora abren?', '¿Aceptan cheques?', '¿Tienen estacionamiento?', '¿Dónde quedan?')]
    # Experimental learned tables are kept apart from the user's production base.
    model_path = Path('.leobot-data/g69_modelos_experimentales.json')
    model_path.write_text(json.dumps(learned_models, ensure_ascii=False)+'\n')
    report['model_sha256'] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    report['cpu_s'] = time.process_time()-started
    report['rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    report['engine_unchanged'] = engine == git('rev-parse', 'HEAD:leobot') and not git('status', '--porcelain', '--', 'leobot')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'selected': selected, 'gate': report['selected_gate'], 'cpu_s': report['cpu_s'],
                      'rss_mib': report['rss_mib'], 'user': report['user_diagnostic_only']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

"""G-70: correspondencias de pares usadas como evidencia, fuera del motor."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

from leobot import Bot
from experiments.g65_correspondencias import examples, grams, train
from experiments.g68_confianza import collect, metrics, TRAIN, DEV
from experiments.g69_educacion_puente import confidence


def phrase_bridge(observations, model):
    qv, av = model['qv'], model['av']
    anames = {i: g[0] for g, i in av.items() if len(g) == 1}
    qnames = {i: g for g, i in qv.items() if len(g) == 2}
    by_domain = defaultdict(list)
    na, support = Counter(), Counter()
    for domain, q, a in observations:
        qs = {qv[g] for g in grams(q, 2) if len(g) == 2 and g in qv}
        ans = {av[g] for g in grams(a, 2) if g in av}
        na.update(ans)
        by_domain[domain].append((qs, ans))
    for domain in sorted(by_domain):
        pairs = set()
        for qs, ans in by_domain[domain]:
            pairs.update((q, a) for q in qs for a in ans if a in anames)
        support.update(sorted(pairs))
    total, kept = sum(na.values()), defaultdict(list)
    for (q, a), n in sorted(support.items()):
        if n < 5:
            continue
        background = na[a]/total
        conditional = model['prob'][q].get(a, 0.)*background/model['background'][q]
        if conditional/background >= 4 and background < 1:
            delta = max(0., min(1., (conditional-background)/(1-background)))
            if delta:
                kept[qnames[q]].append((anames[a], delta))
    return {q: sorted(row, key=lambda x: (-x[1], x[0]))[:12] for q, row in sorted(kept.items())}


def install(bot, table):
    """The wrapper belongs to the prototype. Production methods stay on disk intact."""
    original_rank, original_bridge = bot._rank, bot._bridge

    def rank(terms, question=''):
        contextual = dict(original_bridge())
        for pair in zip(terms, terms[1:]):
            if pair not in table:
                continue
            for q in pair:
                row = dict(contextual.get(q, ()))
                for a, weight in table[pair]:
                    row[a] = max(row.get(a, 0.), weight/2)
                contextual[q] = sorted(row.items())
        bot._bridge = lambda: contextual
        try:
            return original_rank(terms, question)
        finally:
            bot._bridge = original_bridge
    bot._rank = rank
    return lambda: setattr(bot, '_rank', original_rank)


def main():
    base, corpus, output = map(Path, sys.argv[1:4])
    git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
    engine = git('rev-parse', 'HEAD:leobot')
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if git('status', '--porcelain', '--', 'leobot', 'experiments/g70_puente_condicionado.py'):
        raise RuntimeError('Código sin congelar')
    start = time.process_time()
    bot = Bot.load(base)
    observations = examples(bot, corpus)
    model, cost = train(observations, 2)
    begin = time.process_time()
    table = phrase_bridge(observations, model)
    consolidation = time.process_time()-begin
    del observations, model
    baseline = collect(bot, DEV)
    empty = {}
    restore = install(bot, empty)
    control = collect(bot, DEV)
    restore()
    if baseline != control:
        raise AssertionError('La expansión vacía cambia la base')
    install(bot, table)
    begin = time.process_time()
    training = collect(bot, TRAIN)
    fitted, brier = confidence(training)
    bot.context_model['confidence'] = fitted
    training_cpu = time.process_time()-begin
    begin = time.process_time()
    development = collect(bot, DEV)
    validation_cpu = time.process_time()-begin
    reference = metrics(baseline, [r['baseline_p'] for r in baseline])
    measured = metrics(development, [r['baseline_p'] for r in development])
    gate = measured['useful_rate'] >= reference['useful_rate']+.05 and \
        measured['quotes_without_data_rate'] <= reference['quotes_without_data_rate']
    report = {'engine': engine, 'script_sha256': script_sha, 'alignment_cost': cost,
              'consolidation_cpu_s': consolidation, 'training_cpu_s': training_cpu,
              'validation_cpu_s': validation_cpu, 'phrase_sources': len(table),
              'associations': sum(map(len, table.values())), 'empty_expansion_identical': True,
              'baseline': reference, 'candidate': measured, 'oof_brier': brier, 'gate': gate}
    bot.calibrated, bot.closest = True, True
    bot.load_context('''Panadería La Espiga
Horario: lunes a sábado de 7:00 a 19:00. Domingos cerrado.
Dirección: Calle Real 12, frente a la plaza.
Pagos: efectivo y tarjeta. No aceptamos cheques.
Productos: pan de trigo, pan integral, croissants y tortas por encargo.
Las tortas por encargo se piden con dos días de anticipación.
''', '')
    report['user_diagnostic_only'] = [{'question': q, 'reply': bot.answer(q, [])} for q in (
        '¿A qué hora abren?', '¿Aceptan cheques?', '¿Tienen estacionamiento?', '¿Dónde quedan?')]
    report['cpu_s'] = time.process_time()-start
    report['rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    report['engine_unchanged'] = engine == git('rev-parse', 'HEAD:leobot') and not git('status', '--porcelain', '--', 'leobot')
    report['script_unchanged'] = script_sha == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    Path('.leobot-data/g70_modelo_experimental.json').write_text(json.dumps({
        'phrase_bridge': {'\x1f'.join(q): row for q, row in table.items()}, 'confidence': fitted}, ensure_ascii=False)+'\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

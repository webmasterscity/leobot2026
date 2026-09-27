"""G-68: confianza conjunta aprendida; prototipo fuera del motor.

timeout 600s python3 -m experiments.g68_confianza BASE SALIDA
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from experiments.g57_kiosco import businesses, contains, plain
from experiments.g60_calibrar_confianza import naive_bayes, score
from leobot import Bot

TRAIN = ('congelado', 'congelado_g58', 'congelado_g59', 'congelado_g60', 'congelado_g61', 'desarrollo')
DEV = ('congelado_g62', 'congelado_g63', 'congelado_g64')
THRESHOLD = .4


def collect(bot, banks):
    rows = []
    bot.calibrated, bot.closest = False, False
    for bank in banks:
        root = Path('results_v3/kiosco')/bank
        for name, text, instructions, conversations in businesses(sorted(p for p in root.iterdir() if p.is_dir())):
            bot.load_context(text, instructions)
            group = bank+'/'+name
            rows.extend(collect_context(bot, group, conversations))
    return rows


def collect_context(bot, group, conversations):
    rows = []
    digest = int(hashlib.sha256(group.encode()).hexdigest(), 16)
    for c, conv in enumerate(conversations):
        for i, turn in enumerate(conv):
            action = turn.get('accion', 'responder')
            if action == 'charla':
                continue
            reply = bot.answer(turn['cliente'])
            if reply['status'] != 'answered':
                continue
            keys = [k for k in turn.get('claves', []) or [] if plain(k)]
            if action not in ('abstenerse', 'derivar') and not keys:
                continue
            _, question = bot._question_part(turn['cliente'])
            ranked = bot._rank(bot.context_terms(question), question)
            absent = action in ('abstenerse', 'derivar')
            useful = int(not absent and all(contains(reply['text'], k) for k in keys))
            rows.append({'id': f'{group}/{c}/{i}', 'group': group, 'fold': digest % 5,
                         'half': digest % 2, 'y': useful, 'f': ranked['features'],
                         'core': action == 'responder' and turn.get('tipo') in ('directa', 'si_no'),
                         'absent': absent, 'baseline_p': ranked['useful']})
    return rows

def grow(rows, depth=6, prior=None):
    n, pos = len(rows), sum(r['y'] for r in rows)
    prior = pos/n if prior is None else prior
    node = {'rate': (pos+5*prior)/(n+5), 'n': n}
    if depth == 0 or n < 40 or pos in (0, n):
        return node
    groups = defaultdict(lambda: [0, 0])
    for row in rows:
        for name, value in sorted(row['f'].items()):
            groups[(name, value)][0] += 1
            groups[(name, value)][1] += row['y']
    impurity = lambda p, size: 2*p*(size-p)/size if size else 0.
    best, gain = None, 0.
    for key, (m, p) in sorted(groups.items()):
        if min(m, n-m) < 20:
            continue
        improvement = impurity(pos, n)-impurity(p, m)-impurity(pos-p, n-m)
        if improvement > gain:
            best, gain = key, improvement
    if best is None:
        return node
    name, value = best
    yes = [r for r in rows if r['f'].get(name) == value]
    no = [r for r in rows if r['f'].get(name) != value]
    node.update(test=[name, value], yes=grow(yes, depth-1, node['rate']), no=grow(no, depth-1, node['rate']))
    return node


def predict(model, features):
    if isinstance(model, list):
        return sum(predict(tree, features) for tree in model)/len(model)
    while 'test' in model:
        name, value = model['test']
        model = model['yes'] if features.get(name) == value else model['no']
    return model['rate']


def fit(rows, seed=None):
    if seed is None:
        return grow(rows)
    rng = random.Random(seed)
    return [grow([rng.choice(rows) for _ in rows]) for _ in range(15)]


def isotonic(points):
    # Equal scores must get the same frequency before enforcing monotonicity.
    tied = defaultdict(lambda: [0, 0])
    for s, y in points:
        tied[s][0] += y
        tied[s][1] += 1
    blocks = []
    for s, (y, n) in sorted(tied.items()):
        blocks.append([s, y, n])
        while len(blocks) > 1 and blocks[-2][1]/blocks[-2][2] >= blocks[-1][1]/blocks[-1][2]:
            _, y2, n2 = blocks.pop()
            blocks[-1][1] += y2
            blocks[-1][2] += n2
    while len(blocks) > 1 and min(b[2] for b in blocks) < 30:
        k = min(range(len(blocks)), key=lambda i: (blocks[i][2], i))
        j = k-1 if k == len(blocks)-1 or (k > 0 and blocks[k-1][2] <= blocks[k+1][2]) else k+1
        lo, hi = sorted((j, k))
        blocks[lo:hi+1] = [[blocks[lo][0], blocks[lo][1]+blocks[hi][1], blocks[lo][2]+blocks[hi][2]]]
    return [[low, y/n, n] for low, y, n in blocks]


def calibrated(table, s):
    return next((p for low, p, _ in reversed(table) if s >= low), table[0][1])


def metrics(rows, probabilities):
    cited = [p >= THRESHOLD for p in probabilities]
    core = sum(r['core'] for r in rows)
    absent = sum(r['absent'] for r in rows)
    useful = sum(r['y'] and r['core'] and c for r, c in zip(rows, cited))
    false = sum(r['absent'] and c for r, c in zip(rows, cited))
    return {'n': len(rows), 'core': core, 'ceiling': sum(r['y'] and r['core'] for r in rows),
            'useful_core': useful, 'useful_rate': useful/core, 'quotes': sum(cited),
            'useful_quotes': sum(r['y'] and c for r, c in zip(rows, cited)),
            'absent_n': absent, 'quotes_without_data': false, 'quotes_without_data_rate': false/absent,
            'brier': sum((p-r['y'])**2 for p, r in zip(probabilities, rows))/len(rows)}


def main():
    base, output = map(Path, sys.argv[1:3])
    git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
    engine = git('rev-parse', 'HEAD:leobot')
    if git('status', '--porcelain', '--', 'leobot'):
        raise RuntimeError('Motor sin congelar')
    start = time.process_time()
    bot = Bot.load(base)
    training = collect(bot, TRAIN)
    development = collect(bot, DEV)
    report = {'engine': engine, 'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
              'examples': len(training), 'preparation_cpu_s': time.process_time()-start,
              'baseline': metrics(development, [r['baseline_p'] for r in development]), 'candidates': {}}
    print('baseline', json.dumps(report['baseline']), flush=True)
    nb = naive_bayes(training)
    report['nb_counts_match_base'] = all(nb[k] == bot.context_model['confidence'][k] for k in nb)
    crossed = []
    for half in (0, 1):
        learned = naive_bayes([r for r in training if r['half'] != half])
        crossed.extend((score(learned, r['f']), r['y']) for r in training if r['half'] == half)
    fixed = isotonic(crossed)
    report['ties_corrected'] = metrics(development, [calibrated(fixed, score(nb, r['f'])) for r in development])
    report['old_calibration_duplicate_boundaries'] = len(bot.context_model['confidence']['calibration'])-len(
        {r[0] for r in bot.context_model['confidence']['calibration']})
    models = {}
    for name, seed in (('tree', None), ('forest_0', 0), ('forest_1', 1), ('forest_2', 2)):
        begin = time.process_time()
        points, raw = [], []
        for fold in range(5):
            learned = fit([r for r in training if r['fold'] != fold], seed)
            for row in training:
                if row['fold'] == fold:
                    p = predict(learned, row['f'])
                    points.append((p, row['y']))
                    raw.append((p-row['y'])**2)
        table = isotonic(points)
        model = fit(training, seed)
        models[name] = {'tree': model, 'calibration': table, 'cite_from': THRESHOLD}
        times, probabilities = [], []
        for row in development:
            t = time.perf_counter()
            probabilities.append(calibrated(table, predict(model, row['f'])))
            times.append(1000*(time.perf_counter()-t))
        measured = metrics(development, probabilities)
        measured.update(oof_brier=sum(raw)/len(raw), cpu_s=time.process_time()-begin,
                        confidence_p95_ms=sorted(times)[int(.95*len(times))])
        measured['gate'] = measured['useful_rate'] >= report['baseline']['useful_rate']+.05 and \
            measured['quotes_without_data_rate'] <= report['baseline']['quotes_without_data_rate']
        report['candidates'][name] = measured
        print(name, json.dumps(measured), flush=True)
    forest_brier = sum(report['candidates'][f'forest_{i}']['oof_brier'] for i in (0, 1, 2))/3
    selected = 'tree' if report['candidates']['tree']['oof_brier'] <= forest_brier else 'forest'
    report['selected'] = selected
    report['selected_gate'] = report['candidates']['tree']['gate'] if selected == 'tree' else all(
        report['candidates'][f'forest_{i}']['gate'] for i in (0, 1, 2))
    # The user's visible case is evaluated only after the model is chosen.
    bot.load_context('''Panadería La Espiga
Horario: lunes a sábado de 7:00 a 19:00. Domingos cerrado.
Dirección: Calle Real 12, frente a la plaza.
Pagos: efectivo y tarjeta. No aceptamos cheques.
Productos: pan de trigo, pan integral, croissants y tortas por encargo.
Las tortas por encargo se piden con dos días de anticipación.
''', '')
    report['user_diagnostic_only'] = []
    for question in ('¿A qué hora abren?', '¿Aceptan cheques?', '¿Tienen estacionamiento?', '¿Dónde quedan?'):
        ranked = bot._rank(bot.context_terms(question), question)
        values = {name: calibrated(m['calibration'], predict(m['tree'], ranked['features'])) for name, m in models.items()}
        report['user_diagnostic_only'].append({'question': question, 'baseline_p': ranked['useful'],
                                             'candidate': bot.context_units[ranked['unit']]['text'], 'p': values})
    report['cpu_s'] = time.process_time()-start
    report['rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    report['engine_unchanged'] = engine == git('rev-parse', 'HEAD:leobot') and not git('status', '--porcelain', '--', 'leobot')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    output.with_name('g68_modelos_experimentales.json').write_text(json.dumps(models)+'\n')
    print(json.dumps({'selected': selected, 'gate': report['selected_gate'], 'cpu_s': report['cpu_s'],
                      'rss_mib': report['rss_mib'], 'user': report['user_diagnostic_only']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

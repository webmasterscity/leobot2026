"""Optimistic bound for existing learned shape links; never an answerer."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time
import unicodedata

from leobot import Bot
from experiments.g57_kiosco import businesses, contains, plain
from experiments.g68_confianza import DEV
from experiments.g74_relation_coverage import ROOT, BASE_SHA, ENGINE
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE
from experiments.g80_factorized_selection import G79_SHA

PAR1 = '87c3e8fb1822c6a7dc61990ca3494dc8d509accf'
PAR1_CONTEXT_SHA = '712f4da24427ddc8603f057ec732f732139347573b66d93c978a52502b42c6ae'
PAR1_TABLE_SHA = 'a5cdbb700dc51660cee7005cf3e6d5e2e773ac695fa1ff49baa1d5dbf1ff68c0'


def source():
    data = subprocess.check_output(['git', 'show', PAR1+':leobot/context.py'], cwd=ROOT)
    assert hashlib.sha256(data).hexdigest() == PAR1_CONTEXT_SHA
    parsed = ast.parse(data.decode())
    nodes = [node for node in parsed.body if
             isinstance(node, ast.FunctionDef) and node.name == 'chunk_form' or
             isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('_FORM_EDGES', 'FORM_LONGEST')
                                                  for t in node.targets)]
    scope = {'unicodedata': unicodedata}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), PAR1+':chunk_form', 'exec'), scope)
    path = ROOT/'.leobot-data/g82/par1_tablas.json'
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        original = Path('/media/leonardo/data/leobot2026-paralelo/.leobot-data/par1/par1_tablas.json')
        data = original.read_bytes()
        assert hashlib.sha256(data).hexdigest() == PAR1_TABLE_SHA
        path.write_bytes(data)
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == PAR1_TABLE_SHA
    associations = {q: {shape for shape, weight in rows if shape.startswith('#') and weight > 0}
                    for q, rows in json.loads(data)['bridge_forms'].items()}
    return scope['chunk_form'], {q: shapes for q, shapes in associations.items() if shapes}


def fingerprint():
    files = ('experiments/g82_shape_coverage.py', 'experiments/g79_joint_selection.py',
             'experiments/g80_factorized_selection.py', 'experiments/g75_relational_evidence.py',
             'prereg/G-82-alcance-de-formas-aprendidas.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G82 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (61, 65))
    resource.setrlimit(resource.RLIMIT_AS, (768*1024**2, 768*1024**2))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g79_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G79_SHA
    chunk_form, associations = source()
    bot = Bot.load(base)
    binding = Components().bind(bot)
    bot.context_model = json.loads(previous.read_text())['models']['combined']
    baseline = public_measure(bot, deadline=cpu0+60)
    expected = json.loads((ROOT/'results_v3/g79_joint_selection.json').read_text())['candidates']['combined']
    assert baseline['response_sha256'] == expected['response_sha256']
    stats, details = Counter(), []
    for bank in DEV:
        folder = ROOT/'results_v3/kiosco'/bank
        for name, text, instructions, conversations in businesses(sorted(p for p in folder.iterdir() if p.is_dir())):
            bot.load_context(text, instructions)
            forms = [{f for f in (chunk_form(c) for c in u['text'].split()) if f} for u in bot.context_units]
            eligible = {i for i, u in enumerate(bot.context_units) if u['kind'] not in ('question', 'heading')}
            for c, conversation in enumerate(conversations):
                history = []
                for t, turn in enumerate(conversation):
                    if time.process_time()-cpu0 > 60:
                        raise TimeoutError('G82 agotó CPU')
                    question, action = turn['cliente'], turn.get('accion', 'responder')
                    reply = bot.answer(question, history)
                    history += [question, reply['text']]
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    absent = action in ('abstenerse', 'derivar')
                    if action == 'charla' or reply['status'] == 'phatic' or not absent and not keys:
                        continue
                    terms = set(bot.context_terms(bot._question_part(question)[1]))
                    wanted = set().union(*(associations.get(q, set()) for q in terms))
                    active = {i for i in eligible if wanted & forms[i]}
                    said = reply['status'] in ('answered', 'closest')
                    if absent:
                        stats['absent'] += 1
                        stats['absent_with_signal'] += bool(active)
                        stats['baseline_absent_quotes'] += said
                    if action != 'responder' or turn.get('tipo') not in ('directa', 'si_no'):
                        continue
                    useful = said and all(contains(reply['text'], k) for k in keys)
                    stats['core'] += 1
                    stats['baseline_useful'] += useful
                    stats['core_with_signal'] += bool(active)
                    correct = {i for i in eligible if all(contains(bot.context_units[i]['text'], k) for k in keys)}
                    stats['core_with_correct_unit'] += bool(correct)
                    possible = active & correct
                    if not useful and possible:
                        original_pool = {i for i, _ in bot.selection_candidates(question, 6)}
                        distinct = {i for i in possible if any(any(shape not in forms[j] for j in eligible)
                                                               for shape in wanted & forms[i])}
                        stats['optimistic_additional'] += 1
                        stats['additional_in_pool'] += bool(possible & original_pool)
                        stats['additional_distinguishing'] += bool(distinct)
                        details.append({'id': f'{bank}/{name}/{c}/{t}', 'possible_units': sorted(possible),
                                        'in_pool': bool(possible & original_pool), 'distinguishing': bool(distinct)})
    assert (stats['core'], stats['baseline_useful'], stats['absent'], stats['baseline_absent_quotes']) == (816, 326, 488, 90)
    assert stats['optimistic_additional'] <= stats['core']-stats['baseline_useful']
    assert stats['additional_in_pool'] <= stats['optimistic_additional']
    binding.restore()
    cost = {'cpu_s': time.process_time()-cpu0, 'wall_s': time.monotonic()-wall0,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    ceiling = stats['baseline_useful']+stats['optimistic_additional']
    assert fingerprint() == hashes
    report = {'experiment': 'G82', 'scope': 'optimistic availability bound, not learned performance or full-system ceiling',
              'repository_engine_sha': ENGINE, 'selector_reference': REFERENCE, 'base_sha256': BASE_SHA,
              'g79_models_sha256': G79_SHA, 'par1_reference': PAR1, 'par1_context_sha256': PAR1_CONTEXT_SHA,
              'par1_table_sha256': PAR1_TABLE_SHA, 'source_sha256': hashes, 'baseline': baseline,
              'learned_form_questions': len(associations), 'associations': sum(len(v) for v in associations.values()),
              'stats': dict(stats), 'optimistic_useful_ceiling': ceiling,
              'optimistic_rate': ceiling/stats['core'], 'details': details,
              'gates': {'potential_gain': stats['optimistic_additional'] >= 41,
                        'sixty_percent_possible_by_this_route_alone': ceiling >= 490,
                        'budget': cost['cpu_s'] <= 60 and cost['wall_s'] <= 90 and cost['peak_rss_kib'] <= 768*1024},
              'cost': cost}
    (ROOT/'results_v3/g82_shape_coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('stats', 'optimistic_useful_ceiling', 'gates', 'cost')}), flush=True)


if __name__ == '__main__':
    main()

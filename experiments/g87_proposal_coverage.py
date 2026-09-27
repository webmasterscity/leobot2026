"""Availability diagnostic only; gold keys never select a public response."""
from collections import Counter
import hashlib
import json
import resource
import subprocess
import time

from leobot import Bot
from experiments import g65_correspondencias as g65
from experiments.g57_kiosco import businesses, contains, plain
from experiments.g68_confianza import DEV
from experiments.g74_relation_coverage import ROOT, ENGINE, BASE_SHA
from experiments.g75_relational_evidence import public_measure
from experiments.g79_joint_selection import Components, REFERENCE
from experiments.g85_human_selection import DirectBinding, G84_SHA


def proposed(initial, scores, units):
    eligible = [i for i, u in enumerate(units) if u['kind'] not in ('question', 'heading')]
    additional = sorted(eligible, key=lambda i: (-scores[i], i))[:6]
    return list(dict.fromkeys(initial+additional))


def fingerprint():
    files = ('experiments/g87_proposal_coverage.py', 'experiments/test_g87_proposal_coverage.py',
             'experiments/g85_human_selection.py', 'experiments/g84_indirect_alignment.py',
             'experiments/g65_correspondencias.py', 'experiments/g79_joint_selection.py',
             'experiments/g75_relational_evidence.py', 'prereg/G-87-alcance-de-propuestas-aprendidas.md')
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    if git('rev-parse', 'HEAD:leobot') != ENGINE or git('status', '--porcelain', '--', 'leobot', *files):
        raise RuntimeError('G87 no congelado')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (61, 65))
    resource.setrlimit(resource.RLIMIT_AS, (768*1024**2, 768*1024**2))
    hashes, cpu0, wall0 = fingerprint(), time.process_time(), time.monotonic()
    base, previous = ROOT/'.leobot-data/base_kiosco.json', ROOT/'.leobot-data/g84_models.json'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == G84_SHA
    bot = Bot.load(base)
    reference = Components().bind(bot)
    bot.context_model = json.loads(previous.read_text())['models']['direct']
    binding = DirectBinding(bot)
    loaded_cpu = time.process_time()-cpu0
    start = time.process_time()
    baseline = public_measure(bot, deadline=cpu0+60)
    expected = json.loads((ROOT/'results_v3/g84_indirect_alignment.json').read_text())['candidates']['direct']
    assert baseline['response_sha256'] == expected['response_sha256']
    public_cpu = time.process_time()-start
    start = time.process_time()
    stats, details, counts = Counter(), [], {'core': Counter(), 'absent': Counter()}
    for bank in DEV:
        folder = ROOT/'results_v3/kiosco'/bank
        for name, text, instructions, conversations in businesses(sorted(p for p in folder.iterdir() if p.is_dir())):
            bot.load_context(text, instructions)
            eligible = {i for i, u in enumerate(bot.context_units) if u['kind'] not in ('question', 'heading')}
            model = binding.decoded[0][0]
            for c, conversation in enumerate(conversations):
                for t, turn in enumerate(conversation):
                    if time.process_time()-cpu0 > 60:
                        raise TimeoutError('G87 agotó CPU')
                    action = turn.get('accion', 'responder')
                    absent = action in ('abstenerse', 'derivar')
                    core = action == 'responder' and turn.get('tipo') in ('directa', 'si_no')
                    keys = [k for k in turn.get('claves') or [] if plain(k)]
                    if not (core or absent) or core and not keys:
                        continue
                    _, question = bot._question_part(turn['cliente'])
                    if bot._phatic(question):
                        continue
                    terms = bot.context_terms(question)
                    order = bot._scored(terms, question)['order']
                    initial = [i for _, i in order[:6]]
                    wider = [i for _, i in order[:12]]
                    scores = g65.alignment_scores(model, binding.prepared, sorted(set(terms)))
                    union = proposed(initial, scores, bot.context_units)
                    assert set(initial) <= set(union) and len(union) <= 12
                    assert set(union)-set(initial) <= eligible
                    kind = 'absent' if absent else 'core'
                    stats[kind] += 1
                    for label, pool in (('six', initial), ('twelve', wider), ('union', union)):
                        counts[kind][label+'_total_candidates'] += len(pool)
                    counts[kind]['identical_alignment_scores'] += len({scores[i] for i in eligible}) <= 1
                    if absent:
                        continue
                    correct = {i for i in eligible if all(contains(bot.context_units[i]['text'], k) for k in keys)}
                    hits = {label: bool(correct & set(pool)) for label, pool in
                            (('six', initial), ('twelve', wider), ('union', union), ('all', eligible))}
                    for label, hit in hits.items():
                        stats[label+'_covered'] += hit
                    stats['union_new_over_six'] += hits['union'] and not hits['six']
                    stats['union_unique_over_twelve'] += hits['union'] and not hits['twelve']
                    stats['union_losses_vs_twelve'] += hits['twelve'] and not hits['union']
                    details.append({'id': f'{bank}/{name}/{c}/{t}', 'correct': sorted(correct),
                                    'six': initial, 'twelve': wider, 'union': union})
    assert (stats['core'], stats['absent']) == (816, 488)
    assert stats['union_new_over_six'] == stats['union_covered']-stats['six_covered']
    prep = dict(binding.cost)
    binding.restore()
    reference.restore()
    assert fingerprint() == hashes
    cost = {'load_cpu_s': loaded_cpu, 'public_check_cpu_s': public_cpu,
            'diagnostic_cpu_s': time.process_time()-start, 'preparation_included': prep,
            'cpu_s': time.process_time()-cpu0, 'wall_s': time.monotonic()-wall0,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    gates = {'potential_gain': stats['union_new_over_six'] >= 17,
             'distinct_information': stats['union_unique_over_twelve'] >= 17,
             'budget': cost['cpu_s'] <= 60 and cost['wall_s'] <= 90 and cost['peak_rss_kib'] <= 768*1024}
    report = {'experiment': 'G87', 'scope': 'availability oracle only; not learned performance',
              'repository_engine_sha': ENGINE, 'selector_reference': REFERENCE,
              'source_sha256': hashes, 'g84_models_sha256': G84_SHA, 'base_sha256': BASE_SHA,
              'baseline': baseline, 'stats': dict(stats), 'inventory_sizes': {k: dict(v) for k, v in counts.items()},
              'details': details, 'gates': gates, 'continue_to_learning': all(gates.values()), 'cost': cost}
    (ROOT/'results_v3/g87_proposal_coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('stats', 'inventory_sizes', 'gates', 'cost')}), flush=True)


if __name__ == '__main__':
    start_cpu, start_wall = time.process_time(), time.monotonic()
    try:
        main()
    except Exception as error:
        (ROOT/'results_v3/g87_interruption.json').write_text(json.dumps({
            'error': repr(error), 'cpu_s': time.process_time()-start_cpu,
            'wall_s': time.monotonic()-start_wall,
            'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, indent=2)+'\n')
        raise

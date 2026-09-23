"""G-38: prover work proportional to distinct atoms, not to assertions.

See prereg/G-38-trabajo-por-atomo-distinto.md.
python3 -m experiments.g38_distinct_atoms ENGINE_ROOT OUT.json [REPS]

ENGINE_ROOT is a directory holding a ``leobot`` package (the working tree or an
extracted tag), so the same cases run on the baseline and on the candidate.
"""
from __future__ import annotations

import json
import resource
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

N_SOURCES = 100_000
N_NEG = 50_000


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.95 * len(xs)))]


def build(kb, case):
    """Adversarial memories from the G-37 audit, plus a rule join over duplicates."""
    from leobot.core import Atom, Rule
    add = kb.add
    if case == 'duplicate_sources':
        for i in range(N_SOURCES):
            add(Atom('padre', ('a', 'b')), f's{i}')
    elif case == 'negated_positions':
        add(Atom('padre', ('a', 'b')), 'usuario')
        for i in range(N_NEG):
            add(Atom('!padre', ('a', f'y{i}')), 'usuario')
            add(Atom('!padre', (f'x{i}', 'b')), 'usuario')
    elif case == 'duplicate_join':
        for i in range(N_SOURCES // 2):
            add(Atom('padre', ('a', 'b')), f's{i}')
            add(Atom('padre', ('b', 'c')), f's{i}')
        kb.add_rule(Rule('abuelo_def', Atom('abuelo', ('?x', '?z')),
                         (Atom('padre', ('?x', '?y')), Atom('padre', ('?y', '?z')))))
    if hasattr(kb, 'db'):
        kb.db.commit()


QUERIES = {
    'duplicate_sources': ['padre(a,b)', '!padre(a,b)', 'padre(a,?x)', 'padre(?x,b)'],
    'negated_positions': ['padre(a,b)', '!padre(a,b)'],
    'duplicate_join': ['abuelo(a,c)', 'abuelo(a,?z)'],
}


def run_case(kb, case, reps):
    from leobot.core import Atom, Engine
    out = {}
    for text in QUERIES[case]:
        atom = Atom.parse(text)
        times, results = [], []
        for _ in range(reps):
            t = perf_counter()
            r = Engine(kb).answer(atom)
            times.append((perf_counter() - t) * 1000)
            results.append((r['status'], r['positive']['complete'], r['positive']['reason'],
                            r['positive']['stats']['work'],
                            [(p.atom.pred, p.atom.args, p.id) for p in r['positive']['answers']]))
        status, complete, reason, work, answers = results[0]
        out[text] = {'status': status, 'complete': complete, 'reason': reason, 'work': work,
                     'answers': [f'{p}{list(a)}:{i}' for p, a, i in answers][:5],
                     'n_answers': len(answers), 'stable': all(x == results[0] for x in results),
                     'p50_ms': round(median(times), 3), 'p95_ms': round(p95(times), 3)}
    return out


def main():
    root, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    sys.path.insert(0, str(root))
    import leobot
    from leobot.core import KnowledgeBase
    from leobot.diskkb import SQLiteKnowledgeBase
    report = {'engine_path': leobot.__file__, 'reps': reps, 'memory': {}, 'disk': {}}
    for case in QUERIES:
        kb = KnowledgeBase(); build(kb, case)
        report['memory'][case] = run_case(kb, case, reps)
        del kb
        with tempfile.TemporaryDirectory() as d:
            kb = SQLiteKnowledgeBase(Path(d) / 'kb.sqlite')
            t = perf_counter(); build(kb, case); built = perf_counter() - t
            report['disk'][case] = run_case(kb, case, reps)
            report['disk'][case]['_build_s'] = round(built, 2)
            kb.close()
    report['rss_peak_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    out_path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    for store in ('memory', 'disk'):
        for case, qs in report[store].items():
            for q, r in qs.items():
                if q.startswith('_'):
                    continue
                print(f"{store:6} {case:18} {q:14} {r['status']:10} complete={r['complete']!s:5} "
                      f"work={r['work']:>7} p95={r['p95_ms']:>9} ms answers={r['n_answers']}")
    print('rss_peak_mib', report['rss_peak_mib'])


if __name__ == '__main__':
    main()

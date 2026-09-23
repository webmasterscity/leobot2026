"""G-38 differential: candidate engine against a baseline engine, same random memories.

See prereg/G-38-trabajo-por-atomo-distinto.md.
python3 -m experiments.g38_differential BASELINE_ROOT CANDIDATE_ROOT OUT.json [N_BASES] [FIRST_SEED]

The gate run takes FIRST_SEED from the first 8 hex digits of the frozen engine
hash, so its memories were not seen during development (seeds 0..59).

Each engine runs in its own child process (``--child ROOT FIRST N``) and prints
one JSON line per memory; the parent compares them.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

PREDS = ('p', 'q', 'r')
N_QUERIES = 20


def proof_key(p):
    return [p.atom.pred, list(p.atom.args), p.kind, p.id, p.hypothesis, p.contested,
            [proof_key(c) for c in p.children]]


def build(kb, rng):
    from leobot.core import Atom, Rule
    ents = [f'e{i}' for i in range(rng.randint(4, 9))]
    fids = []
    for _ in range(rng.randint(20, 160)):
        pred = rng.choice(PREDS)
        if rng.random() < 0.12:
            pred = '!' + pred
        atom = Atom(pred, (rng.choice(ents), rng.choice(ents)))
        fids.append(kb.add(atom, f's{rng.randint(0, 3)}'))
    for fid in rng.sample(fids, k=len(fids) // 6):
        kb.remove(fid)
    rules = []
    if rng.random() < 0.7:
        rules.append(Rule('comp', Atom('t', ('?x', '?z')), (Atom('p', ('?x', '?y')), Atom('q', ('?y', '?z')))))
    if rng.random() < 0.4:
        rules.append(Rule('inv', Atom('q', ('?x', '?y')), (Atom('r', ('?y', '?x')),)))
    if rng.random() < 0.3:
        rules.append(Rule('neg', Atom('!t', ('?x', '?y')), (Atom('!p', ('?x', '?y')),)))
    if rng.random() < 0.5:
        rules.append(Rule('learned:anc:base', Atom('anc', ('?x', '?y')), (Atom('p', ('?x', '?y')),), 'learned'))
        rules.append(Rule('learned:anc:rec', Atom('anc', ('?x', '?z')),
                          (Atom('p', ('?x', '?y')), Atom('anc', ('?y', '?z'))), 'learned'))
    if rng.random() < 0.3:
        rules.append(Rule('reach', Atom('reach', ('?x', '?z')), (Atom('r', ('?x', '?y')), Atom('reach', ('?y', '?z')))))
        rules.append(Rule('reach0', Atom('reach', ('?x', '?y')), (Atom('r', ('?x', '?y')),)))
    for rule in rules:
        kb.add_rule(rule)
    heads = sorted({*PREDS, *(r.head.pred.lstrip('!') for r in rules)})
    queries = []
    for _ in range(N_QUERIES):
        pred = rng.choice(heads)
        if rng.random() < 0.2:
            pred = '!' + pred
        args = tuple(rng.choice(ents) if rng.random() < 0.6 else f'?v{i}' for i in range(2))
        queries.append(Atom(pred, args))
    return queries


def run_base(kb, queries, budget):
    from leobot.core import Engine
    out = {'matches': [], 'contains': [], 'answers': []}
    for q in queries:
        out['matches'].append([f['id'] for f in kb.matches(q)])
        out['contains'].append(kb.contains(q))
        r = Engine(kb, max_work=budget).answer(q)
        out['answers'].append({
            'status': r['status'],
            'complete': r['positive']['complete'] and (r['negative'] is None or r['negative']['complete']),
            'positive': [proof_key(p) for p in r['positive']['answers']],
            'negative': [proof_key(p) for p in r['negative']['answers']] if r['negative'] else None})
    return out


def child(root, first, n):
    sys.path.insert(0, str(Path(root).resolve()))
    import leobot
    from leobot import Bot
    from leobot.diskkb import SQLiteKnowledgeBase
    for seed in range(first, first + n):
        # Small budgets on some memories make incompleteness part of the comparison.
        budget = 200_000 if seed % 3 else 300
        rng = random.Random(seed)
        bot = Bot(); queries = build(bot.kb, rng)
        rec = {'seed': seed, 'engine': leobot.__file__, 'budget': budget, 'memory': run_base(bot.kb, queries, budget)}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bot.json'; bot.save(path)
            rec['restart'] = run_base(Bot.load(path).kb, queries, budget)
            if seed % 5 == 0:
                kb = SQLiteKnowledgeBase(Path(d) / 'k.sqlite')
                build(kb, random.Random(seed))
                rec['disk'] = run_base(kb, queries, budget)
                kb.close()
        print(json.dumps(rec), flush=True)


def main():
    if sys.argv[1] == '--child':
        child(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        return
    base_root, cand_root, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 300
    first = int(sys.argv[5]) if len(sys.argv) > 5 else 0

    def run(root):
        text = subprocess.check_output([sys.executable, '-m', 'experiments.g38_differential', '--child', root, str(first), str(n)],
                                       text=True, env={'PYTHONHASHSEED': '0', 'PATH': '/usr/bin:/bin'},
                                       cwd=Path(__file__).resolve().parents[1], timeout=1800)
        return [json.loads(line) for line in text.splitlines()]

    base, cand = run(base_root), run(cand_root)
    counts = {'comparisons': 0, 'differences': 0, 'baseline_incomplete': 0,
              'baseline_incomplete_now_complete': 0, 'baseline_incomplete_differences': 0}
    examples = []
    for b, c in zip(base, cand, strict=True):
        for store in ('memory', 'restart', 'disk'):
            if store not in b:
                continue
            for kind in ('matches', 'contains'):
                for i, (x, y) in enumerate(zip(b[store][kind], c[store][kind], strict=True)):
                    counts['comparisons'] += 1
                    if x != y:
                        counts['differences'] += 1
                        examples.append({'seed': b['seed'], 'store': store, 'kind': kind, 'query': i, 'base': x, 'cand': y})
            for i, (x, y) in enumerate(zip(b[store]['answers'], c[store]['answers'], strict=True)):
                counts['comparisons'] += 1
                if not x['complete']:
                    counts['baseline_incomplete'] += 1
                    counts['baseline_incomplete_now_complete'] += bool(y['complete'])
                    counts['baseline_incomplete_differences'] += x != y
                    continue
                if x != y:
                    counts['differences'] += 1
                    examples.append({'seed': b['seed'], 'store': store, 'kind': 'answer', 'query': i, 'base': x, 'cand': y})
    report = {'baseline': base[0]['engine'], 'candidate': cand[0]['engine'], 'bases': n, 'first_seed': first, **counts, 'examples': examples[:20]}
    out.write_text(json.dumps(report, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'examples'}))
    for e in examples[:3]:
        print(json.dumps(e)[:600])


if __name__ == '__main__':
    main()
